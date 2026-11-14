# GroundIQ — the context engine for construction sites

**One-line pitch:** GroundIQ connects messages, plans and schedules into a shared construction-site record, detects conflicts before work starts, and tracks each problem until a responsible human closes it.

**Team:** Anastasia, David, Filip and Lea · Talona track · Proximata Hackathon 2026.

## The problem

Construction decisions are spread across emails, crew chats, drawings and schedules. Each message may look reasonable on its own while the combination reveals a costly mistake: a wall is about to be closed before its inspection, a crew is working without acknowledging the latest plan revision, or a task starts before its predecessor is complete. Finding these conflicts requires someone to connect the right information across channels and keep following up. A useful answer in a chat is not enough if the underlying problem then disappears from view.

## What we built

GroundIQ maintains a persistent Site Record linking Zones, Tasks, Crews, plan Revisions, Inspections and source-backed Evidence. Gmail and Telegram adapters bring messages into one ingestion pipeline. Language models extract structured Events and explain potential problems, while deterministic rules evaluate the work's Preconditions and create Flags. Morning scans check upcoming scheduled work; factual notifications and configurable escalation keep unresolved conflicts visible.

The dashboard combines a Flag inbox, separate Evidence review, proposed actions, an activity feed and an interactive 3D building view. The building geometry comes from DXF drawings rather than a disconnected visual mockup. A geometric comparison between plan revisions identifies affected Zones, connecting drawing changes to the same record used by rules, reviewers and agents.

Each Flag links back to its sources, identifies the missing or conflicting Precondition, and records its lifecycle. The Superintendent can review a proposed response, such as postponing drywall work and reallocating a crew. Operational instructions require explicit human approval. Outbound messages pass through a persistent outbox with delivery status and retries. Flags stay open until a human closes them with feedback and a reason.

## Trustworthy uncertainty and human control

An extracted statement is not proof. Even a confident message saying “inspection passed” remains unconfirmed until a responsible human reviews its source and confirms Evidence for the exact Inspection and Zone. Preconditions distinguish satisfied, not satisfied, unknown and contradictory states. Missing, stale, mismatched, unconfirmed or unresolved contradictory Evidence cannot clear work to proceed.

Evidence confirmation, Flag acknowledgment, Proposal approval and Flag closure are separate actions. Confirming an Inspection does not close a Flag; closing a Flag does not certify an Inspection. Source references and audit history preserve that distinction. Models can advise, but cannot confirm Evidence, approve actions or close Flags.

## A concrete demonstration

Our synthetic project is a four-floor residential building. An architect emails Revision D, moving the bathroom wall in apartment 3B by 30 centimetres. GroundIQ detects the changed Zone and flags missing confirmed receipt of the revision by the relevant crew. An inspector then postpones the required inspection. When the drywall crew writes “tomorrow morning we're closing 3B,” GroundIQ connects these records and raises a critical conflict before the planned work.

The Superintendent reviews the sources, acknowledges the problem and separately approves a response. Later, a positive inspection report still requires human Evidence review. The guided replay pauses for these decisions and demonstrates that satisfying a Precondition does not automatically close its Flag.

## Learning and an open agent interface

Feedback can correct a specific extraction mistake, such as a question misread as a work announcement. Replaying that case uses traceable Site Knowledge, while genuine conflicts still trigger rules. Learning does not weaken safety checks or automatically confirm Evidence.

The context engine is the product; the agent is replaceable. Our Telegram question-answering flow uses the same Model Context Protocol tools available to an external agent, including a future Talona integration. Answers draw on the shared record, cite sources and expose uncertainty. Decision requests are forwarded to the Superintendent rather than treated as approvals.

## Technology, reproducibility and limits

The implementation uses Python/FastAPI, PostgreSQL, a background worker, an MCP server, and a Next.js/React/Three.js dashboard, packaged with Docker Compose. The repository documents setup and includes synthetic DXF plans, seed data and a guided replay. Cached model outputs support a demonstration without external credentials; simulated deliveries are explicitly labelled. GitHub CI checks backend tests, frontend tests/build and Compose configuration.

This is a hackathon MVP using synthetic data and team test accounts. It has no per-person performance rankings. Telegram processing uses chat and user allowlists with configurable raw-data retention. Production authentication, complete retention policies and provider/legal arrangements remain deployment requirements. Real-world reductions in rework have not been measured. The private repository and application work belong to Talona under the track's terms.

**Links:** [Repository](https://github.com/davidsteindl/ProximataHackathon) · [Setup and demo](README.md) · [Pitch deck](pitch/GroundIQ-pitch.pdf) · [Compliance and limits](COMPLIANCE.md).
