---
theme: default
title: GroundIQ Pitch
colorSchema: light
canvasWidth: 1280
aspectRatio: 16/9
transition: none
fonts:
  sans: Inter
  serif: Space Grotesk
  mono: JetBrains Mono
  weights: '400,500,600,700'
class: sheet-dark
sheet: Title
axes: true
---

<img src="/groundiq-logo-white.svg" style="height: 76px; margin-top: 40px" alt="GroundIQ" />

<h1 style="font-size: 68px; margin-top: 64px">The context engine<br>for construction sites.</h1>

<p style="max-width: 900px; color: #C9D1DB">GroundIQ catches site conflicts before the work happens, and keeps each one open until a responsible person closes it.</p>

<div class="label" style="margin-top: 48px">Talona track · Proximata Hackathon '26 · Anastasia · David · Filip · Lea</div>

<!--
We are GroundIQ, a context engine for construction sites.
It notices when work is about to start without its preconditions, before the work happens, and keeps the problem open until a responsible person closes it.
-->

---
sheet: Problem
---

# Three messages, three channels.<br>Nobody connects them.

<div style="position: absolute; left: 64px; right: 64px; top: 250px; display: grid; grid-template-columns: repeat(4, 1fr); gap: 18px; font-size: 25px; line-height: 1.3">
  <div class="box"><div class="label">Day 1 · 10:15</div><p style="margin-top: 10px">"Plan A-103 Rev D: Badwand 3B um 30 cm verschoben"</p><div class="mono muted" style="font-size: 17px; margin-top: 10px">mail · architect</div></div>
  <div class="box"><div class="label">Day 2 · 16:40</div><p style="margin-top: 10px">"Abnahme der Rohinstallation im 3. OG auf Tag 4 verschoben."</p><div class="mono muted" style="font-size: 17px; margin-top: 10px">mail · inspector</div></div>
  <div class="box"><div class="label">Day 2 · 18:05</div><p style="margin-top: 10px">"morgen früh machen wir 3B zu, platten sind da"</p><div class="mono muted" style="font-size: 17px; margin-top: 10px">telegram · drywall</div></div>
  <div class="box conflict"><div class="label red">Day 3 · 07:00</div><p style="margin-top: 10px">Wall 3B is closed before the inspection, without confirmed Rev D.</p><div class="mono red" style="font-size: 17px; margin-top: 10px">→ rework</div></div>
</div>

<svg style="position: absolute; left: 64px; top: 210px" width="1152" height="24" viewBox="0 0 1152 24"><line x1="0" y1="12" x2="1152" y2="12" stroke="#171A1F" stroke-width="1.5"/><g stroke="#171A1F" stroke-width="1.5"><line x1="0" y1="2" x2="0" y2="22"/><line x1="292" y1="2" x2="292" y2="22"/><line x1="584" y1="2" x2="584" y2="22"/></g><line x1="876" y1="2" x2="876" y2="22" stroke="#E2492F" stroke-width="2"/><line x1="1152" y1="2" x2="1152" y2="22" stroke="#171A1F" stroke-width="1.5"/></svg>

<p style="position: absolute; left: 64px; top: 520px; max-width: 900px">Each message is harmless alone. The conflict only exists <b>between</b> them.</p>

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

<div style="position: absolute; left: 64px; right: 64px; top: 220px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 40px">
  <div><div style="font: 600 88px/1 'Space Grotesk'; color: var(--blue)">48 %</div><p style="margin-top: 16px; font-size: 26px">of US rework comes from poor project data and miscommunication: <b>$31.3 B</b> in 2018. <sup class="mono muted" style="font-size: 16px">[1]</sup></p></div>
  <div><div style="font: 600 88px/1 'Space Grotesk'; color: var(--blue)">14 h</div><p style="margin-top: 16px; font-size: 26px">per person and week go to searching for data, resolving conflicts and fixing mistakes. <sup class="mono muted" style="font-size: 16px">[1]</sup></p></div>
  <div><div style="font: 600 88px/1 'Space Grotesk'; color: var(--blue)">$1.85 T</div><p style="margin-top: 16px; font-size: 26px">global cost of bad data in construction in 2020. <sup class="mono muted" style="font-size: 16px">[2]</sup></p></div>
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

