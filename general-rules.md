# Building Better Worlds Hackathon — General Rules

13–14 November 2026 · Home of Innovation (HOIV), Arsenalstraße 11, 1030 Vienna · 24 hours

| | |
|---|---|
| Keynote panel | Friday 13 November, 12:00, with Hubert Rhomberg, CEO of Rhomberg |
| Start | Friday 13 November, 14:00 |
| n8n and Adaption workshop | Saturday 14 November, 11:00 |
| Code freeze | Saturday 14 November, 15:00 sharp |
| Round 1: track judging | Saturday 14 November, 15:00–16:00 |
| Round 2: final demos | Saturday 14 November, 16:00–16:45 |
| Winner announcement | Saturday 14 November, 17:00 |
| End | Saturday 14 November, 18:00, with networking |
| Format | In person (online only by exception, arranged beforehand) |
| Teams | 2–4 people, one track per team |

## Submission

One submission per team via the submission form by code freeze on Saturday, 14 November at 15:00.
Late submissions are not accepted. [Form link, shared on Discord]

- Public GitHub repository (MIT license) in the proximata GitHub organisation, in your track's
  folder, in your team's folder
- 3-minute demo video showing the solution working end to end
- Written submission: project title, one-line pitch, team & members, problem, solution overview,
  tech stack, and links
- Optional: a live demo link and a pitch deck (PDF)

### Track-specific additions

| Track | On top of the standard package |
|---|---|
| Talona | Code sits in a private repository, not the public MIT one. All work belongs to Talona. |
| Rhomberg | `decisions.jsonl`, `decisions_holdout.jsonl` and `insights.md` at the repository root, plus a `pre-holdout` git tag. The pipeline runs as one documented command. |
| Dorabella | A filled Excel factsheet per project, a short description of the approach, and code or a demo. Private repository; all work belongs to Dorabella. |
| TUWRC | Standard package. The README documents the hardware findings so the next team can build on them. |
| proximata | A `REPORT.md` at the repo root that starts with the scorecard from `docs/REPORT_TEMPLATE.md`, one command that reproduces your held-out numbers, and a download script or link for data you may not redistribute. |
| Biscuit, Crypto Club Vienna | Standard package. |

## Repository requirements

- Public at submission time, with an MIT `LICENSE` file at the root (except Talona and Dorabella)
- A real README (setup, run, environment, architecture, assumptions) and a `.env.example` — no
  secrets committed
- Code that the jury can run or reproduce from the README

## How judging works

Judging runs in two rounds.

**Round 1 — track juries (15:00–16:00).** Every track has its own jury, including its case partner.
Each team gets up to 5 minutes of live demo and 3 minutes of questions, on top of what it submitted.
Teams are scored on their track's criteria (see the full brief of your track) and each track jury
picks one Track Winner. Rhomberg also runs an automated check on its holdout dataset; it is input
for the jury, not the final grade. proximata has no hidden test suite: the jury checks each team's
evidence live and in its `REPORT.md`.

Tracks whose partner sets no scoring of its own (currently Biscuit) use the default criteria:

| Category | Points | What we look at |
|---|---|---|
| Technical implementation | 40 | Does it work, is it well built, how hard was it |
| Effectiveness and impact | 35 | How well it solves the partner's problem, and the value if deployed |
| Demo and presentation | 25 | Clarity of the pitch and a live working demo |
| Total | 100 | |

**Round 2 — external jury (from 16:00).** The 7 Track Winners each get 4 minutes of live demo and
2 minutes of questions in front of an external jury of VCs, founders and tech leads. Track scores do
not carry over; every team is judged relative to the difficulty of its own case.

| Category | Points | What the jury looks for |
|---|---|---|
| Impact and relevance | 30 | Solves a real problem for its partner or users, with clear value if deployed |
| Technical achievement | 30 | How hard the case was, how far the team got, and how well it works live |
| Innovation | 20 | A fresh approach rather than a known product rebuilt |
| Live demo and pitch | 20 | A working demo, a clear story in 4 minutes, strong answers to questions |
| Total | 100 | |

Tie-breakers in Round 2: the stronger live demo first, then technical achievement.

What the juries reward: what was built, not what was promised — a roadmap slide is not a feature,
and a simulated effect is not a measurement. Honesty counts: "not found", labelled simulations and
stated limitations are signs of a strong team. Code that cannot be run or reproduced from its README
costs points.

## Intellectual property

All code is committed to the proximata public GitHub organisation under the MIT license. Hackers
retain copyright of their work. By participating, hackers grant the case partner of their assigned
track a perpetual, worldwide, royalty-free, non-exclusive license to use, modify, distribute, and
commercialise their work product. Hackers keep the right to use, develop further, and commercialise
their own work in parallel.

**Exception: the Talona and Dorabella tracks.** All work produced on these two tracks belongs to the
track partner. Participants grant the partner the exclusive, perpetual, worldwide right to use it;
code goes to a private repository and is not published under the MIT license. Participants may
mention their participation and role in a CV or portfolio. Every team member must accept these
terms before their team is matched to either track.

Credentials such as API keys or sandbox access go out on Discord only — never commit a secret.

Questions? contact@proximata.io
