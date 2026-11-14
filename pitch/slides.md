---
theme: default
title: GroundIQ Pitch
colorSchema: light
canvasWidth: 1280
aspectRatio: 16/9
transition: none
fonts:
  sans: Manrope
  serif: Sora
  mono: IBM Plex Mono
  weights: '400,500,600,700'
class: sheet-dark
sheet: Title
axes: true
---

<img src="/groundiq-logo-white.svg" style="height: 64px; margin-top: 28px" alt="GroundIQ" />

<h1 style="font-size: 76px; line-height: 1.04; letter-spacing: -.035em; margin-top: 84px">The context engine<br>for construction sites.</h1>

<p class="lead" style="max-width: 820px; font-size: 27px">GroundIQ catches site conflicts before the work happens, and keeps each one open until a responsible person closes it.</p>

<div class="label" style="position: absolute; left: 64px; bottom: 72px">Talona track · Proximata Hackathon '26 · Anastasia · David · Filip · Lea</div>

<!--
We are GroundIQ, a context engine for construction sites.
It notices when work is about to start without its preconditions, before the work happens, and keeps the problem open until a responsible person closes it.
-->

---
sheet: Problem
---

# Three messages, three channels.<br>Nobody connects them.

<svg style="position: absolute; left: 64px; top: 236px" width="1152" height="16" viewBox="0 0 1152 16">
  <defs><linearGradient id="tl" gradientUnits="userSpaceOnUse" x1="6" y1="0" x2="1146" y2="0"><stop offset="0" stop-color="#8DC0F5"/><stop offset=".72" stop-color="#176AC6"/><stop offset="1" stop-color="#E2492F"/></linearGradient></defs>
  <line x1="6" y1="8" x2="1146" y2="8" stroke="url(#tl)" stroke-width="2" stroke-linecap="round"/>
  <g fill="#176AC6"><circle cx="6" cy="8" r="6"/><circle cx="300" cy="8" r="6"/><circle cx="594" cy="8" r="6"/></g>
  <circle cx="888" cy="8" r="7" fill="#E2492F"/><circle cx="888" cy="8" r="12" fill="#E2492F" fill-opacity=".18"/>
</svg>

<div style="position: absolute; left: 64px; right: 64px; top: 272px; display: grid; grid-template-columns: repeat(4, 1fr); gap: 18px; font-size: 23px; line-height: 1.35">
  <div class="box"><div class="label">Day 1 · 10:15</div><p class="quote" style="margin-top: 12px">"Plan A-103 Rev D: Badwand 3B um 30 cm verschoben"</p><div class="mono muted" style="font-size: 15px; margin-top: 14px">mail · architect</div></div>
  <div class="box"><div class="label">Day 2 · 16:40</div><p class="quote" style="margin-top: 12px">"Abnahme der Rohinstallation im 3. OG auf Tag 4 verschoben."</p><div class="mono muted" style="font-size: 15px; margin-top: 14px">mail · inspector</div></div>
  <div class="box"><div class="label">Day 2 · 18:05</div><p class="quote" style="margin-top: 12px">"morgen früh machen wir 3B zu, platten sind da"</p><div class="mono muted" style="font-size: 15px; margin-top: 14px">telegram · drywall</div></div>
  <div class="box conflict"><div class="label red">Day 3 · 07:00</div><p style="margin-top: 12px">Wall 3B is closed before the inspection, without confirmed Rev D.</p><div class="mono red" style="font-size: 15px; margin-top: 14px">→ rework</div></div>
</div>

<p class="lead" style="position: absolute; left: 64px; top: 548px; max-width: 900px; font-size: 26px">Each message is harmless alone. The conflict only exists <b style="color: #171A1F">between</b> them.</p>

