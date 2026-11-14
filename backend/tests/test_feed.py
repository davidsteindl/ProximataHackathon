"""Activity feed (#37): ordering, Zone/time filtering, paging and evidence labelling."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.lifecycle import transition_flag
from test_cad_pipeline import ENTRIES, upload
from test_lifecycle import action, decision, signal
from test_plan_diff import hero_payload
from test_rules import ingest, initialized  # noqa: F401


def feed(client, **params):
    response = client.get("/feed", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def titles(page):
    return [entry["title"] for entry in page["entries"]]


def flag_of(client, kind, **context):
    return next(flag for flag in client.get("/flags").json() if flag["type"] == kind
                and all(flag["context"].get(key) == value for key, value in context.items()))


def approve(engine, flag_id):
    """#13 calls this after its human approval validation; it is not a public endpoint yet."""
    with Session(engine) as session, session.begin():
        flag = session.get(models.Flag, flag_id)
        transition_flag(session, flag, action="action_approved", actor="synthetic-superintendent",
                        actor_type="human", role="superintendent", channel="dashboard",
                        source_ref="proposal:synthetic", feedback=None)


def hero_days_one_and_two(client, engine):
    assert upload(client, ENTRIES[2]).status_code == 200
    assert client.post("/ingestion/messages", json=hero_payload()).json()["source"]["status"] == "processed"
    plumbing = flag_of(client, "B", crew_id="plumbing")
    signal(engine, plumbing["id"], "notified")
    plumbing = client.get(f"/flags/{plumbing['id']}").json()
    assert action(client, plumbing, "acknowledge", actor="lead-plumbing", role="crew_lead",
                  reason="Warnung gesehen").status_code == 200
    ingest(client, external_id="postponed", sender_role="inspector", sender_crew_id=None,
           sent_at="2026-11-14T16:40:00+01:00", text="Abnahme der Rohinstallation im 3. OG auf Tag 4 verschoben.")
    ingest(client, external_id="closing", sent_at="2026-11-14T18:05:00+01:00")
    flag_a = flag_of(client, "A")
    signal(engine, flag_a["id"], "notified")
    assert action(client, client.get(f"/flags/{flag_a['id']}").json(), "acknowledge",
                  reason="Seen").status_code == 200
    proposal = client.post("/agent/proposals", headers={"X-SiteMind-Client": "mcp"}, json={
        "flag_id": flag_a["id"], "action": "Trockenbau 3B verschieben, Crew auf 3A/3C umplanen",
        "rationale": "Inspection not proven and Rev D not acknowledged.",
    })
    assert proposal.status_code == 201
    approve(engine, flag_a["id"])
    return plumbing, flag_a


def test_hero_days_one_and_two_read_as_a_feed(initialized, engine):
    plumbing, flag_a = hero_days_one_and_two(initialized, engine)
    page = feed(initialized, limit=200)
    entries = page["entries"]
    keys = [entry["recorded_at"] for entry in entries]
    assert keys == sorted(keys, reverse=True)
    headline = titles(page)

    def first(predicate):
        return next(index for index, entry in enumerate(entries) if predicate(entry))

    rev_d = first(lambda e: e["title"].startswith("Rev D received for A-103"))
    flag_b = first(lambda e: e["flag_id"] == plumbing["id"] and e["title"].startswith("Flag B raised"))
    acknowledged = first(lambda e: e["flag_id"] == plumbing["id"] and "acknowledged" in e["title"])
    postponed = first(lambda e: e["title"].startswith("Inspection rough in postponed"))
    raised_a = first(lambda e: e["flag_id"] == flag_a["id"] and e["title"].startswith("Flag A raised"))
    approved = first(lambda e: e["flag_id"] == flag_a["id"] and "action approved" in e["title"])
    proposed = first(lambda e: e["kind"] == "proposal")
    # Most recently recorded first: Rev D is the oldest of these, the approval the newest.
    assert rev_d > flag_b > postponed > raised_a
    assert acknowledged < flag_b and approved < raised_a and proposed < raised_a
    assert entries[rev_d]["confirmation"] == "deterministic"
    assert "Does not confirm crew receipt" in entries[rev_d]["summary"]
    assert entries[postponed]["confirmation"] == "unconfirmed" and "(unconfirmed)" in headline[postponed]
    assert entries[acknowledged]["confirmation"] == "human"
    assert "not evidence of receipt" in entries[acknowledged]["summary"]
    assert entries[flag_b]["link"] == f"/flags/{plumbing['id']}"
    assert entries[rev_d]["link"] == "/zones/3B"
    assert entries[proposed]["confirmation"] == "advice"
    # The Rev D event covers its Revision record; only seed revisions appear on their own.
    assert not any(entry["id"] == "revision:A-103-D" for entry in entries)
    assert any(entry["id"] == "revision:A-103-C" and entry["confirmation"] == "seed" for entry in entries)


