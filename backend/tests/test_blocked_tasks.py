from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as Row

from sqlalchemy.orm import Session

from app import models, rules
from app.blocked_tasks import detect_blocked_tasks
from test_rules import initialized, ingest  # noqa: F401

NOW = datetime(2026, 11, 14, tzinfo=UTC)


def task(id, zone="3B", after=(), days=1):
    return Row(id=id, zone_id=zone, predecessor_ids=list(after), starts_at=NOW,
               ends_at=NOW + timedelta(days=days))


def test_zone_descendants_matched_parent_task_and_transitive_successors_with_cycles():
    flag = Row(zone_id="3B", task_id="floor-task", state="detected", evaluation="unknown")
    zones = [Row(id="F3", parent_id=None), Row(id="3B", parent_id="F3"),
             Row(id="bath", parent_id="3B"), Row(id="3A", parent_id="F3")]
    tasks = [task("floor-task", "F3"), task("room", "bath", ["last"]),
             task("successor", "3A", ["room"]), task("last", "3A", ["successor"]),
             task("sibling", "3A"), task("other-floor", "F4"), task("past", days=-1)]
    assert {item.id for item in detect_blocked_tasks(flag, tasks, zones, NOW)} == {
        "floor-task", "room", "successor", "last"}
    flag.task_id = None
    assert "floor-task" not in {item.id for item in detect_blocked_tasks(flag, tasks, zones, NOW)}
    flag.evaluation = "satisfied"
    assert detect_blocked_tasks(flag, tasks, zones, NOW) == []
    flag.evaluation, flag.state = "unknown", "resolved"
    assert detect_blocked_tasks(flag, tasks, zones, NOW) == []


def add_successor(engine):
    with Session(engine) as session, session.begin():
        predecessor = session.get(models.Task, "drywall-F3")
        session.add(models.Task(id="finish-3A", name="Finishing after drywall", zone_id="3A", crew_id="insulation",
            starts_at=predecessor.ends_at, ends_at=predecessor.ends_at + timedelta(days=1), predecessors=[predecessor]))


def test_hero_successor_notices_are_factual_deduplicated_and_audited(initialized, engine, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CREW_GROUPS_JSON", '{"drywall":"-123", "insulation":"-456"}')
    add_successor(engine)
    ingest(initialized)
    flag = initialized.get("/flags").json()[0]
    assert {item["id"] for item in flag["blocked_tasks"]} == {"drywall-F3", "finish-3A"}
    messages = initialized.get("/outbox").json()
    assert len(messages) == 4  # one lead and one group per Crew
    assert {item["recipient"] for item in messages if item["channel"] == "telegram"} == {"-123", "-456"}
    for item in messages:
        assert "Check with the Superintendent before starting" in item["content"]
        assert "source:" in item["content"]
        assert "on hold" not in item["content"].lower()
        assert "do not continue" not in item["content"].lower()
    assert len([row for row in flag["audit"] if row["action"] == "blocked_notice_queued"]) == 3
    ingest(initialized, external_id="repeat-work")
    with Session(engine) as session, session.begin():
        rules.evaluate_site(session)
    assert initialized.get("/outbox").json() == messages


def test_updated_flag_notifies_newly_affected_crew_once(initialized, engine):
    ingest(initialized)
    add_successor(engine)
    with Session(engine) as session, session.begin():
        rules.evaluate_site(session)
    assert len(initialized.get("/outbox").json()) == 2
    with Session(engine) as session, session.begin():
        rules.evaluate_site(session)
    assert len(initialized.get("/outbox").json()) == 2


def test_positive_group_contact_is_never_used(initialized, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CREW_GROUPS_JSON", '{"drywall":"123"}')
    ingest(initialized)
    assert len(initialized.get("/outbox").json()) == 1


def test_hold_proposal_requires_its_own_superintendent_approval(initialized, engine, monkeypatch):
    from test_proposals import acknowledged, advise, decide
    from app.blocked_tasks import HOLD_ACTION, HOLD_MESSAGE

    monkeypatch.setenv("TELEGRAM_CREW_GROUPS_JSON", '{"drywall":"-123", "insulation":"-456"}')
    add_successor(engine)
    ingest(initialized)
    flag = initialized.get("/flags").json()[0]
    advice = advise(initialized, flag).json()
    hold = next(item for item in advice["proposals"] if item["action"] == HOLD_ACTION)
    assert hold["message"] == HOLD_MESSAGE
    assert set(hold["affected_tasks"]) == {"drywall-F3", "finish-3A"}
    assert set(hold["affected_crews"]) == {"drywall", "insulation"}
    assert not any(row["kind"] == "proposal_followup" for row in initialized.get("/outbox").json())
    assert decide(initialized, hold["id"], "approved").status_code == 409
    flag = acknowledged(initialized, engine, flag)
    assert decide(initialized, hold["id"], "approved", role="crew_lead", actor="lead-drywall").status_code == 403
    # Approving a different measure cannot send the hold instruction.
    ordinary = advice["proposals"][0]
    assert decide(initialized, ordinary["id"], "approved").status_code == 200
    assert not any(HOLD_MESSAGE in row["content"] for row in initialized.get("/outbox").json()
                   if row["kind"] == "proposal_followup")
    assert decide(initialized, hold["id"], "approved").status_code == 200
    notices = [row for row in initialized.get("/outbox").json()
               if row["kind"] == "proposal_followup" and HOLD_MESSAGE in row["content"]]
    assert len(notices) == 4
    assert {row["recipient"] for row in notices if row["channel"] == "telegram"} == {"-123", "-456"}
    assert decide(initialized, hold["id"], "approved").status_code == 409
    updated = initialized.get(f"/flags/{flag['id']}").json()
    assert updated["state"] == "in_progress" and updated["evaluation"] == "unknown"


def test_rejected_hold_proposal_sends_no_instruction(initialized, engine):
    from test_proposals import advise, decide
    from app.blocked_tasks import HOLD_ACTION

    ingest(initialized)
    flag = initialized.get("/flags").json()[0]
    hold = next(item for item in advise(initialized, flag).json()["proposals"] if item["action"] == HOLD_ACTION)
    assert decide(initialized, hold["id"], "rejected").status_code == 200
    assert not any(row["kind"] == "proposal_followup" for row in initialized.get("/outbox").json())
