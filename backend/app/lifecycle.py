"""Flag transitions shared by human actions and trusted API-side integrations."""

from datetime import UTC, datetime

from app import models

TRANSITIONS = {
    "notified": ({"detected"}, "notified", "system"),
    "acknowledge": ({"notified"}, "acknowledged", "human"),
    "action_approved": ({"acknowledged"}, "in_progress", "human"),
    "resolved": ({"in_progress"}, "resolved", "human"),
    "false_alarm": ({"notified", "acknowledged", "in_progress"}, "false_alarm", "human"),
    # Escalation informs the next level; it keeps the current state (None).
    "escalated": ({"detected", "notified"}, None, "system"),
}


class InvalidTransition(ValueError):
    pass


def transition_flag(session, flag, *, action, actor, actor_type, channel, source_ref,
                    role=None, feedback=None, reason=None):
    """Caller locks the Site first and authorizes the actor/source before calling.

    #10 calls notified after delivery; #13 calls action_approved only after its
    human approval validation; #14 calls escalated after an actual escalation.
    None of those signals is accepted from the public human action endpoint.
    """
    spec = TRANSITIONS.get(action)
    if spec is None:
        raise InvalidTransition("Unknown Flag action")
    allowed, target, required_actor = spec
    target = target or flag.state
    if flag.state not in allowed or actor_type != required_actor:
        raise InvalidTransition(f"Cannot {action} a {flag.state} Flag as {actor_type}")
    expected_feedback = {"acknowledge": "confirmed", "resolved": "resolved", "false_alarm": "false_alarm"}.get(action)
    if feedback != expected_feedback:
        raise InvalidTransition("Action requires matching feedback")
    if expected_feedback and (not reason or not reason.strip()):
        raise InvalidTransition("Feedback requires a reason")
    if not actor or not actor.strip() or not source_ref or not source_ref.strip() or not channel:
        raise InvalidTransition("Actor, channel and basis/source are required")
    if required_actor == "human" and role not in {"superintendent", "crew_lead"}:
        raise InvalidTransition("Human role required")
    if required_actor == "human" and role == "crew_lead" and actor != flag.responsible_id:
        raise InvalidTransition("Only the responsible Crew Lead may act on this Flag")
    if action == "action_approved" and role != "superintendent":
        raise InvalidTransition("Only the Superintendent may approve an action")
    now = datetime.now(UTC)
    flag.audit.append(models.FlagAudit(
        action=action, actor=actor, actor_role=role, channel=channel,
        source_ref=source_ref, recorded_at=now, from_state=flag.state,
        to_state=target, feedback=feedback, reason=reason.strip() if reason else None,
    ))
    flag.state, flag.updated_at = target, now
    if target in {"resolved", "false_alarm"}:
        flag.open_key = None
    session.add(flag)