<!--
A normal week on our synthetic site.
Day 1, the architect mails Rev D: the bathroom wall in 3B moves 30 cm.
Day 2, the inspector postpones the rough-in inspection.
That evening the drywall crew writes in Telegram: we close 3B tomorrow morning.
Each message is fine alone. Together they mean a wall closed over uninspected pipes, by a crew without the new plan. That is rework.
-->

---
sheet: Evidence
---

# Lost information is expensive.

<div style="position: absolute; left: 64px; right: 64px; top: 210px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 22px">
  <div class="box" style="padding: 32px 30px"><div class="stat" style="color: #0F4C93">48 %</div><p class="lead" style="margin-top: 22px; font-size: 23px">of US rework comes from poor project data and miscommunication: <b style="color: #171A1F">$31.3 B</b> in 2018. <sup class="mono muted" style="font-size: 14px">[1]</sup></p></div>
  <div class="box" style="padding: 32px 30px"><div class="stat" style="color: #176AC6">14 h</div><p class="lead" style="margin-top: 22px; font-size: 23px">per person and week go to searching for data, resolving conflicts and fixing mistakes. <sup class="mono muted" style="font-size: 14px">[1]</sup></p></div>
  <div class="box" style="padding: 32px 30px"><div class="stat" style="color: #2F86E0">$1.85 T</div><p class="lead" style="margin-top: 22px; font-size: 23px">global cost of bad data in construction in 2020. <sup class="mono muted" style="font-size: 14px">[2]</sup></p></div>
</div>

<div class="cite">[1] FMI & PlanGrid, <i>Construction Disconnected</i>, 2018 · [2] FMI & Autodesk, <i>Harnessing the Data Advantage in Construction</i>, 2021</div>

<!--
This is common. FMI and PlanGrid found that 48 percent of US rework comes from poor data and miscommunication, about 31 billion dollars in 2018, and people lose 14 hours a week to it.
FMI and Autodesk put the global cost of bad data at 1.85 trillion dollars in 2020.
-->

---
sheet: Solution
---

# One pattern catches every conflict.

<div class="box accent" style="display: inline-block; padding: 18px 26px; font: 500 25px/1.35 'IBM Plex Mono', monospace">Work <span class="blue" style="font-weight: 600">Y</span> is due in zone <span class="blue" style="font-weight: 600">X</span>, but precondition <span class="blue" style="font-weight: 600">Z</span> is not satisfied.</div>

<svg style="position: absolute; left: 64px; top: 330px" width="1152" height="44" viewBox="0 0 1152 44">
  <defs><linearGradient id="st" gradientUnits="userSpaceOnUse" x1="22" y1="0" x2="1140" y2="0"><stop offset="0" stop-color="#0D3A78"/><stop offset="1" stop-color="#8DC0F5"/></linearGradient></defs>
  <line x1="22" y1="22" x2="1140" y2="22" stroke="url(#st)" stroke-width="2" stroke-dasharray="2 8" stroke-linecap="round"/>
</svg>

<div style="position: absolute; left: 64px; right: 64px; top: 330px; display: grid; grid-template-columns: repeat(4, 1fr); gap: 40px; font-size: 22px; line-height: 1.35">
  <div><div class="step-n" style="background: #0D3A78">01</div><div style="font: 600 26px/1.2 'Sora', sans-serif">Site record</div><p class="muted" style="margin-top: 8px">mail, chat, DXF plans, schedule</p></div>
  <div><div class="step-n" style="background: #176AC6">02</div><div style="font: 600 26px/1.2 'Sora', sans-serif">Deterministic rules</div><p class="muted" style="margin-top: 8px">satisfied, not satisfied, unknown, contradictory</p></div>
  <div><div class="step-n" style="background: #2F86E0">03</div><div style="font: 600 26px/1.2 'Sora', sans-serif">Flag</div><p class="muted" style="margin-top: 8px">with sources, owner and audit trail</p></div>
  <div><div class="step-n" style="background: #5AA2EE">04</div><div style="font: 600 26px/1.2 'Sora', sans-serif">A person closes it</div><p class="muted" style="margin-top: 8px">resolved or false alarm, with a reason</p></div>
