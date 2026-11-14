"""Morning scan and escalation (#14): schedule-only detection, dedup, time logic."""

from datetime import UTC, datetime, time, timedelta
from unittest.mock import MagicMock

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app import jobs, models
from app.job_schedule import JobSchedule, parse_scan_time, run_due_jobs
from conftest import BACKEND
from test_lifecycle import action, decision, signal
from test_rules import ingest, initialized, inspection_claim  # noqa: F401

# Day 2 (PLAN §7), 06:00 site time (Europe/Vienna): drywall-F3 starts on day 3.
DAY2_MORNING = "2026-11-14T05:00:00Z"


def scan(client, as_of=DAY2_MORNING):
    response = client.post("/jobs/morning-scan", json={"as_of": as_of})
    assert response.status_code == 200, response.text
    return response.json()


def escalate(client, as_of):
    response = client.post("/jobs/escalation", json={"as_of": as_of})
    assert response.status_code == 200, response.text
    return response.json()


def drywall_f3(client, status="open"):
    flags = [flag for flag in client.get("/flags", params={"status": status}).json()
             if flag["task_id"] == "drywall-F3" and flag["type"] == "A"]
    assert len(flags) == 1, flags
    return flags[0]


def test_scan_finds_hero_conflict_from_schedule_alone(initialized):
    assert initialized.get("/flags").json() == []
    result = scan(initialized)
    assert "drywall-F3" in result["task_ids"]
    # Rough-in plumbing does not require the inspection; the scan is not a blanket alarm.
    assert not any(task.startswith("plumbing") for task in result["task_ids"])
    flag = drywall_f3(initialized)
    assert flag["id"] in result["created_flag_ids"]
    assert (flag["zone_id"], flag["inspection_id"], flag["activity"]) == ("F3", "rough-in-F3", "drywall")
    assert flag["responsible"]["id"] == "lead-drywall"
    assert flag["evaluation"] == "unknown" and flag["state"] == "detected"
    assert flag["sources"] == []
    assert flag["audit"][0] == {**flag["audit"][0], "action": "detected", "actor": "morning_scan",
                                "channel": "system", "source_ref": "schedule:drywall-F3@2026-11-15T06:00:00+00:00"}
    [warning] = flag["notifications"]
    assert warning["kind"] == "warning"
    assert "morning scan of the site schedule" in warning["content"]
    assert "drywall-F3" in warning["content"]


def test_scan_uses_confirmed_seed_baseline_without_inventing_proof(client, seed):
    assert client.post("/seed/import", json=seed.model_dump(mode="json")).status_code == 200
    scan(client)
    flag = drywall_f3(client)
    # Confirmed pending baseline plus unconfirmed pass/fail examples: never satisfied.
    assert flag["evaluation"] in {"not_satisfied", "contradictory"}


def test_scan_is_idempotent_and_dedups_with_later_announcement(initialized):
    first = scan(initialized)
    flag = drywall_f3(initialized)
    again = scan(initialized)
    assert again["created_flag_ids"] == [] and again["updated_flag_ids"] == []
    assert drywall_f3(initialized) == flag
    # The day-2 18:05 announcement for 3B joins the scan's Flag for the same Task.
    result = ingest(initialized)
    joined = drywall_f3(initialized)
    assert joined["id"] == flag["id"] and joined["zone_id"] == "F3"
    assert [source["id"] for source in joined["sources"]] == [result["events"][0]["id"]]
    assert len(initialized.get("/flags").json()) == len(first["created_flag_ids"])
    assert len(initialized.get("/outbox").json()) == len(first["created_flag_ids"])


def test_scan_after_announcement_attaches_once_without_new_flag(initialized):
    ingest(initialized)
    announced = drywall_f3(initialized)
    assert announced["zone_id"] == "3B"
    for _ in range(2):
        result = scan(initialized)
    assert announced["id"] not in result["created_flag_ids"]
    flag = drywall_f3(initialized)
    assert flag["id"] == announced["id"]
    assert [item["action"] for item in flag["audit"]] == ["detected", "morning_scan"]
    assert len(flag["notifications"]) == 1


