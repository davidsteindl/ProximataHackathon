"""Replay uses only REST; test human decisions are explicit fixture actions."""

import json

import pytest

from app.extraction import CachedExtractor, validate_quotes
from conftest import BACKEND
from app.replay import OfflineChannels, Replay, ReplayError, Scenario, ScenarioClock
from test_lifecycle import HUMAN, action, decision


def test_offline_preflight_does_not_return_provider_configuration(client, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    monkeypatch.setenv("LLM_API_KEY", "synthetic-secret-not-for-response")
    assert client.get("/replay/config").json() == {"offline_ready": False}
    monkeypatch.setenv("LLM_PROVIDER", "cached")
    assert client.get("/replay/config").json() == {"offline_ready": True}


def test_all_scenario_messages_have_offline_extraction_fixtures():
    scenario = json.loads((BACKEND / "demo/hero-scenario.json").read_text(encoding="utf-8"))
    extractor = CachedExtractor(BACKEND / "demo/extraction-cache.json")
    for step in scenario["steps"]:
        if "text" not in step:
            continue
        text = (f"Subject: {step['subject']}\n\n{step['text']}" if step.get("subject") else step["text"])
        batch = extractor.extract(text, step["sender_role"])
        statements = validate_quotes(batch, text, text)
        assert statements, step["id"]


CAD = BACKEND.parent / "cad/plans"


class RecordingAPI:
    def __init__(self, client):
        self.client, self.writes = client, []

    def get(self, path, **kwargs):
        return self.client.get(path, **kwargs)

    def post(self, path, **kwargs):
        self.writes.append(path)
        return self.client.post(path, **kwargs)


def build_replay(client, *, pause, log=lambda *args, **kwargs: None):
    api = RecordingAPI(client)
    scenario = Scenario.model_validate_json((BACKEND / "demo/hero-scenario.json").read_text(encoding="utf-8"))
    channels = OfflineChannels(api, "unit-hero", CAD, log)
    replay = Replay(api, scenario, CAD, channels, pause=pause, sleep=lambda _: None, output=lambda _: None, log=log)
    return replay, api


def test_full_offline_hero_only_test_human_callback_submits_decisions(client, monkeypatch):
    import httpx

    def no_network(*args, **kwargs):
        raise AssertionError("Offline replay attempted provider traffic")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_network)
    monkeypatch.setattr("app.gmail.GmailClient.__init__", no_network)
    monkeypatch.setattr("app.telegram.TelegramClient.__init__", no_network)
    monkeypatch.setenv("LLM_PROVIDER", "cached")
    checkpoints, records, confirmation_attempts = [], [], []

    def approve(flag):
        if flag["state"] == "notified":
            assert action(client, flag, "acknowledge").status_code == 200
        proposal = flag["advice"]["proposals"][0]
        response = client.post(f"/proposals/{proposal['id']}/decisions", json={
            **HUMAN, "decision": "approved", "reason": "Synthetic human postpones closing work",
        })
        assert response.status_code == 200, response.text

    def human(_):
        step = next_step[0]
        if step.decision == "confirm_inspection":
            confirmation_attempts.append(step.decision)
            if len(confirmation_attempts) == 1:
                # A different positive seed claim can satisfy the rule but must not
                # replace review of the concrete day-4 source requested by replay.
                assert decision(client, "example-contradictory-negative", "rejected").status_code == 200
                assert decision(client, "example-contradictory-positive", "confirmed").status_code == 200
                return ""
        next_step.pop(0)
        checkpoints.append(step.decision)
        if step.decision == "acknowledge_b":
            assert action(client, replay.flag("b"), "acknowledge").status_code == 200
        elif step.decision == "approve_a":
            approve(replay.flag("a"))
        elif step.decision == "resolve_a":
            assert action(client, replay.flag("a"), "resolved").status_code == 200
        elif step.decision == "correct_false_alarm":
            assert action(client, replay.flag("false_alarm"), "false_alarm",
                          correction_event_id=replay.results["learning_before"]["events"][0]["id"]).status_code == 200
        elif step.decision == "confirm_inspection":
            for evidence in replay.evidence_for("concrete_result"):
                assert decision(client, evidence["id"], "confirmed").status_code == 200
        elif step.decision == "confirm_revision":
            for evidence in replay.evidence_for("revision_receipt"):
                assert decision(client, evidence["id"], "confirmed").status_code == 200
        else:
            approve(replay.flag("genuine"))
            assert action(client, replay.flag("genuine"), "resolved").status_code == 200
        return ""

    replay, api = build_replay(client, pause=human, log=lambda kind, **record: records.append({"kind": kind, **record}))
    next_step = [step for step in replay.scenario.steps if step.decision]
    replay.run()
    assert checkpoints == [step.decision for step in replay.scenario.steps if step.decision]
    assert len(confirmation_attempts) == 2
    assert not any(path.endswith(("/reviews", "/actions", "/decisions")) for path in api.writes)
    assert all(result["source"]["extraction_backend"] == "cached:v1" for result in replay.results.values())
    deliveries = [record["message"] for record in records if record["kind"] == "synthetic_delivery"]
    assert {message["kind"] for message in deliveries} >= {"warning", "approval_request", "proposal_followup"}
    assert replay.flag("a")["state"] == replay.flag("genuine")["state"] == "resolved"
    assert replay.flag("b")["state"] == "acknowledged" and replay.flag("b")["evaluation"] == "satisfied"
    # Reset after the completed run clears feedback, proposals, source/events, geometry and outbox,
    # then restores C drawings with synthetic, never-human baseline confirmation history.
    replay.reset()
    assert not client.get("/events").json()
    assert not client.get("/flags", params={"status": "all"}).json()
    assert not client.get("/outbox").json()
    assert not client.get("/proposals").json()
    assert not client.get("/site-knowledge").json()
    assert {item["revision_id"] for item in client.get("/geometry").json()} == {"A-101-C", "A-102-C", "A-103-C", "A-104-C"}
    assert all(item["history"][0]["actor_type"] == "seed_import" for item in client.get("/evidence").json())
    question = next(step for step in replay.scenario.steps if step.id == "learning_before")
    fresh = replay.channels.receive(question, replay.clock.timestamp(question))
    assert fresh["events"][0]["intent"] == "planned_work"
    assert "learning" not in fresh["events"][0]["details"]