</div>

<div style="position: absolute; left: 64px; top: 560px; display: flex; gap: 12px; flex-wrap: wrap">
  <span class="chip info">A · wall closed before the inspection is confirmed</span>
  <span class="chip info">B · crew without confirmed latest revision</span>
</div>

<!--
Every conflict has one shape: work Y is due in zone X, but precondition Z is not satisfied.
We keep a living site record from mail, chat, DXF plans and the schedule. Deterministic rules evaluate each precondition. Missing data is never a go.
If it fails, a rule raises a Flag, and only a person closes it, with a reason.
We built two conflict types, A and B.
-->

---
sheet: Plan diff · A-103 Rev C → D
---

# Rev D moves the bathroom wall by 30 cm.

<img src="/plan-3b.svg" alt="Apartment 3B, plan A-103: Rev D in red, Rev C dashed" class="drawing" style="position: absolute; left: 64px; top: 140px; width: 640px" />

<Leader :at="[583, 288]" :to="[770, 254]" tone="red">3B-BATH-WALL · A-WALL</Leader>
<Leader :at="[560, 207]" :to="[770, 196]" tone="red">3B-SANR-03 · drain</Leader>

<div style="position: absolute; left: 770px; top: 330px; width: 440px; font-size: 24px; line-height: 1.4">
  <div style="display: flex; gap: 22px; font: 500 16px 'IBM Plex Mono', monospace; margin-bottom: 24px; color: #4A5568">
    <span style="display: inline-flex; align-items: center; gap: 8px"><svg width="30" height="10"><line x1="2" y1="5" x2="28" y2="5" stroke="#E2492F" stroke-width="4" stroke-linecap="round"/></svg> Rev D</span>
    <span style="display: inline-flex; align-items: center; gap: 8px"><svg width="30" height="10"><line x1="2" y1="5" x2="28" y2="5" stroke="#8A93A1" stroke-width="4" stroke-dasharray="6 5" stroke-linecap="round"/></svg> Rev C</span>
  </div>
  <p class="lead">Parsed from the DXF, compared by stable element IDs.</p>
  <p style="margin-top: 16px">Affected zone: <b class="mono blue">3B</b>. No crew has confirmed Rev D → <b>Flag B</b>.</p>
</div>

<!--
This is the real plan of 3B, from our DXF files.
GroundIQ compares Rev D with Rev C element by element. The wall moved 300 millimetres, the drain was rerouted.
The diff is deterministic. Affected zone 3B, no crew there has confirmed Rev D, so Flag B warns the crew leads.
-->

---
sheet: Hero scenario
---

# GroundIQ catches it the evening before.

<div class="box rail" style="display: grid; grid-template-columns: 180px 1fr auto; align-items: center; column-gap: 8px; padding: 12px 32px; font-size: 25px">
  <span class="mono blue">Day 1 · 10:15</span><span>Rev D arrives by mail</span><span class="chip crit">Flag B · receipt not confirmed</span>
  <span class="mono blue">Day 2 · 17:00</span><span>"Abnahme dürfte passen"</span><span class="chip warn">unconfirmed claim, not proof</span>
  <span class="mono blue">Day 2 · 18:05</span><span>"morgen früh machen wir 3B zu"</span><span class="chip crit">Flag A · critical</span>
  <span class="mono blue">Day 2 · 18:06</span><span>Superintendent approves the proposal</span><span class="chip info">crew leads informed</span>
  <span class="mono blue">Day 3 · 09:00</span><span>Superintendent closes Flag A, with a reason</span><span class="chip ok">closed by a person</span>
</div>

<p style="position: absolute; left: 64px; top: 566px; max-width: 900px; font: 600 26px/1.3 'Sora', sans-serif; color: #0F4C93">Decided the evening before, not discovered after the wall is closed.</p>

