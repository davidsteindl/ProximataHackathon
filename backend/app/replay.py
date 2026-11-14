"""Guided hero replay. Only REST writes; human decisions are never submitted here."""

import argparse
import base64
import json
import math
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ingestion_schemas import SenderRole, SourceMessageInput
from app.seed import load_seed

BACKEND = Path(__file__).resolve().parents[1]
DECISIONS = {"acknowledge_b", "approve_a", "resolve_a", "correct_false_alarm",
             "confirm_inspection", "confirm_revision", "resolve_after_confirmation"}


class ReplayError(Exception):
    pass


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    day: int = Field(ge=1, le=30)
    time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    decision: str | None = None
    channel: str | None = None
    sender_role: SenderRole | None = None
    sender_crew_id: str | None = None
    text: str | None = None
    subject: str | None = None
    attachment: str | None = None

    @model_validator(mode="after")
    def valid_step(self):
        if self.decision:
            if self.decision not in DECISIONS or self.text is not None:
                raise ValueError("Unknown or ambiguous human decision")
        elif self.channel not in {"gmail", "telegram"} or not self.sender_role or not self.text:
            raise ValueError("Message steps need channel, role and text")
        if self.attachment and Path(self.attachment).name != self.attachment:
            raise ValueError("Attachment must be a file name")
        return self

    @property
    def source_text(self):
        return f"Subject: {self.subject}\n\n{self.text}" if self.subject else self.text


class Scenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1, le=1)
    name: str
    steps: list[Step] = Field(min_length=1)

    @model_validator(mode="after")
    def ordered_steps(self):
        if len({step.id for step in self.steps}) != len(self.steps):
            raise ValueError("Step IDs must be unique")
        clocks = [(step.day, step.time) for step in self.steps]
        if clocks != sorted(clocks):
            raise ValueError("Scenario steps must follow the simulated clock")
        return self


def request(api, method, path, **kwargs):
    response = getattr(api, method)(path, **kwargs)
    if response.is_error:
        raise ReplayError(f"{method.upper()} {path}: HTTP {response.status_code}")
    return response.json()


class ScenarioClock:
    def __init__(self, site, speed, sleep=time.sleep):
        if not math.isfinite(speed) or speed <= 0:
            raise ReplayError("Speed must be a finite number greater than zero")
        self.site, self.speed, self.sleep, self.current = site, speed, sleep, None

    def timestamp(self, step):
        day = self.site.start_date + timedelta(days=step.day - 1)
        return datetime.combine(day, datetime.strptime(step.time, "%H:%M").time(), ZoneInfo(self.site.timezone))

    def advance(self, step):
        target = self.timestamp(step)
        if self.current is not None:
            delay = (target - self.current).total_seconds() / self.speed
            # Keep interruptible even with deliberately slow pacing.
            while delay > 0:
                chunk = min(delay, 1)
                self.sleep(chunk)
                delay -= chunk
        self.current = target
        return target


class Transcript:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path

    def __call__(self, kind, **record):
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps({"kind": kind, **record}, ensure_ascii=False, default=str) + "\n")


class OfflineChannels:
    """Synthetic messages and local-file delivery, never provider clients."""
    def __init__(self, api, run_id, plans, log):
        self.api, self.run_id, self.plans, self.log = api, run_id, plans, log

    def receive(self, step, sent_at):
        attachments = []
        if step.attachment:
            attachments.append({"file_name": step.attachment, "media_type": "image/vnd.dxf",
                "content_base64": base64.b64encode((self.plans / step.attachment).read_bytes()).decode()})
        payload = SourceMessageInput(channel="replay", source_key=f"hero:{self.run_id}", external_id=step.id,
            sender_id=f"synthetic-{step.sender_role}", sender_role=step.sender_role,
            sender_crew_id=step.sender_crew_id, sent_at=sent_at, text=step.source_text, attachments=attachments)
        return request(self.api, "post", "/ingestion/messages", json=payload.model_dump(mode="json"))

    def deliver(self):
        for channel in ("gmail", "telegram"):
            for _ in range(200):
                message = request(self.api, "post", "/outbox/claim", params={"channel": channel})
                if message is None:
                    break
                # Write before reporting success; a failed file write is not a delivery.
                self.log("synthetic_delivery", message=message)
                request(self.api, "post", f"/outbox/{message['id']}/result", json={
                    "lease_token": message["lease_token"], "status": "sent",
                    "provider_message_id": f"synthetic-replay:{self.run_id}:{message['id']}",
                })
            else:
                raise ReplayError("Unexpectedly large outbox; stopped synthetic delivery")


