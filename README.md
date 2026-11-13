# Puntimata

## Links

**Google Docs:**
https://docs.google.com/document/d/191BTonyg6-m5O6dTQWNTi6LpWj3htCbGVGOswbQmgXY/edit?usp=sharing

**Excalidraw Whiteboard:**
https://excalidraw.com/#room=ac3240648cf122511709,arFEEYfSUXenyB8QTL0RbQ

**Projektplan:** [docs/PLAN.md](docs/PLAN.md)

## Architektur

Die Diagramme hier sind die Grundlage für die Implementierung. Begriffe wie Flag, Event oder Precondition stehen in [PLAN.md §2](docs/PLAN.md). Wer die Architektur ändert, passt zuerst das Diagramm per PR an.

**Bearbeiten:** Die Quelle ist der Mermaid-Code in dieser Datei. Für das Whiteboard einen Block kopieren und in Excalidraw über *Weitere Werkzeuge → Mermaid zu Excalidraw* einfügen. Änderungen am Whiteboard danach hier im Code nachziehen.

### 1. Dienste und Kanäle

```mermaid
flowchart LR
  classDef ext fill:#f4f4f5,stroke:#71717a,color:#18181b
  classDef svc fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
  classDef store fill:#dcfce7,stroke:#16a34a,color:#14532d
  classDef person fill:#fef3c7,stroke:#d97706,color:#78350f

  SUP(["Superintendent"]):::person
  CREW(["Crews · Crew Leads"]):::person
  ARCH(["Architekt · Inspektor"]):::person

  subgraph KANAL["Bestehende Kanäle der Baustelle"]
    GMAIL["Gmail<br/>Projektpostfach"]:::ext
    TG["Telegram<br/>Crew-Gruppen"]:::ext
  end

  SEED["Seed-Dateien<br/>Terminplan · Gebäude-Metadaten · DWG-Pläne"]:::ext
  REPLAY["Replay-Skript<br/>Demo · Reset"]:::ext
  LLM["LLM-Provider<br/>austauschbar"]:::ext
  EXTAG["Externer Agent<br/>z. B. Talona"]:::ext

  subgraph SITEMIND["SiteMind · docker compose"]
    WEB["web<br/>Next.js · Dashboard · 3D · Chat"]:::svc
    API["api<br/>FastAPI · Context Engine"]:::svc
    WORKER["worker<br/>Kanal-Adapter · Scheduler"]:::svc
    MCP["mcp<br/>MCP-Server"]:::svc
    DB[("db<br/>PostgreSQL")]:::store
  end

  ARCH -->|"Mails, DWG-Revisionen"| GMAIL
  CREW <-->|"Chat"| TG
  GMAIL -.->|"Warnungen, Freigabe-Anfragen"| SUP
  SUP -->|"Browser"| WEB
  GMAIL <-->|"Gmail API: Polling / Senden"| WORKER
  TG <-->|"Bot API: Polling / Senden"| WORKER
  WORKER -->|"REST: Ingest, Outbox, Trigger"| API
  WEB -->|"REST"| API
  MCP -->|"REST"| API
  API -->|"MCP (Chat-Agent)"| MCP
  EXTAG -->|"MCP"| MCP
  API <-->|"SQL"| DB
  API -.->|"Extraktion, Erklärung, Chat"| LLM
  SEED -->|"Seed-Import"| API
  REPLAY -->|"echte Mails"| GMAIL
  REPLAY -->|"echte Nachrichten"| TG
  REPLAY -.->|"Offline-Modus: Ingest"| API
```

### 2. Vom Eingang zum Flag (in `api`)

Durchgezogene Pfeile sind der Hauptfluss, gestrichelte die Rückkopplung aus dem Learning Loop.