def test_unconfirmed_success_claim_is_still_flagged_until_human_confirmation(initialized):
    evidence_id = inspection_claim(initialized)
    scan(initialized)
    flag = drywall_f3(initialized)
    assert flag["evaluation"] == "unknown"
    assert any(item["id"] == evidence_id and item["review_status"] == "unconfirmed" for item in flag["evidence"])
    # Human confirmation re-runs rules, also for schedule-only Flags; it never closes them.
    assert decision(initialized, evidence_id, "confirmed").status_code == 200
    flag = drywall_f3(initialized)
    assert flag["evaluation"] == "satisfied" and flag["awaiting_human_closure"]
    assert flag["state"] == "detected"


def test_satisfied_precondition_creates_no_scan_flag(initialized):
    evidence_id = inspection_claim(initialized)
    assert decision(initialized, evidence_id, "confirmed").status_code == 200
    scan(initialized)
    assert not any(flag["task_id"] in {"drywall-F3", "insulation-F3"}
                   for flag in initialized.get("/flags").json())


@pytest.mark.parametrize(("as_of", "days", "expected", "excluded"), [
    # Day 1, 07:30 Vienna, today only: insulation starts tomorrow.
    ("2026-11-13T06:30:00Z", 0, set(), {"insulation-F3", "drywall-F3"}),
    ("2026-11-13T06:30:00Z", 1, {"insulation-F3"}, {"drywall-F3"}),
    ("2026-11-14T05:00:00Z", 1, {"insulation-F3", "drywall-F3"}, set()),
    # After the task has started it is no longer upcoming work.
    ("2026-11-15T07:00:00Z", 1, set(), {"drywall-F3"}),
])
def test_scan_window_follows_site_days(initialized, engine, monkeypatch, as_of, days, expected, excluded):
    monkeypatch.setenv("SCAN_LOOKAHEAD_DAYS", str(days))
    task_ids = set(scan(initialized, as_of)["task_ids"])
    assert expected <= task_ids and not excluded & task_ids


def test_scan_window_uses_site_timezone():
    start, end = jobs.scan_window(datetime(2026, 11, 14, 22, 30, tzinfo=UTC), "Europe/Vienna", 0)
    # 23:30 Vienna on day 2: the local day ends at 23:00 UTC.
    assert end == datetime(2026, 11, 14, 23, 0, tzinfo=UTC)
    assert start == datetime(2026, 11, 14, 22, 30, tzinfo=UTC)


def close(client, engine, flag):
    signal(engine, flag["id"], "notified")
    flag = client.get(f"/flags/{flag['id']}").json()
    response = action(client, flag, "false_alarm")
    assert response.status_code == 200, response.text


def test_human_closure_settles_scheduled_occurrence_but_not_a_reschedule(initialized, engine):
    scan(initialized)
    flag = drywall_f3(initialized)
    close(initialized, engine, flag)
    scan(initialized)
    assert not any(item["task_id"] == "drywall-F3" for item in initialized.get("/flags").json())
    with Session(engine) as session, session.begin():
        task = session.get(models.Task, "drywall-F3")
        task.starts_at += timedelta(hours=2)
        task.ends_at += timedelta(hours=2)
    scan(initialized)
    assert drywall_f3(initialized)["id"] != flag["id"]


def test_scan_requires_seed(client):
    assert client.post("/jobs/morning-scan", json={}).status_code == 409


# Default test message (day 2, 18:05 site time): the Event Flag's detection time.
SENT = datetime(2026, 11, 14, 17, 5, tzinfo=UTC)


def iso(value):
    return value.isoformat().replace("+00:00", "Z")