<!--
The same week with GroundIQ.
Day 1, Flag B. Day 2, "Abnahme dürfte passen" stays an unconfirmed claim, not proof.
At 18:05 the drywall announcement raises Flag A, critical.
The advisor proposes to postpone drywall in 3B. The superintendent approves, then the crew leads are informed.
Day 3 the superintendent closes Flag A. The system never closes a Flag itself.
-->

---
sheet: Demo · dashboard
---

# See it on the plan. Read why.

<div class="shot" style="position: absolute; left: 64px; top: 140px; width: 640px; height: 424px"><img src="/room-3B-BATH.jpg" alt="3D site model, zone 3B-BATH with open Flags" /></div>
<div class="shot" style="position: absolute; left: 730px; top: 140px; width: 486px; height: 424px"><img src="/flag-detail.jpg" alt="Flag A detail with sources and advisory proposal" /></div>

<Leader :at="[365, 494]" :to="[420, 612]" tone="red">Rev D wall · Flag A + B</Leader>
<Leader :at="[1049, 302]" :to="[1000, 612]" tone="blue">LLM proposal · advisory</Leader>

<!--
Live demo, or these screenshots as backup.
Left, the 3D site model built from the same DXF geometry, zone 3B with its open Flags and the moved wall.
Right, the Flag detail: why it exists, original sources, evidence status, and an advisory proposal only the superintendent can approve.
-->

---
sheet: Demo · Telegram Q&A
---

# Crews ask. The record answers.

<div style="position: absolute; left: 64px; top: 140px; width: 620px; display: flex; flex-direction: column; gap: 14px; font-size: 21px; line-height: 1.35">
  <div class="bubble me"><div class="label" style="margin-bottom: 4px">crew lead · Day 2 · 18:30</div>welcher plan gilt für 3B?</div>
  <div class="bubble bot"><div class="label blue" style="margin-bottom: 4px">GroundIQ</div>Plan A-103 <b>Rev D</b> is the latest recorded revision, issued day 1, 10:15. Source: mail from the architect.</div>
  <div class="bubble me"><div class="label" style="margin-bottom: 4px">superintendent · Day 2 · 18:45</div>wie ist der Stand im Bad 3B?</div>
  <div class="bubble bot"><div class="label blue" style="margin-bottom: 4px">GroundIQ</div>Revision, inspection with evidence status, open Flags, next tasks, each with its source. <span class="mono blue">/zones/3B-BATH</span></div>
</div>

<div style="position: absolute; left: 748px; top: 150px; width: 468px; display: flex; flex-direction: column; gap: 20px; font-size: 24px; line-height: 1.35">
  <p style="border-left: 3px solid #0F4C93; padding-left: 20px"><b>The LLM only routes.</b> <span class="lead">It picks question type and zone from a fixed list.</span></p>
  <p style="border-left: 3px solid #176AC6; padding-left: 20px"><b>The answer comes from the record</b>, <span class="lead">through our own MCP tools, with sources.</span></p>
  <p style="border-left: 3px solid #5AA2EE; padding-left: 20px"><b>Unsure? It asks back.</b> <span class="lead">Decisions go to the superintendent.</span></p>
</div>

<!--
Crews ask where they already are, in Telegram. "Welcher Plan gilt für 3B?" Answer: Rev D, with its source.
The language model only routes the question to a fixed choice. The answer is built from the record through our own MCP tools, so it cannot claim an approval the record does not contain.
-->

---
sheet: Architecture
---

# How it works