def test_entries_are_about_zones_and_crews_never_people(initialized, engine):
    hero_days_one_and_two(initialized, engine)
    people = {"lead-plumbing", "lead-drywall", "synthetic-superintendent"}
    leads = {crew["lead"]["name"] for crew in initialized.get("/crews").json()}
    for entry in feed(initialized, limit=200)["entries"]:
        text = " ".join(str(value) for value in entry.values())
        assert not any(person in text for person in people | leads), entry
        assert entry["actor_role"] in {None, "system", "agent", "superintendent", "crew_lead",
                                       "architect", "inspector", "crew", "unknown"}


def test_zone_filter_includes_descendants_and_time_range(initialized, engine):
    hero_days_one_and_two(initialized, engine)
    floor = feed(initialized, zone_id="F3", limit=200)["entries"]
    unit = feed(initialized, zone_id="3B", limit=200)["entries"]
    assert unit and {entry["id"] for entry in unit} <= {entry["id"] for entry in floor}
    assert all(set(entry["zone_ids"]) & ({"3B"} | {z for z in entry["zone_ids"] if z.startswith("3B-")})
               for entry in unit)
    # The floor-level inspection notice is not inside unit 3B; ancestors are not included.
    assert any(entry["title"].startswith("Inspection rough in postponed") for entry in floor)
    assert not any(entry["title"].startswith("Inspection rough in postponed") for entry in unit)
    assert not any("F1" in entry["zone_ids"] for entry in floor)
    assert feed(initialized, zone_id="3B", include_descendants=False, limit=200)["entries"]
    assert initialized.get("/feed", params={"zone_id": "nowhere"}).status_code == 404

    day_two = feed(initialized, from_time="2026-11-14T00:00:00Z", to_time="2026-11-14T17:30:00Z", limit=200)
    assert day_two["entries"]
    assert all("2026-11-14T00:00:00Z" <= entry["occurred_at"] < "2026-11-14T17:30:00Z" for entry in day_two["entries"])
    assert any(entry["title"].startswith("Inspection rough in postponed") for entry in day_two["entries"])
    assert initialized.get("/feed", params={"from_time": "2026-11-15T00:00:00Z",
                                            "to_time": "2026-11-14T00:00:00Z"}).status_code == 422