def test_escalation_fires_once_after_threshold_and_is_audited(initialized, engine, monkeypatch):
    monkeypatch.setenv("ESCALATION_HOURS", "4")
    monkeypatch.setenv("SUPERINTENDENT_EMAIL", "superintendent@example.test")
    ingest(initialized)
    flag = drywall_f3(initialized)
    assert escalate(initialized, iso(SENT + timedelta(hours=3, minutes=59)))["escalated_flag_ids"] == []
    result = escalate(initialized, iso(SENT + timedelta(hours=4)))
    assert result == {**result, "escalated_flag_ids": [flag["id"]], "threshold_hours": 4}
    for hours in (5, 9, 48):
        assert escalate(initialized, iso(SENT + timedelta(hours=hours)))["escalated_flag_ids"] == []
    flag = drywall_f3(initialized)
    assert flag["state"] == "detected"
    escalated = [item for item in flag["audit"] if item["action"] == "escalated"]
    assert len(escalated) == 1
    assert escalated[0]["actor"] == "escalation_timer" and escalated[0]["channel"] == "system"
    messages = {item["kind"]: item for item in flag["notifications"]}
    assert set(messages) == {"warning", "escalation"}
    assert escalated[0]["source_ref"] == f"outbox:{messages['escalation']['id']}"
    assert messages["escalation"]["recipient"] == "superintendent@example.test"
    assert "no human reaction for 4 hours" in messages["escalation"]["content"]
    assert "does not change, approve or close" in messages["escalation"]["content"]


def test_human_reaction_prevents_escalation(initialized, engine):
    ingest(initialized)
    flag = drywall_f3(initialized)
    signal(engine, flag["id"], "notified")
    flag = initialized.get(f"/flags/{flag['id']}").json()
    assert action(initialized, flag, "acknowledge").status_code == 200
    later = SENT + timedelta(days=3)
    assert escalate(initialized, iso(later))["escalated_flag_ids"] == []


def test_notified_flag_escalates_and_escalation_delivery_does_not_notify(initialized, engine):
    ingest(initialized)
    flag = drywall_f3(initialized)
    escalate(initialized, iso(SENT + timedelta(hours=5)))
    with Session(engine) as session, session.begin():
        for message in session.scalars(select(models.OutboxMessage)):
            message.available_at = datetime.now(UTC) - timedelta(seconds=1)
            if message.kind == "warning":
                message.available_at = datetime.now(UTC) + timedelta(days=1)
    claimed = initialized.post("/outbox/claim").json()
    assert claimed["kind"] == "escalation"
    response = initialized.post(f"/outbox/{claimed['id']}/result", json={
        "lease_token": claimed["lease_token"], "status": "sent", "provider_message_id": "gmail-test"})
    assert response.status_code == 200, response.text
    # The responsible Crew Lead has not been notified; the Flag stays detected.
    assert drywall_f3(initialized)["state"] == "detected"


def test_escalation_threshold_is_configurable(initialized, engine, monkeypatch):
    monkeypatch.setenv("ESCALATION_HOURS", "0.5")
    ingest(initialized)
    flag = drywall_f3(initialized)
    assert escalate(initialized, iso(SENT + timedelta(minutes=30)))["escalated_flag_ids"] == [flag["id"]]


def test_closed_flags_never_escalate(initialized, engine):
    ingest(initialized)
    flag = drywall_f3(initialized)
    close(initialized, engine, flag)
    later = SENT + timedelta(days=3)
    assert escalate(initialized, iso(later))["escalated_flag_ids"] == []


def test_escalation_runs_on_the_trigger_clock_not_the_wall_clock(initialized, engine):
    # Replay (#22) run long after the simulated timeline: real creation is later.
    ingest(initialized)
    flag = drywall_f3(initialized)
    with Session(engine) as session, session.begin():
        session.get(models.Flag, flag["id"]).created_at = datetime(2027, 6, 1, tzinfo=UTC)
    assert escalate(initialized, iso(SENT + timedelta(hours=3, minutes=59)))["escalated_flag_ids"] == []
    assert escalate(initialized, iso(SENT + timedelta(hours=4)))["escalated_flag_ids"] == [flag["id"]]