<div class="box" style="font: 500 27px/1.35 'JetBrains Mono'; display: inline-block">Work <span class="blue">Y</span> is due in zone <span class="blue">X</span>, but precondition <span class="blue">Z</span> is not satisfied.</div>

<div style="position: absolute; left: 64px; right: 64px; top: 360px; display: grid; grid-template-columns: repeat(4, 1fr); gap: 44px; font-size: 24px; line-height: 1.3">
  <div><div class="label blue">01</div><b style="font-size: 28px">Site record</b><p class="muted" style="margin-top: 6px">mail, chat, DXF plans, schedule</p></div>
  <div><div class="label blue">02</div><b style="font-size: 28px">Deterministic rules</b><p class="muted" style="margin-top: 6px">satisfied, not satisfied, unknown, contradictory</p></div>
  <div><div class="label blue">03</div><b style="font-size: 28px">Flag</b><p class="muted" style="margin-top: 6px">with sources, owner and audit trail</p></div>
  <div><div class="label blue">04</div><b style="font-size: 28px">A person closes it</b><p class="muted" style="margin-top: 6px">resolved or false alarm, with a reason</p></div>
</div>

<svg style="position: absolute; left: 64px; top: 340px" width="1152" height="12" viewBox="0 0 1152 12"><line x1="0" y1="6" x2="1140" y2="6" stroke="#176AC6" stroke-width="2"/><polygon points="1140,0 1152,6 1140,12" fill="#176AC6"/><g fill="#176AC6"><circle cx="4" cy="6" r="4"/><circle cx="296" cy="6" r="4"/><circle cx="588" cy="6" r="4"/><circle cx="880" cy="6" r="4"/></g></svg>

<div style="position: absolute; left: 64px; top: 548px; display: flex; gap: 14px; flex-wrap: wrap">
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

<img src="/plan-3b.svg" alt="Apartment 3B, plan A-103: Rev D in red, Rev C dashed" style="position: absolute; left: 64px; top: 140px; width: 640px; background: #fff; border: 1.5px solid #171A1F" />

<Leader :at="[583, 288]" :to="[770, 254]" tone="red">3B-BATH-WALL · A-WALL</Leader>
<Leader :at="[560, 207]" :to="[770, 196]" tone="red">3B-SANR-03 · drain</Leader>

<div style="position: absolute; left: 760px; top: 320px; width: 450px; font-size: 26px; line-height: 1.35">
  <div style="display: flex; gap: 20px; font: 500 18px 'JetBrains Mono'; margin-bottom: 22px">
    <span><svg width="34" height="10"><line x1="0" y1="5" x2="34" y2="5" stroke="#E2492F" stroke-width="4"/></svg> Rev D</span>
    <span><svg width="34" height="10"><line x1="0" y1="5" x2="34" y2="5" stroke="#8A93A1" stroke-width="4" stroke-dasharray="7 5"/></svg> Rev C</span>
  </div>
  <p>Parsed from the DXF, compared by stable element IDs.</p>
  <p style="margin-top: 14px">Affected zone: <b class="mono">3B</b>. No crew has confirmed Rev D → <b>Flag B</b>.</p>
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