```mermaid
flowchart TD
  classDef llm fill:#ede9fe,stroke:#7c3aed,color:#3b0764
  classDef rule fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
  classDef store fill:#dcfce7,stroke:#16a34a,color:#14532d
  classDef human fill:#fef3c7,stroke:#d97706,color:#78350f

  IN["Source Message<br/>Mail · Chat · Seed · Replay"] --> TYP{"Inhalt?"}
  TYP -->|"Text"| EXTR["LLM-Extraktion<br/>wer · Zone · was · wann · Absicht"]:::llm
  TYP -->|"DWG-Anhang"| CONV["DWG → DXF<br/>externer Konverter"]:::rule
  CONV --> GEO["Geometrie-Extraktion<br/>Räume · Wände · Bauteile → Zonen"]:::rule
  GEO --> DIFF["Plan-Diff<br/>zur vorherigen Revision"]:::rule
  EXTR --> EV["Event"]
  DIFF -->|"betroffene Zonen"| EV
  GEO -->|"Geometrie für 3D und Agent"| REC
  EV --> REC[("Site Record<br/>Zonen · Tasks · Revisionen · Inspections · Events")]:::store
  SCAN["Morgen-Scan<br/>täglich, ausgelöst vom worker"] --> RULES
  REC --> RULES{"Regel-Engine<br/>Preconditions erfüllt?"}:::rule
  RULES -->|"ja"| OK["kein Flag"]
  RULES -->|"nein"| DEDUP{"Offener Flag für<br/>denselben Konflikt?"}:::rule
  DEDUP -->|"ja"| ATT["an bestehenden Flag anhängen"]
  DEDUP -->|"nein"| NEW["neuer Flag<br/>+ verantwortliche Person"]
  NEW --> ADV["Advisor<br/>Erklärung · Proposal"]:::llm
  ADV --> OUT["Outbox"]
  OUT -->|"Fakten: automatisch"| CL(["Crew Lead"]):::human
  OUT -->|"Proposal: braucht Freigabe"| SUP(["Superintendent"]):::human
  CL -->|"zur Kenntnis genommen"| LIFE["Flag-Lebenszyklus<br/>+ Audit-Trail"]:::rule
  SUP -->|"Freigabe · Feedback"| LIFE
  LIFE -->|"Abschluss mit Feedback"| LEARN["Learning Loop"]
  LEARN --> SK[("Site Knowledge")]:::store
  SK -.->|"Kontext"| EXTR
  SK -.->|"Unterdrückung / Anpassung"| RULES
```

### 3. Flag-Lebenszyklus

```mermaid
flowchart LR
  classDef open fill:#fee2e2,stroke:#dc2626,color:#7f1d1d
  classDef closed fill:#dcfce7,stroke:#16a34a,color:#14532d

  E["erkannt"]:::open -->|"System"| B["benachrichtigt"]:::open
  B -->|"keine Reaktion nach X h:<br/>Eskalation an nächsthöhere Stelle"| B
  B -->|"verantwortliche Person:<br/>Feedback bestätigt"| K["zur Kenntnis genommen"]:::open
  K -->|"Superintendent gibt Maßnahme frei"| I["in Bearbeitung"]:::open
  I -.->|"System: Precondition jetzt erfüllt,<br/>nur Hinweis, kein Abschluss"| I
  I -->|"Mensch: Feedback erledigt"| D["erledigt"]:::closed
  B -->|"Mensch: Feedback Fehlalarm"| F["Fehlalarm"]:::closed
  K -->|"Mensch: Feedback Fehlalarm"| F
  I -->|"Mensch: Feedback Fehlalarm"| F
```

### Architekturregeln

- **`api` ist der einzige Dienst mit Zugriff auf die DB.** `worker`, `mcp` und `web` sprechen ausschließlich über die REST-API (OpenAPI-Vertrag).
- **Alle Quellen laufen über einen Ingestion-Eingang.** Ein neuer Kanal (z. B. WhatsApp) ist nur ein neuer Adapter im `worker`.
- **Ausgehende Nachrichten laufen über eine Outbox.** `api` legt jede Nachricht als Eintrag an, `worker` versendet und meldet den Status zurück. Keine Nachricht geht verloren, und jede steht im Audit-Trail.
- **Das LLM berät nur** (lila im Diagramm 2). Flags entstehen ausschließlich durch die Regel-Engine, Handlungen und Abschlüsse nur durch Menschen.
- **Der Chat-Agent nutzt dieselben MCP-Tools wie externe Agents.** Was unser Chat kann, kann auch Talonas Agent.
- **Kanal-Zugangsdaten** (Gmail, Telegram) liegen nur im `worker`, der LLM-Key nur in `api`.