def test_live_api_is_rejected_before_reset(client, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai_compatible")
    replay, api = build_replay(client, pause=lambda _: "q")
    with pytest.raises(ReplayError, match="LLM_PROVIDER=cached"):
        replay.reset()
    assert api.writes == []


def test_clock_speed_is_adjustable_and_rejects_invalid_values():
    from app.seed import load_seed

    site = load_seed(BACKEND / "seed").site
    scenario = Scenario.model_validate_json((BACKEND / "demo/hero-scenario.json").read_text(encoding="utf-8"))
    slept = []
    clock = ScenarioClock(site, 3600, sleep=slept.append)
    start = clock.advance(scenario.steps[0])
    end = clock.advance(scenario.steps[1])
    assert start.isoformat() == "2026-11-13T10:15:00+01:00"
    assert sum(slept) == (end - start).total_seconds() / 3600
    assert max(slept) <= 1
    for speed in (0, -1, float("inf"), float("nan")):
        with pytest.raises(ReplayError):
            ScenarioClock(site, speed)



def test_enter_does_not_replace_a_dashboard_decision_and_quit_preserves_state(client):
    answers = iter(["", "q"])
    replay, api = build_replay(client, pause=lambda _: next(answers))
    with pytest.raises(ReplayError, match="human checkpoint"):
        replay.run()
    assert replay.flag("b")["state"] == "notified"
    assert not any(path.endswith(("/reviews", "/actions", "/decisions")) for path in api.writes)
    assert "closing" not in replay.results


def test_missing_drawing_is_rejected_before_destructive_reset(client, tmp_path):
    replay, api = build_replay(client, pause=lambda _: "q")
    replay.plans = tmp_path
    with pytest.raises(ReplayError, match="Missing DXF"):
        replay.reset()
    assert api.writes == []