<div class="rail" style="display: grid; grid-template-columns: 190px 1fr auto; align-items: center; font-size: 27px">
  <span class="mono blue">Day 1 · 10:15</span><span>Rev D arrives by mail</span><span class="chip crit">Flag B · receipt not confirmed</span>
  <span class="mono blue">Day 2 · 17:00</span><span>"Abnahme dürfte passen"</span><span class="chip warn">unconfirmed claim, not proof</span>
  <span class="mono blue">Day 2 · 18:05</span><span>"morgen früh machen wir 3B zu"</span><span class="chip crit">Flag A · critical</span>
  <span class="mono blue">Day 2 · 18:06</span><span>Superintendent approves the proposal</span><span class="chip info">crew leads informed</span>
  <span class="mono blue">Day 3 · 09:00</span><span>Superintendent closes Flag A, with a reason</span><span class="chip ok">closed by a person</span>
</div>

<p style="position: absolute; left: 64px; top: 560px; max-width: 900px; font-size: 26px">Decided the evening before, not discovered after the wall is closed.</p>

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

<div style="position: absolute; left: 64px; top: 140px; width: 620px; display: flex; flex-direction: column; gap: 14px; font-size: 22px; line-height: 1.3">
  <div class="box" style="align-self: flex-end; border-radius: 14px 14px 2px 14px"><div class="label">crew lead · Day 2 · 18:30</div>welcher plan gilt für 3B?</div>
  <div class="box" style="align-self: flex-start; border-radius: 14px 14px 14px 2px; border-color: #176AC6"><div class="label blue">GroundIQ</div>Plan A-103 <b>Rev D</b> is the latest recorded revision, issued day 1, 10:15. Source: mail from the architect.</div>
  <div class="box" style="align-self: flex-end; border-radius: 14px 14px 2px 14px"><div class="label">superintendent · Day 2 · 18:45</div>wie ist der Stand im Bad 3B?</div>
  <div class="box" style="align-self: flex-start; border-radius: 14px 14px 14px 2px; border-color: #176AC6"><div class="label blue">GroundIQ</div>Revision, inspection with evidence status, open Flags, next tasks, each with its source. <span class="mono blue">/zones/3B-BATH</span></div>
</div>

<div style="position: absolute; left: 740px; top: 160px; width: 470px; display: flex; flex-direction: column; gap: 26px; font-size: 26px">
  <p><b>The LLM only routes.</b> It picks question type and zone from a fixed list.</p>
  <p><b>The answer comes from the record</b>, through our own MCP tools, with sources.</p>
  <p><b>Unsure? It asks back.</b> Decisions go to the superintendent.</p>
</div>

<!--
Crews ask where they already are, in Telegram. "Welcher Plan gilt für 3B?" Answer: Rev D, with its source.
The language model only routes the question to a fixed choice. The answer is built from the record through our own MCP tools, so it cannot claim an approval the record does not contain.
-->

---
sheet: Architecture
---

# How it works