def test_cursor_pagination_is_stable_and_complete(initialized, engine):
    hero_days_one_and_two(initialized, engine)
    everything = [entry["id"] for entry in feed(initialized, limit=200)["entries"]]
    seen, cursor = [], None
    while True:
        page = feed(initialized, limit=3, **({"cursor": cursor} if cursor else {}))
        seen += [entry["id"] for entry in page["entries"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
        # A new entry arriving between pages must not shift or repeat older pages.
        ingest(initialized, external_id=f"later-{len(seen)}", text="Warnung gesehen",
               sent_at="2026-11-20T08:00:00+01:00")
    assert seen == everything
    assert len(seen) == len(set(seen))
    assert initialized.get("/feed", params={"cursor": "not-a-cursor"}).status_code == 422
    assert initialized.get("/feed", params={"limit": 0}).status_code == 422


def completion(engine, *, claim="completed", task_id="plumbing-F3", zone_id="F3"):
    """A source-backed completion statement, stored as ingestion would."""
    with Session(engine) as session, session.begin():
        source = models.SourceMessage(
            id="done-source", site_id=session.scalars(select(models.Site)).one().id,
            channel="telegram", source_key="crew", external_id="done", payload_hash="0" * 64,
            sender_role="crew_lead", sender_crew_id="plumbing", text="Rohinstallation F3 fertig",
            status="processed", sent_at=datetime(2026, 11, 13, 14, tzinfo=UTC), received_at=datetime.now(UTC),
        )
        event = models.Event(
            id="done-event", source_message_id=source.id, ordinal=0, intent="task_completion",
            crew_id="plumbing", quote=source.text, confidence=0.97, time_precision="unspecified",
            unresolved_zones=[], details={"claim": claim, "task_reference": task_id},
            created_at=datetime.now(UTC), zones=[session.get(models.Zone, zone_id)],
        )
        evidence = models.Evidence(
            id="done-evidence", origin="llm_statement", statement_ref=event.id,
            source_ref=f"source:{source.id}", quote=source.text, kind="task_completion", claim=claim,
            zone_id=zone_id, task_id=task_id,
            history=[models.EvidenceReview(sequence=1, status="unconfirmed", actor_type="statement_ingestion",
                                           recorded_at=datetime.now(UTC))],
        )
        session.add_all([source, event, evidence])
    return "done-evidence"


def test_task_is_completed_only_with_confirmed_evidence(initialized, engine):
    evidence_id = completion(engine)

    claimed = feed(initialized)["entries"]
    reported = next(entry for entry in claimed if entry["id"] == "event:done-event")
    assert reported["title"] == "Completion of Rough-in plumbing F3 reported (unconfirmed)"
    assert reported["confirmation"] == "unconfirmed"
    assert reported["task_id"] == "plumbing-F3"
    assert not any(entry["kind"] == "task_completed" for entry in claimed)

    assert decision(initialized, evidence_id, "confirmed").status_code == 200
    confirmed = feed(initialized)["entries"]
    done = [entry for entry in confirmed if entry["kind"] == "task_completed"]
    assert [entry["title"] for entry in done] == ["Rough-in plumbing F3 completed"]
    assert done[0]["confirmation"] == "confirmed" and done[0]["actor_role"] == "superintendent"
    assert done[0]["link"] == "/zones/F3"
    assert next(entry for entry in confirmed if entry["id"] == "event:done-event")["confirmation"] == "confirmed"

    assert decision(initialized, evidence_id, "rejected", reason="Wrong floor").status_code == 200
    rejected = feed(initialized)["entries"]
    assert not any(entry["kind"] == "task_completed" for entry in rejected)
    decisions = [entry for entry in rejected if entry["evidence_id"] == evidence_id]
    assert [entry["confirmation"] for entry in decisions] == ["rejected", "confirmed"]
    assert "Later rejected." in decisions[1]["summary"]
    assert "Wrong floor" in decisions[0]["summary"]


def test_not_completed_claim_never_reads_as_completion(initialized, engine):
    evidence_id = completion(engine, claim="not_completed")
    assert decision(initialized, evidence_id, "confirmed").status_code == 200
    entries = feed(initialized)["entries"]
    assert not any(entry["kind"] == "task_completed" for entry in entries)
    assert next(entry for entry in entries if entry["id"] == "event:done-event")["title"] == \
        "Rough-in plumbing F3 reported not completed"


def test_kind_filter(initialized):
    assert feed(initialized, kind="flag_change")["entries"] == []
    revisions = feed(initialized, kind="revision")["entries"]
    assert revisions and all(entry["kind"] == "revision" for entry in revisions)