<svg viewBox="0 0 1152 420" style="overflow: visible; position: absolute; left: 64px; top: 130px; width: 1152px; font-family: Manrope, sans-serif; font-size: 18px">
  <defs>
    <marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path d="M0,1 L9,5 L0,9 z" fill="#2F86E0"/></marker>
    <linearGradient id="api" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#F3F8FE"/><stop offset="1" stop-color="#E2EEFC"/></linearGradient>
    <filter id="sh" x="-10%" y="-20%" width="120%" height="160%"><feDropShadow dx="0" dy="4" stdDeviation="6" flood-color="#0F4C93" flood-opacity=".10"/></filter>
  </defs>
  <rect x="460" y="0" width="360" height="410" rx="22" fill="url(#api)" stroke="#BCD8F8" stroke-width="1.5"/>
  <g fill="#fff" stroke="#BCD8F8" stroke-width="1.25" filter="url(#sh)">
    <rect x="0" y="90" width="150" height="54" rx="12"/><rect x="0" y="190" width="150" height="54" rx="12"/>
    <rect x="220" y="120" width="170" height="94" rx="14"/>
    <rect x="490" y="44" width="300" height="48" rx="12"/><rect x="490" y="122" width="300" height="48" rx="12" stroke="#8DC0F5" stroke-dasharray="6 5"/>
    <rect x="490" y="200" width="300" height="48" rx="12" fill="#176AC6" stroke="#176AC6"/><rect x="490" y="278" width="300" height="48" rx="12"/><rect x="490" y="348" width="300" height="48" rx="12"/>
    <rect x="900" y="44" width="252" height="70" rx="14"/><rect x="900" y="176" width="252" height="70" rx="14"/><rect x="900" y="308" width="252" height="70" rx="14" fill="#0F4C93" stroke="#0F4C93"/>
  </g>
  <g fill="#171A1F" text-anchor="middle">
    <text x="75" y="124">Gmail</text><text x="75" y="224">Telegram</text>
    <text x="305" y="160" font-weight="700">worker</text><text x="305" y="186" style="font-size: 14px" fill="#7A8699">adapters · scheduler</text>
    <text x="640" y="74">Ingestion</text><text x="640" y="152" fill="#4A5568">LLM extraction · advisory</text>
    <text x="640" y="230" font-weight="700" fill="#fff">Site record · Postgres</text><text x="640" y="308">Rules → Flag</text><text x="640" y="378">Outbox</text>
    <text x="1026" y="76" font-weight="700">web</text><text x="1026" y="100" style="font-size: 14px" fill="#7A8699">dashboard · 3D</text>
    <text x="1026" y="208" font-weight="700">mcp</text><text x="1026" y="232" style="font-size: 14px" fill="#7A8699">9 tools</text>
    <text x="1026" y="338" fill="#fff" font-weight="700">any agent</text><text x="1026" y="362" style="font-size: 14px" fill="#BCD8F8">e.g. Talona's</text>
  </g>
  <text x="484" y="27" style="font-family: 'IBM Plex Mono', monospace; font-size: 14px" fill="#0F4C93">api · the only service with DB access</text>
  <g stroke="#2F86E0" stroke-width="1.5" fill="none" marker-end="url(#ar)" stroke-linecap="round">
    <path d="M150,117 L218,150"/><path d="M150,217 L218,186"/>
    <path d="M390,150 L488,68"/>
    <path d="M640,92 L640,120"/><path d="M640,170 L640,198"/><path d="M640,248 L640,276"/><path d="M640,326 L640,346"/>
    <path d="M490,372 L330,372 L330,216"/>
    <path d="M898,79 L792,224"/><path d="M898,211 L792,230"/><path d="M1026,306 L1026,248"/>
  </g>
</svg>

<div class="cite" style="font-size: 15px">5 services · <b style="color: #171A1F">docker compose up</b> · 761 tests in CI, all offline</div>

<!--
Five services, one docker compose up.
Mail and chat come in through the worker and one ingestion entry point. The LLM only extracts claims. Only the api touches the database. Rules raise Flags, and every outgoing message goes through an outbox.
Dashboard and MCP use the same REST API, so any agent, also Talona's, can plug in.
-->

---
sheet: Trust & compliance
---

# The LLM advises. People decide.