<svg viewBox="0 0 1152 420" style="position: absolute; left: 64px; top: 130px; width: 1152px; font-family: Inter; font-size: 19px">
  <defs><marker id="ar" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#171A1F"/></marker></defs>
  <g fill="#fff" stroke="#171A1F" stroke-width="1.5">
    <rect x="0" y="90" width="150" height="54"/><rect x="0" y="190" width="150" height="54"/>
    <rect x="220" y="120" width="170" height="94"/>
    <rect x="460" y="0" width="360" height="410" fill="none" stroke-width="2"/>
    <rect x="490" y="44" width="300" height="48"/><rect x="490" y="122" width="300" height="48" stroke-dasharray="7 5"/>
    <rect x="490" y="200" width="300" height="48"/><rect x="490" y="278" width="300" height="48"/><rect x="490" y="348" width="300" height="48"/>
    <rect x="900" y="44" width="252" height="70"/><rect x="900" y="176" width="252" height="70"/><rect x="900" y="308" width="252" height="70" stroke="#176AC6"/>
  </g>
  <g fill="#171A1F" text-anchor="middle">
    <text x="75" y="124">Gmail</text><text x="75" y="224">Telegram</text>
    <text x="305" y="160" font-weight="600">worker</text><text x="305" y="186" style="font-size: 15px" fill="#5b6472">adapters · scheduler</text>
    <text x="640" y="74">Ingestion</text><text x="640" y="152">LLM extraction · advisory</text>
    <text x="640" y="230" font-weight="600">Site record · Postgres</text><text x="640" y="308">Rules → Flag</text><text x="640" y="378">Outbox</text>
    <text x="1026" y="76" font-weight="600">web</text><text x="1026" y="100" style="font-size: 15px" fill="#5b6472">dashboard · 3D</text>
    <text x="1026" y="208" font-weight="600">mcp</text><text x="1026" y="232" style="font-size: 15px" fill="#5b6472">9 tools</text>
    <text x="1026" y="338" fill="#176AC6" font-weight="600">any agent</text><text x="1026" y="362" style="font-size: 15px" fill="#176AC6">e.g. Talona's</text>
  </g>
  <text x="472" y="26" style="font-family: JetBrains Mono; font-size: 15px" fill="#5b6472">api · the only service with DB access</text>
  <g stroke="#171A1F" stroke-width="1.5" fill="none" marker-end="url(#ar)">
    <path d="M150,117 L218,150"/><path d="M150,217 L218,186"/>
    <path d="M390,150 L488,68"/>
    <path d="M640,92 L640,120"/><path d="M640,170 L640,198"/><path d="M640,248 L640,276"/><path d="M640,326 L640,346"/>
    <path d="M490,372 L330,372 L330,216"/>
    <path d="M898,79 L792,224"/><path d="M898,211 L792,230"/><path d="M1026,306 L1026,248"/>
  </g>
</svg>

<div class="cite" style="font-size: 17px">5 services · <b>docker compose up</b> · 761 tests in CI, all offline</div>

<!--
Five services, one docker compose up.
Mail and chat come in through the worker and one ingestion entry point. The LLM only extracts claims. Only the api touches the database. Rules raise Flags, and every outgoing message goes through an outbox.
Dashboard and MCP use the same REST API, so any agent, also Talona's, can plug in.
-->

---
sheet: Trust & compliance
---

# The LLM advises. People decide.

<div style="position: absolute; left: 64px; top: 140px; width: 640px; font-size: 22px">
  <div style="display: grid; grid-template-columns: 1fr 92px 92px 92px; border-top: 1.5px solid #171A1F">
    <span></span><span class="label" style="text-align: center; padding: 10px 0">LLM</span><span class="label" style="text-align: center; padding: 10px 0">Rules</span><span class="label" style="text-align: center; padding: 10px 0">Person</span>
  </div>
  <div v-for="row in [['Extract claims', 'unconf.', '', ''], ['Raise a Flag', '', '■', ''], ['Confirm evidence', '', '', '■'], ['Approve a proposal', 'propose', '', '■'], ['Close a Flag', '', '', '■ + reason']]" :key="row[0]" style="display: grid; grid-template-columns: 1fr 92px 92px 92px; border-top: 1px solid rgba(23,26,31,.35); padding: 12px 0; align-items: center">
    <span>{{ row[0] }}</span>
    <span v-for="(c, i) in row.slice(1)" :key="i" class="mono" :style="{ textAlign: 'center', fontSize: c.length > 1 ? '15px' : '22px', color: i === 0 ? '#5b6472' : '#176AC6' }">{{ c }}</span>
  </div>
  <p class="mono muted" style="font-size: 16px; margin-top: 14px">Every state change in the audit trail: who, when, channel, source.</p>
</div>

<div style="position: absolute; left: 770px; top: 150px; width: 440px; display: flex; flex-direction: column; gap: 22px; font-size: 24px; line-height: 1.3">
  <div class="label">Privacy by design</div>
  <p><b>No per-person metrics.</b> Flags belong to zones, tasks and trades.</p>
  <p><b>The LLM sees text and role only.</b> Phone numbers, emails, usernames masked.</p>
  <p><b>Telegram:</b> allowlisted chats, retention period, <span class="mono" style="font-size: 20px">/delete_my_data</span>.</p>
  <p><b>Synthetic data only</b> in this demo.</p>
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

