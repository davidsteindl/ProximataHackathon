# AGENTS.md

SiteMind: a context engine for construction sites (Proximata Hackathon '26, Talona track).
The product is the engine (site record, rules, flags). The agent is replaceable.

## Read first
- `docs/PLAN.md`: scope, glossary (§2), core concepts (§3), hero scenario (§7). Use the glossary terms in code (Flag, Event, Zone, Precondition …).
- `README.md#architektur`: diagrams and architecture rules.
- Your GitHub issue: *what* and inputs/outputs are fixed there; *how* is your call. Overview: issue #1.

## Workflow
- One issue = one branch = one PR. Never commit to `main`.
- Work in a separate git worktree per issue, so 4 people with agents don't collide:
  `git worktree add ../ProximataHackathon-<issue> -b <issue>-<short-slug> origin/main`
- Before starting, check that the issue's blockers are merged.
- Stay inside the issue's acceptance criteria and *Out of scope*. Note follow-up work in the PR; don't build it.
- PR: English, `Closes #<n>`, short summary + how to verify. One human approves and merges, never the agent.
- Before opening the PR: rebase on `origin/main`, CI must pass.
- Changing a shared contract (DB schema, REST API, glossary, architecture)? State it in the PR and update `docs/PLAN.md` / `README.md` in the same PR.
- DB migrations: rebase right before creating one; if another migration landed meanwhile, regenerate yours on top. No parallel heads.

## Architecture rules (non-negotiable)
- Services: `db` (Postgres), `api` (FastAPI), `worker`, `mcp`, `web` (Next.js + Three.js). Everything starts with `docker compose up`.
- Only `api` touches the database. `worker`, `mcp` and `web` use the REST API (OpenAPI is the contract).
- All inbound sources (Gmail, Telegram, seed, replay) go through the single ingestion entry point.
- All outbound messages go through the outbox: `api` writes, `worker` sends and reports status.
- The LLM only advises: extraction, explanation, proposals, answers. It never creates, changes or closes flags and never approves actions.
- Flags are created by deterministic rules only. Flags are closed by humans only, always with feedback (`resolved` / `false alarm` + reason). The system never closes a flag.
- Every flag state change is written to the audit trail (who, when, channel, source).
- The chat agent uses our own MCP tools, like any external agent. MCP tools can't close flags or approve proposals.
- Gmail/Telegram credentials live only in `worker`, the LLM key only in `api`.

## Compliance (part of the product, not optional)
- No secrets in the repo. Every new env var goes into `.env.example`.
- Send the LLM only message text + sender role. No phone numbers, usernames or emails.
- No per-person metrics or rankings. Flags belong to zones, tasks and trades, not to people (works council issue).
- Telegram: process only allowlisted chats/users; raw messages have a configurable retention period.
- Gmail: minimal scopes, dedicated project mailbox only.
- Only synthetic data and team test accounts. No real third-party data.
- The code belongs to Talona: private repo, no MIT licence. GPL tools (e.g. LibreDWG) only as a separate process, never linked as a library.

## Tests
- Every piece of logic gets unit tests (rules, lifecycle, dedup, escalation, extraction, CAD parsing, plan diff).
- LLM, Gmail and Telegram are always mocked in tests. CI runs offline without credentials.
- The hero scenario (PLAN §7) is the acceptance reference. Don't break the seed reset, replay or offline mode.

## Environment
- Team machines are ARM64 (Windows) and x64. Images and binaries must work on both; x64-only tools need a fallback.
- Several worktrees can run compose stacks at the same time: no fixed `container_name`, host ports configurable via `.env`.

## Deadline
- Feature freeze Sat 12:00: after that only bug fixes. Code freeze Sat 15:00 (hard).
- Prefer a working, demoable slice over completeness.
