"""Worker-side clock for the morning scan and escalation timer (REST only)."""

import os
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo


def parse_scan_time(value):
    try:
        hour, minute = (int(part) for part in value.split(":"))
        return time(hour, minute)
    except ValueError as error:
        raise ValueError("MORNING_SCAN_TIME must be HH:MM") from error


@dataclass
class JobSchedule:
    """Decides when jobs are due. The API jobs are idempotent, so a restart that
    repeats today's scan or an early escalation check only re-deduplicates."""
    scan_time: time
    escalation_seconds: float
    last_scan_date: object = None
    last_escalation: datetime | None = None

    @classmethod
    def from_env(cls):
        seconds = float(os.environ.get("ESCALATION_CHECK_SECONDS") or 300)
        if seconds <= 0:
            raise ValueError("ESCALATION_CHECK_SECONDS must be positive")
        return cls(parse_scan_time(os.environ.get("MORNING_SCAN_TIME") or "06:00"), seconds)

    def scan_due(self, now, timezone):
        """Once per local day, at or after the configured time."""
        local = now.astimezone(ZoneInfo(timezone))
        return local.time() >= self.scan_time and self.last_scan_date != local.date()

    def mark_scanned(self, now, timezone):
        self.last_scan_date = now.astimezone(ZoneInfo(timezone)).date()

    def escalation_due(self, now):
        return self.last_escalation is None or now - self.last_escalation >= timedelta(seconds=self.escalation_seconds)

    def mark_escalation(self, now):
        self.last_escalation = now


def run_due_jobs(schedule, api, now=None):
    """Trigger due jobs via the API; the API owns all rule logic and thresholds."""
    now = now or datetime.now(UTC)
    ran = []
    site = api.get("/site")
    site.raise_for_status()
    site = site.json()
    if site is None:
        return ran
    if schedule.scan_due(now, site["timezone"]):
        api.post("/jobs/morning-scan", json={}).raise_for_status()
        schedule.mark_scanned(now, site["timezone"])
        ran.append("morning_scan")
    if schedule.escalation_due(now):
        api.post("/jobs/escalation", json={}).raise_for_status()
        schedule.mark_escalation(now)
        ran.append("escalation")
    return ran