<div class="box" style="position: absolute; left: 64px; top: 140px; width: 660px; padding: 8px 26px 18px; font-size: 21px">
  <div style="display: grid; grid-template-columns: 1fr 96px 96px 96px">
    <span></span><span class="label" style="text-align: center; padding: 14px 0 10px">LLM</span><span class="label" style="text-align: center; padding: 14px 0 10px">Rules</span><span class="label" style="text-align: center; padding: 14px 0 10px">Person</span>
  </div>
  <div v-for="row in [['Extract claims', 'unconf.', '', ''], ['Raise a Flag', '', '■', ''], ['Confirm evidence', '', '', '■'], ['Approve a proposal', 'propose', '', '■'], ['Close a Flag', '', '', '■ + reason']]" :key="row[0]" style="display: grid; grid-template-columns: 1fr 96px 96px 96px; border-top: 1px solid rgba(23,106,198,.14); padding: 12px 0; align-items: center">
    <span>{{ row[0] }}</span>
    <span v-for="(c, i) in row.slice(1)" :key="i" class="mono" :style="{ textAlign: 'center', fontSize: c.length > 1 ? '14px' : '18px', color: i === 0 ? '#7A8699' : '#176AC6', fontWeight: 600 }">{{ c }}</span>
  </div>
  <p class="mono muted" style="font-size: 14px; margin-top: 12px">Every state change in the audit trail: who, when, channel, source.</p>
</div>

<div style="position: absolute; left: 776px; top: 146px; width: 440px; display: flex; flex-direction: column; gap: 18px; font-size: 22px; line-height: 1.35">
  <div class="label blue">Privacy by design</div>
  <p><b>No per-person metrics.</b> <span class="lead">Flags belong to zones, tasks and trades.</span></p>
  <p><b>The LLM sees text and role only.</b> <span class="lead">Phone numbers, emails, usernames masked.</span></p>
  <p><b>Telegram:</b> <span class="lead">allowlisted chats, retention period, <span class="mono" style="font-size: 18px">/delete_my_data</span>.</span></p>
  <p><b>Synthetic data only</b> <span class="lead">in this demo.</span></p>
</div>

<!--
The rule of the system: the LLM advises, people decide.
Rules raise Flags. Only a person confirms evidence, approves a proposal or closes a Flag, and these are separate actions. Everything is audited.
For privacy: no per-person metrics, the LLM sees only text and role, Telegram is allowlisted with a retention period.
-->

---
sheet: Learning loop
---

# One false alarm teaches the site.

<div style="position: absolute; left: 64px; right: 64px; top: 170px; display: grid; grid-template-columns: repeat(4, 1fr); gap: 18px; font-size: 21px; line-height: 1.35">
  <div class="box"><div class="label">Day 3 · 09:10</div><p class="quote" style="margin-top: 10px">"Können wir morgen früh 3B zumachen?"</p><p class="muted" style="margin-top: 10px; font-size: 17px">misread as planned work → Flag</p></div>
  <div class="box"><div class="label">Feedback</div><p style="margin-top: 10px">A person closes it as <b>false alarm</b>: "question, not announcement"</p></div>
  <div class="box"><div class="label">Site Knowledge</div><p style="margin-top: 10px">Correction stored, linked to feedback and source</p></div>
  <div class="box accent"><div class="label blue">Day 3 · 09:12</div><p style="margin-top: 10px">Same message → read as a question</p><p class="blue" style="margin-top: 10px; font-size: 17px; font-weight: 600">no Flag</p></div>
</div>

<div style="position: absolute; left: 64px; top: 432px; display: flex; align-items: center; gap: 18px; font-size: 23px">
  <span class="mono blue" style="font-size: 18px">Day 3 · 09:15</span><span>"heute früh machen wir 3B zu"</span><span class="chip crit">Flag A · still raised</span>
</div>

