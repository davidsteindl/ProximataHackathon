"""Deterministic predecessor completion checks using source-backed Evidence."""

from sqlalchemy import and_, or_, select

from app import models


def completion_evidence(session, task, zones):
    from app.event_mapping import normalized
    from app.rules import inspection_evidence_scope

    records = session.scalars(select(models.Evidence).where(
        models.Evidence.kind == "task_completion",
        or_(models.Evidence.task_id == task.id, and_(
            models.Evidence.task_id.is_(None),
            models.Evidence.zone_id.in_(inspection_evidence_scope(task.zone_id, zones)),
        )),
    ).order_by(models.Evidence.id).execution_options(populate_existing=True)).all()
    result = []
    for item in records:
        if item.task_id is None and item.origin == "llm_statement":
            statement = session.get(models.Event, item.statement_ref)
            reference = statement.details.get("task_reference") if statement else None
            if reference and normalized(reference) not in {normalized(task.id), normalized(task.name)}:
                continue
        result.append(item)
    return result


def evaluate_completion(session, task, records):
    from app.rules import utc

    relevant, confirmed = [], []
    for item in records:
        if item.review_status == "rejected":
            continue
        exact_scope = item.task_id == task.id and item.zone_id == task.zone_id
        if item.task_id is not None and not exact_scope:
            continue
        if item.origin == "llm_statement":
            statement = session.get(models.Event, item.statement_ref)
            if (statement is None or statement.intent != "task_completion"
                    or item.source_ref != f"source:{statement.source_message_id}"
                    or item.quote != statement.quote or item.claim != statement.details.get("claim")
                    or item.zone_id not in statement.zone_ids
                    or utc(statement.source.sent_at) < utc(task.starts_at)):
                continue
        relevant.append(item)
        review = item.history[-1] if item.history else None
        if exact_scope and review and review.status == "confirmed" and (
            review.actor_type == "human" or
            item.origin == "seed_baseline" and review.actor_type == "seed_import"
        ):
            confirmed.append(item)
    claims = {item.claim for item in relevant}
    if {"completed", "not_completed"} <= claims:
        return "contradictory", relevant
    if any(item.claim == "completed" for item in confirmed):
        return "satisfied", relevant
    if any(item.claim == "not_completed" for item in confirmed):
        return "not_satisfied", relevant
    return "unknown", relevant


class PredecessorsCompleted:
    type = "C"
    name = "predecessors_completed"

    def applies(self, work):
        return (work.revision is None and work.task is not None and bool(work.task.predecessors)
                and (work.event is None or work.event.intent == "planned_work"))

    def evaluate(self, session, work, zones):
        from app.rules import Evaluation

        predecessors, source_ids = [], []
        for task in sorted(work.task.predecessors, key=lambda item: item.id):
            status, records = evaluate_completion(session, task, completion_evidence(session, task, zones))
            predecessors.append({
                "task_id": task.id, "task_name": task.name, "zone_id": task.zone_id,
                "evaluation": status, "evidence_ids": [item.id for item in records],
                "source_refs": [f"task:{task.id}", *[item.source_ref for item in records]],
            })
            source_ids.extend(item.statement_ref for item in records if item.origin == "llm_statement")
        statuses = {item["evaluation"] for item in predecessors}
        status = next((candidate for candidate in ("contradictory", "not_satisfied", "unknown")
                       if candidate in statuses), "satisfied")
        missing = [f'{item["task_name"]} ({item["task_id"]}): {item["evaluation"]}'
                   for item in predecessors if item["evaluation"] != "satisfied"]
        explanation = ("Predecessor completion requires review: " + "; ".join(missing)
                       + ". Missing or unconfirmed statements are not proof."
                       if missing else "Valid confirmed completion evidence for all predecessor Tasks.")
        return Evaluation(status, explanation, context={"predecessors": predecessors},
                          source_event_ids=tuple(dict.fromkeys(source_ids)))