def test_scan_flags_escalate_from_the_scan_time(initialized):
    created = scan(initialized)["created_flag_ids"]
    morning = datetime(2026, 11, 14, 5, tzinfo=UTC)
    assert escalate(initialized, iso(morning + timedelta(hours=3, minutes=59)))["escalated_flag_ids"] == []
    assert sorted(escalate(initialized, iso(morning + timedelta(hours=4)))["escalated_flag_ids"]) == sorted(created)


def test_job_schedule_runs_scan_once_per_local_day():
    schedule = JobSchedule(parse_scan_time("06:00"), 300)
    tz = "Europe/Vienna"
    assert not schedule.scan_due(datetime(2026, 11, 14, 4, 59, tzinfo=UTC), tz)  # 05:59 local
    due = datetime(2026, 11, 14, 5, 0, tzinfo=UTC)
    assert schedule.scan_due(due, tz)
    schedule.mark_scanned(due, tz)
    assert not schedule.scan_due(due + timedelta(hours=12), tz)
    assert schedule.scan_due(due + timedelta(days=1), tz)


def test_job_schedule_escalation_interval():
    schedule = JobSchedule(time(6), 300)
    now = datetime(2026, 11, 14, 8, tzinfo=UTC)
    assert schedule.escalation_due(now)
    schedule.mark_escalation(now)
    assert not schedule.escalation_due(now + timedelta(seconds=299))
    assert schedule.escalation_due(now + timedelta(seconds=300))


@pytest.mark.parametrize("value", ["6", "25:00", "aa:bb"])
def test_invalid_scan_time_is_rejected(value):
    with pytest.raises(ValueError):
        parse_scan_time(value)


def test_worker_jobs_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("MORNING_SCAN_TIME", "off")
    monkeypatch.setenv("ESCALATION_CHECK_SECONDS", "0")
    api = MagicMock()
    assert run_due_jobs(JobSchedule.from_env(), api, datetime(2026, 11, 14, 12, tzinfo=UTC)) == []
    assert not api.get.called and not api.post.called
    # Scan off alone: the escalation timer keeps running.
    api.get.return_value.json.return_value = {"timezone": "Europe/Vienna"}
    monkeypatch.setenv("ESCALATION_CHECK_SECONDS", "300")
    assert run_due_jobs(JobSchedule.from_env(), api, datetime(2026, 11, 14, 12, tzinfo=UTC)) == ["escalation"]
    monkeypatch.setenv("ESCALATION_CHECK_SECONDS", "-1")
    with pytest.raises(ValueError):
        JobSchedule.from_env()


def test_worker_triggers_due_jobs_via_rest_only():
    api = MagicMock()
    api.get.return_value.json.return_value = {"timezone": "Europe/Vienna"}
    schedule = JobSchedule(time(6), 300)
    now = datetime(2026, 11, 14, 5, 30, tzinfo=UTC)
    assert run_due_jobs(schedule, api, now) == ["morning_scan", "escalation"]
    assert [call.args[0] for call in api.post.call_args_list] == ["/jobs/morning-scan", "/jobs/escalation"]
    assert run_due_jobs(schedule, api, now + timedelta(seconds=10)) == []
    api.get.return_value.json.return_value = None
    assert run_due_jobs(JobSchedule(time(6), 300), api, now) == []


def test_escalation_migration_round_trips(engine):
    config = Config(str(BACKEND / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0010")
        assert "kind" not in {column["name"] for column in inspect(connection).get_columns("outbox_messages")}
        command.upgrade(config, "head")
        assert "kind" in {column["name"] for column in inspect(connection).get_columns("outbox_messages")}