<p style="position: absolute; left: 64px; top: 516px; max-width: 980px; font-size: 23px"><span style="font: 600 24px/1.3 'Sora', sans-serif; color: #0F4C93">Learning fixes the reading, never the safety check.</span> <span class="lead">The dashboard tracks the share of confirmed Flags over time.</span></p>

<!--
Learning, from our replay. A question, "Können wir morgen früh 3B zumachen?", is misread as an announcement and raises a Flag.
The superintendent closes it as a false alarm and marks the extraction wrong. Next time the same message is read as a question.
But a real announcement still raises Flag A. Learning fixes the reading, never the safety check.
-->

---
sheet: Vision
---

# One site today. Every site next.

<div style="position: absolute; left: 64px; right: 64px; top: 170px; display: grid; grid-template-columns: 1fr 1fr; gap: 20px; font-size: 24px; line-height: 1.35">
  <div class="box" style="background: linear-gradient(135deg, #0F4C93, #176AC6); border: 0; color: #fff"><span class="chip ok" style="background: #DFF2E7">built</span><p style="margin-top: 14px"><b>MCP server for any agent.</b> <span style="color: #E2EEFC">Talona's own agent can plug in, with the tools our Q&A uses.</span></p></div>
  <div class="box"><span class="chip grey">next</span><p style="margin-top: 14px"><b>Learning across projects.</b> <span class="lead">What one site learns, the next one knows.</span></p></div>
  <div class="box"><span class="chip grey">next</span><p style="margin-top: 14px"><b>Photos checked against plans.</b> <span class="lead">"Wall is closed" as a claim to review.</span></p></div>
  <div class="box"><span class="chip grey">next</span><p style="margin-top: 14px"><b>Context for robots.</b> <span class="lead">Which plan and precondition apply, right here.</span></p></div>
</div>

<!--
Built today: an MCP server any agent can use, so Talona's own agent can plug in.
Next: learning across projects, photos checked against plans, and context for robots on site.
-->

---
class: sheet-dark
sheet: Close
axes: true
---

<img src="/groundiq-logo-white.svg" style="height: 52px; margin-top: 20px" alt="GroundIQ" />

<h1 style="font-size: 60px; line-height: 1.06; letter-spacing: -.03em; margin-top: 48px">Decisions stop getting lost<br>between mail and chat.</h1>

<div class="label" style="margin-top: 4px">Built in 24 hours</div>

<div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-top: 18px; font-size: 21px; max-width: 1150px">
  <span style="background: rgba(255,255,255,.06); border: 1px solid rgba(141,192,245,.22); border-radius: 14px; padding: 14px 18px">Conflicts A + B from mail, chat and DXF</span>
  <span style="background: rgba(255,255,255,.06); border: 1px solid rgba(141,192,245,.22); border-radius: 14px; padding: 14px 18px">Gmail and Telegram, in and out</span>
  <span style="background: rgba(255,255,255,.06); border: 1px solid rgba(141,192,245,.22); border-radius: 14px; padding: 14px 18px">3D site model from plan geometry</span>
  <span style="background: rgba(255,255,255,.06); border: 1px solid rgba(141,192,245,.22); border-radius: 14px; padding: 14px 18px">9 MCP tools for any agent</span>
  <span style="background: rgba(255,255,255,.06); border: 1px solid rgba(141,192,245,.22); border-radius: 14px; padding: 14px 18px">Offline replay of the hero week</span>
  <span style="background: rgba(255,255,255,.06); border: 1px solid rgba(141,192,245,.22); border-radius: 14px; padding: 14px 18px">761 tests · one docker compose up</span>
</div>

<div class="label" style="position: absolute; left: 64px; bottom: 72px">github.com/davidsteindl/ProximataHackathon · 3-min video: see submission</div>

<!--
Back to the start: three messages nobody connected. GroundIQ connects them before the wall is closed.
All of this was built in 24 hours and runs with one docker compose up. Thank you, we are happy to take questions.
-->