class Replay:
    def __init__(self, api, scenario, plans, channels, *, speed=3600, pause=input, output=print,
                 log=lambda *args, **kwargs: None, sleep=time.sleep, seed_directory=BACKEND / "seed"):
        self.api, self.scenario, self.plans, self.channels = api, scenario, plans, channels
        self.pause, self.output, self.log = pause, output, log
        self.seed = load_seed(seed_directory)
        self.clock = ScenarioClock(self.seed.site, speed, sleep)
        self.results, self.flags = {}, {}

    def get(self, path, **kwargs):
        return request(self.api, "get", path, **kwargs)

    def flag(self, key):
        return self.get(f"/flags/{self.flags[key]}")

    def require(self, condition, message):
        if not condition:
            raise ReplayError(message)

    def reset(self):
        config = self.get("/replay/config")
        self.require(config["offline_ready"], "Hero replay requires LLM_PROVIDER=cached in the API (also for the intentional learning error)")
        # Check every required local input before replacing data.
        required = {revision.file_name for revision in self.seed.revisions}
        required.update(step.attachment for step in self.scenario.steps if step.attachment)
        for name in required:
            self.require((self.plans / name).is_file(), f"Missing DXF fixture: {name}")
        request(self.api, "post", "/seed/import", json=self.seed.model_dump(mode="json"))
        for revision in self.seed.revisions:
            plan = next(plan for plan in self.seed.plans if plan.id == revision.plan_id)
            with (self.plans / revision.file_name).open("rb") as drawing:
                request(self.api, "post", "/geometry/import", data={
                    "plan_id": plan.id, "floor_id": plan.floor_id, "revision_id": revision.id,
                    "label": revision.label, "sequence": revision.sequence, "issued_at": revision.issued_at.isoformat(),
                }, files={"file": (revision.file_name, drawing, "image/vnd.dxf")})
        evidence = self.get("/evidence")
        self.require(all(item["origin"] == "seed_baseline" and item["history"][0]["actor_type"] == "seed_import"
                         and item["import_ref"] for item in evidence if item["review_status"] == "confirmed"),
                     "Reset lost synthetic baseline provenance")
        self.require(not self.get("/flags") and not self.get("/site-knowledge"), "Reset did not clear demo state")
        self.results.clear()
        self.flags.clear()
        self.clock.current = None
        self.log("reset", site_id=self.seed.site.id, evidence_ids=[item["id"] for item in evidence])

    def service(self):
        for flag in self.get("/flags"):
            if (flag["type"] == "A" and flag["zone_id"] == "3B"
                    and flag["task_id"] == "drywall-F3" and flag["advice"] is None):
                request(self.api, "post", f"/flags/{flag['id']}/advice")
        self.deliver()

    def deliver(self):
        # A transient send failure must not throw away a guided run that has no resume.
        while True:
            try:
                return self.channels.deliver()
            except ReplayError as error:
                self.output(f"Delivery not complete: {error}")
                if self.pause("Fix delivery, wait for the backoff, then Enter to retry (q to stop): ").strip().lower() == "q":
                    raise

    def remember_flag(self, key, step, kind, crew=None):
        source_id = self.results[step]["source"]["id"]
        flags = [flag for flag in self.get("/flags") if flag["type"] == kind and flag["zone_id"] == "3B"
                 and any(event["source_message_id"] == source_id for event in flag["sources"])
                 and (crew is None or flag["context"].get("crew_id") == crew)]
        self.require(len(flags) == 1, f"Expected one open Flag {kind} for {step}")
        self.flags[key] = flags[0]["id"]
        self.require(flags[0]["state"] == "notified", f"Flag {kind} warning has not been delivered")
        self.output(f"Flag {kind}: {flags[0]['id']} ({flags[0]['evaluation']}); notification delivered")

    def evidence_for(self, step):
        return [item for event in self.results[step]["events"] for item in event["evidence"]]

    def check_message(self, step):
        result = self.results[step.id]
        self.require(result["source"]["status"] == "processed", f"Source failed at {step.id}")
        self.require(all(item["review_status"] == "unconfirmed" for item in self.evidence_for(step.id)),
                     "Replay statement unexpectedly confirmed Evidence")
        if step.id == "revision":
            self.require(any(event["details"].get("diff_status") == "succeeded" and event["zone_ids"] == ["3B"]
                             for event in result["events"]), "Expected deterministic Rev C to Rev D diff for 3B")
            self.remember_flag("b", step.id, "B", "plumbing")
        elif step.id == "warning_seen":
            self.require(not self.evidence_for(step.id) and self.flag("b")["state"] == "notified",
                         "Warning seen must not acknowledge a Flag or plan revision automatically")
        elif step.id in {"postponed", "ambiguous"}:
            self.require(self.evidence_for(step.id), "Expected an unconfirmed inspection claim")
        elif step.id in {"closing", "learning_before", "genuine_after_learning"}:
            key = {"closing": "a", "learning_before": "false_alarm", "genuine_after_learning": "genuine"}[step.id]
            self.remember_flag(key, step.id, "A")
            self.require(self.flag(key)["evaluation"] != "satisfied", "Unconfirmed claims suppressed the necessary Flag")
            if step.id == "closing":
                self.require(self.flag(key)["severity"] == "high", "Hero Flag A must be critical")
                self.require(self.flag("b")["evaluation"] != "satisfied", "Warning seen was counted as Rev D receipt")
        elif step.id == "learning_after":
            original = self.results["learning_before"]["events"][0]
            event = result["events"][0]
            learning = event["details"].get("learning", {})
            self.require(event["intent"] == "question" and learning.get("event_id") == original["id"]
                         and learning.get("feedback_id") and learning.get("knowledge_id"),
                         "Learning replay did not expose the correction and source/feedback references")
            self.require(not any(flag["type"] == "A" and flag["zone_id"] == "3B" for flag in self.get("/flags")),
                         "Learned question raised another work Flag")
        elif step.id in {"concrete_result", "revision_receipt"}:
            self.require(self.evidence_for(step.id), "Expected source-backed unconfirmed Evidence")
            key = "genuine" if step.id == "concrete_result" else "b"
            self.require(self.flag(key)["evaluation"] != "satisfied", "Extraction bypassed human confirmation")
        elif step.id in {"plan_question", "room_question"}:
            self.require(result["events"] and all(event["intent"] == "question" for event in result["events"]),
                         "Crew question was not extracted as a question")
            context = self.get("/context/zones/3B-BATH")
            self.output("Read-only record context (Telegram Q&A delivery belongs to #20): " +
                        json.dumps({key: context[key] for key in ("zone", "preconditions", "source_refs")}, ensure_ascii=False))

    def decision(self, step):
        name = step.decision
        key = {"acknowledge_b": "b", "approve_a": "a", "resolve_a": "a", "correct_false_alarm": "false_alarm",
               "confirm_inspection": "genuine", "confirm_revision": "b", "resolve_after_confirmation": "genuine"}[name]
        flag = self.flag(key)
        before_state = flag["state"]
        instructions = {
            "acknowledge_b": "As Plumbing Crew Lead or Superintendent, acknowledge Flag B with reason 'Warnung gesehen'. This does not confirm Rev D receipt.",
            "approve_a": "As Superintendent, acknowledge Flag A, then separately approve the postpone-3B / move-to-3A-or-3C Proposal. Do not confirm Evidence or close the Flag.",
            "resolve_a": "As Superintendent, close Flag A as resolved, reason 'Trockenbau verschoben'. No inspection confirmation is implied.",
            "correct_false_alarm": "As Superintendent, close the question's Flag as false alarm, reason 'A question, not an announcement', explicitly selecting its planned-work Event as the extraction correction.",
            "confirm_inspection": "As Superintendent, review the concrete day-4 inspection source and confirm only that exact Evidence for rough-in-F3. Review and reject the contradictory negative synthetic seed example (example-contradictory-negative). Leave this Flag open.",
            "confirm_revision": "As Superintendent or Plumbing Crew Lead, confirm only the source-backed Plumbing receipt of A-103-D for 3B. This proves receipt, not implementation. Leave Flag B open.",
            "resolve_after_confirmation": "As Superintendent, acknowledge the remaining Flag A, separately approve its Proposal, then separately close it as resolved with a reason. Evidence confirmation alone did not close it.",
        }
        self.output(f"DASHBOARD: /flags/{flag['id']}\n{instructions[name]}")
        for source_step in ({"confirm_inspection": ["concrete_result"], "confirm_revision": ["revision_receipt"]}.get(name, [])):
            self.output("Review Evidence: " + ", ".join(item["id"] for item in self.evidence_for(source_step)))
        while True:
            answer = self.pause("Complete the documented dashboard decisions, then Enter to verify (q to stop): ")
            if answer.strip().lower() == "q":
                raise ReplayError("Stopped at a human checkpoint; state preserved")
            self.deliver()
            current = self.flag(key)
            if name in {"confirm_inspection", "confirm_revision"}:
                source_step = "concrete_result" if name == "confirm_inspection" else "revision_receipt"
                targets = {item["id"] for item in self.evidence_for(source_step)}
                records = {item["id"]: item for item in self.get("/evidence")}
                exact_confirmed = targets and all(records[identifier]["review_status"] == "confirmed"
                    and records[identifier]["history"][-1]["actor_type"] == "human" for identifier in targets)
                ok = exact_confirmed and current["evaluation"] == "satisfied" and current["state"] == before_state
            else:
                desired = {"acknowledge_b": "acknowledged", "approve_a": "in_progress", "resolve_a": "resolved",
                           "correct_false_alarm": "false_alarm", "resolve_after_confirmation": "resolved"}[name]
                ok = current["state"] == desired
                if name == "correct_false_alarm":
                    ok = ok and any(item["flag_id"] == flag["id"] and item["correction_event_id"]
                                    == self.results["learning_before"]["events"][0]["id"] for item in self.get("/site-knowledge"))
            if ok:
                self.log("human_checkpoint", step=step.id, flag_id=current["id"], state=current["state"], evaluation=current["evaluation"])
                break
            self.output("Expected dashboard decision is not recorded yet. Inspect the source, scope and Flag state; no action was submitted by replay.")
        if name in {"approve_a", "resolve_a"}:
            self.require(not any(item["origin"] == "llm_statement" and item["review_status"] == "confirmed"
                                 for item in self.get("/evidence")), "Approval/closure unexpectedly confirmed Evidence")
        if name in {"approve_a", "resolve_after_confirmation"}:
            self.require(any(item["kind"] == "proposal_followup" and item["status"] == "sent"
                             for item in current["notifications"]), "Approved measure follow-up not delivered")

    def run(self):
        self.reset()
        self.output("Seed reset complete. Simulated times follow the Site timezone; all new claims stay unconfirmed.")
        for step in self.scenario.steps:
            timestamp = self.clock.advance(step)
            self.output(f"\nDay {step.day} {step.time} ({timestamp.isoformat()}): {step.id}")
            if step.decision:
                self.decision(step)
            else:
                result = self.channels.receive(step, timestamp)
                self.results[step.id] = result
                self.log("ingestion", step=step.id, source=result["source"], events=result["events"])
                self.service()
                self.check_message(step)
        self.log("complete", flag_ids=self.flags, telegram_answers_verified=False)
        self.output("Hero inputs and dashboard decisions replayed. Telegram answers require #20; the record snapshots above are not chat replies. Deliveries are recorded in the transcript.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("offline", "online"), default="offline")
    parser.add_argument("--api", default=os.environ.get("API_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--scenario", type=Path, default=BACKEND / "demo/hero-scenario.json")
    parser.add_argument("--plans", type=Path, default=Path("/cad/plans") if Path("/cad/plans").exists() else BACKEND.parent / "cad/plans")
    parser.add_argument("--speed", type=float, default=3600, help="Simulated seconds per real second; human pauses are not accelerated")
    parser.add_argument("--reset-only", action="store_true", help="Restore seed and Rev C geometry without playing messages")
    parser.add_argument("--output", type=Path, default=None, help="JSONL transcript, including explicit local mock deliveries")
    parser.add_argument("--timeout", type=float, default=180, help="Seconds to wait for each online test message")
    args = parser.parse_args()
    try:
        scenario = Scenario.model_validate_json(args.scenario.read_text(encoding="utf-8"))
        run_id = uuid4().hex
        log = Transcript(args.output or Path(".replay") / f"{run_id}.jsonl")
        with httpx.Client(base_url=args.api.rstrip("/"), timeout=90) as api:
            if args.mode == "offline" or args.reset_only:
                channels = OfflineChannels(api, run_id, args.plans, log)
                replay = Replay(api, scenario, args.plans, channels, speed=args.speed, log=log)
                replay.reset() if args.reset_only else replay.run()
            else:
                from app.replay_channels import online_channels
                with online_channels(api, run_id, args.plans, log, args.timeout) as channels:
                    Replay(api, scenario, args.plans, channels, speed=args.speed, log=log).run()
        print(f"Transcript: {log.path}")
    except (Exception, KeyboardInterrupt) as error:
        # Do not print provider bodies, HTTP request URLs (bot tokens), or credentials.
        message = str(error) if isinstance(error, ReplayError) else type(error).__name__
        raise SystemExit(f"Replay stopped: {message}") from None


if __name__ == "__main__":
    main()