<div style="position: absolute; left: 64px; right: 64px; top: 170px; display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; font-size: 22px; line-height: 1.3">
  <div class="box"><div class="label">Day 3 · 09:10</div><p style="margin-top: 8px">"Können wir morgen früh 3B zumachen?"</p><p class="muted" style="margin-top: 8px; font-size: 19px">misread as planned work → Flag</p></div>
  <div class="box"><div class="label">Feedback</div><p style="margin-top: 8px">A person closes it as <b>false alarm</b>: "question, not announcement"</p></div>
  <div class="box"><div class="label">Site Knowledge</div><p style="margin-top: 8px">Correction stored, linked to feedback and source</p></div>
  <div class="box" style="border-color: #176AC6"><div class="label blue">Day 3 · 09:12</div><p style="margin-top: 8px">Same message → read as a question</p><p class="blue" style="margin-top: 8px; font-size: 19px">no Flag</p></div>
</div>

<div style="position: absolute; left: 64px; top: 440px; display: flex; align-items: center; gap: 18px; font-size: 24px">
  <span class="mono blue" style="font-size: 20px">Day 3 · 09:15</span><span>"heute früh machen wir 3B zu"</span><span class="chip crit">Flag A · still raised</span>
</div>

<p style="position: absolute; left: 64px; top: 520px; max-width: 980px; font-size: 24px">Learning fixes the reading, never the safety check. The dashboard tracks the share of confirmed Flags over time.</p>

<!--
Learning, from our replay. A question, "Können wir morgen früh 3B zumachen?", is misread as an announcement and raises a Flag.
The superintendent closes it as a false alarm and marks the extraction wrong. Next time the same message is read as a question.
But a real announcement still raises Flag A. Learning fixes the reading, never the safety check.
-->

---
sheet: Vision
---

# One site today. Every site next.

<div style="position: absolute; left: 64px; right: 64px; top: 170px; display: grid; grid-template-columns: 1fr 1fr; gap: 24px 48px; font-size: 26px; line-height: 1.3">
  <div class="box" style="border-color: #176AC6"><span class="chip ok">built</span><p style="margin-top: 12px"><b>MCP server for any agent.</b> Talona's own agent can plug in, with the tools our Q&A uses.</p></div>
  <div class="box"><span class="chip grey">next</span><p style="margin-top: 12px"><b>Learning across projects.</b> What one site learns, the next one knows.</p></div>
  <div class="box"><span class="chip grey">next</span><p style="margin-top: 12px"><b>Photos checked against plans.</b> "Wall is closed" as a claim to review.</p></div>
  <div class="box"><span class="chip grey">next</span><p style="margin-top: 12px"><b>Context for robots.</b> Which plan and precondition apply, right here.</p></div>
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

<img src="/groundiq-logo-white.svg" style="height: 56px; margin-top: 24px" alt="GroundIQ" />

<h1 style="margin-top: 40px">Decisions stop getting lost<br>between mail and chat.</h1>

<div class="label" style="margin-top: 8px">Built in 24 hours</div>

<div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px 40px; margin-top: 20px; font-size: 24px; max-width: 1100px; color: #C9D1DB">
  <span>Conflicts A + B from mail, chat and DXF</span>
  <span>Gmail and Telegram, in and out</span>
  <span>3D site model from plan geometry</span>
  <span>9 MCP tools for any agent</span>
  <span>Offline replay of the hero week</span>
  <span>761 tests · one docker compose up</span>
</div>

<div class="label" style="margin-top: 44px">github.com/davidsteindl/ProximataHackathon · 3-min video: see submission</div>

<!--
Back to the start: three messages nobody connected. GroundIQ connects them before the wall is closed.
All of this was built in 24 hours and runs with one docker compose up. Thank you, we are happy to take questions.
-->
