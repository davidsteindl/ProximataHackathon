# Puntimata

## Frontend Design-Mockup
[https://claude.ai/artifact/3MjWimC7hjDSDSK9RqtxxN#page-dcb81aee8d83](https://claude.ai/artifact/3MjWimC7hjDSDSK9RqtxxN#page-dcb81aee8d83)

## Lokal starten (Issue #2)

Voraussetzung: Docker mit Compose v2 und laufender Docker Engine (Linux-Container).
Die Basis-Images unterstützen x64 und ARM64; es wird keine Plattform erzwungen.

```sh
cp .env.example .env
docker compose up --build
```

In PowerShell statt `cp`: `Copy-Item .env.example .env`. Beim ersten Start baut auch
`docker compose up` die noch fehlenden Images; nach Codeänderungen `--build` verwenden.

- Dashboard: http://localhost:3000 – zeigt den aktuellen API- und DB-Status.
  Der Next.js-Server fragt dafür die API ab, die mit `SELECT 1` PostgreSQL prüft.
  Zum Aktualisieren die Seite neu laden.
- Statischer Site Record (Issue #5): Nach dem Start in einem zweiten Terminal
  `docker compose exec api python -m app.seed` ausführen. Das Dashboard zeigt dann
  Zonen, Terminplan, Crews, Revisionen/Bestätigungen und Inspections.
  Evidence mit Quelle, genauem Geltungsbereich und Prüf-Historie steht unter
  `/evidence` sowie lesend im Dashboard. Synthetische Ausgangsnachweise sind
  von unbestätigten Aussage-Beispielen getrennt; Seed-Herkunft ersetzt keine
  erfundene menschliche Freigabe. Der explizite Demo-Reset setzt auch diese
  Nachweise samt Historie zurück. Extraktion (#6) und menschliche Prüf-Aktion
  (#9) verwenden den Vertrag in [SITE_RECORD.md](docs/SITE_RECORD.md).
  Derselbe Befehl setzt die statischen Daten auf den Seed-Ausgangszustand zurück.
  Format, Zonen-IDs für #3, REST-Vertrag und Migrationen: [docs/SITE_RECORD.md](docs/SITE_RECORD.md).
- API-Health: http://localhost:8000/health – `200` mit
  `{"api":"ok","db":"ok"}`, bei DB-Ausfall `503` mit `db: "error"`.
- CAD-Geometrie (#15): Nach dem Seed-Import
  `docker compose exec api python -m app.cad_import` ausführen. Importiert alle fünf
  DXFs aus #3 samt Metadaten; Originaldateien bleiben je Revision gespeichert.
  Geometrie in Metern unter `/geometry?floor_id=F3` bzw.
  `/geometry?zone_id=3B&revision_id=A-103-D`. API-/Importvertrag und 3D-Koordinaten:
  [docs/CAD-PIPELINE.md](docs/CAD-PIPELINE.md). Ein Seed-Reset entfernt auch die
  daraus abgeleitete Geometrie; danach den CAD-Import erneut ausführen.
- 3D-Baustellenansicht (#16): http://localhost:3000/site, Raumansicht unter
  `/zones/<zoneId>` (z. B. `/zones/3B-BATH`, teilbarer Link). Braucht Seed,
  CAD-Import und für Flag A die Hero-Nachricht unten. Das Gebäude wird nur aus
  `/geometry` erzeugt (Wände auf Geschosshöhe extrudiert, Räume, Türen, Sanitär,
  Abwasser); Kräne, Gerüst, Zaun, Bäume und Container sind als dekorativer
  Kontext gekennzeichnet. Status kommt aus `/flags`, `/inspections`, `/evidence`
  und wird alle 3 s über `web` (`/api/site-state`) nachgeladen, ohne Reload.
  Die Ansicht liest nur; Evidence-Prüfung und Flag-Abschluss bleiben getrennte
  menschliche Aktionen. Flag-Detail (lesend): `/flags/<id>`.
- OpenAPI: http://localhost:8000/openapi.json, interaktive Dokumentation unter `/docs`.
- MCP: http://localhost:8001/mcp – Streamable HTTP mit neun Kontext-Tools,
  Verbindung und Beispiele unter [MCP-Verbindung](#mcp-verbindung-issue-18).
- `docker compose logs worker mcp` zeigt den erfolgreichen API-Zugriff beider Dienste.
  Der Worker wiederholt die Prüfung alle 30 Sekunden; MCP prüft beim Start.

`.env.example` enthält alle derzeit benötigten Einstellungen: lokale DB-Zugangsdaten,
Host-Ports und `API_BASE_URL` (Compose-intern, standardmäßig `http://api:8000`).
Das Beispielpasswort ist ausschließlich für lokale Entwicklung. `.env` wird nicht
versioniert. Nur `api` liegt im DB-Netz und erhält DB-Zugangsdaten; die übrigen
Anwendungsdienste verwenden die REST-API.

Stoppen: `docker compose down`. Die Daten bleiben im Volume `db-data` erhalten.
`docker compose down --volumes` löscht auch die lokalen Daten.

Enthalten sind Infrastruktur, Health-Prüfungen, der statische Site Record aus
Issue #5, Nachrichten-Ingestion, Event-Extraktion und Timeline aus #6 sowie
DXF-Extraktion und Geometrie-API aus #15, Conflict A und Flag-Inbox aus #7,
Conflict B aus Revisionsnotizen (#8), Gmail-Eingang aus #11,
Outbox-/Gmail-Versand aus #10 sowie die 3D-Ansicht aus #16 und der DXF-Plan-Diff
aus #17 sowie MCP-Kontext-Tools aus #18. Telegram-Adapter, Authentifizierung
und Hosting folgen in ihren eigenen Issues.

### MCP-Verbindung (Issue #18)

Nach `docker compose up --build` und dem Seed-Import verbindet sich ein beliebiger
MCP-Client per **Streamable HTTP** mit `http://localhost:8001/mcp`.
Bei geändertem `MCP_PORT` den Port anpassen; Compose-interne Clients verwenden
`http://mcp:8001/mcp`. Keine API-, DB- oder LLM-Zugangsdaten im Client hinterlegen.

Zum manuellen Testen `npx @modelcontextprotocol/inspector` starten, in dessen UI
**Streamable HTTP** wählen, die URL eintragen und verbinden. Unter **Tools**
`get_zone_status` mit `{"zone_id":"3B"}` aufrufen: Die Antwort enthält die
Wohnung und Unterzonen, den auch für 3B geltenden Etagen-Terminplan, Inspections,
Evidence mit Prüfstatus, deterministische Preconditions, offene Flags und Quellen.
Vor einer Arbeitsankündigung ist ein nicht ausgewerteter Task ausdrücklich
`unknown`, nicht freigegeben. Nach der Hero-Nachricht aus dem Abschnitt unten
erscheint Flag A; auch hochkonfidente LLM-Aussagen bleiben `unconfirmed`.

| Tool | Verwendung |
|---|---|
| `list_zones` | Zonen-IDs und Gebäudehierarchie entdecken |
| `get_zone_status(zone_id)` | Status inklusive abdeckender übergeordneter Records; keine Geschwister-only-Records |
| `list_flags(status="open")` | Offene, geschlossene oder alle Flags mit Quellen und Historie |
| `get_flag(flag_id)` | Flag-Detail, Prüfstatus und Audit |
| `get_timeline(zone_id?, from_time?, to_time?, limit=100)` | Events, Evidence-Entscheidungen, Flag-Audit, Revisionen |
| `search_record(query, zone_id?, limit=50)` | Wörtliche, nicht semantische Suche im Record |
| `get_zone_plan(zone_id, revision_id?)` | Importierte DXF-Elemente in Metern; standardmäßig letzte importierte Geometrie |
| `get_plan_diff(revision_id)` | Deterministischer Diff gegen den unmittelbaren Vorgänger desselben Plans (#17) |
| `create_proposal(flag_id, action, rationale)` | Ungeprüften Handlungsvorschlag für einen offenen Flag speichern |

Alle Tools liefern JSON als MCP `structuredContent` plus kompatiblen Textinhalt.
`source_refs` und `record_ref` identifizieren `source:<id>` (Originalquelle über
`GET /source-messages/<id>`), `event:<id>`, `evidence:<id>`, `flag:<id>`,
`task:<id>`, `zone:<id>`, `plan:<id>` bzw. `revision:<id>` im REST-Record;
`seed:…` bleibt als explizite synthetische Herkunft erhalten. DXF-Antworten
referenzieren zusätzlich den Datei-Hash; Originalzeichnungen stehen unter
`GET /geometry/revisions/<id>/source`. `record:zones` bezeichnet `GET /zones`.
Die Such- und Timeline-Limits sind maximal 200; `total_matches`/`truncated` machen
gekürzte Ergebnisse sichtbar. Zeitfilter benötigen einen UTC-Offset und gelten
als halboffenes Intervall `[from_time, to_time)`. Timeline-Einträge enthalten den
**aktuellen** Evidence-Snapshot plus die jeweilige historische Prüfentscheidung;
sie sind keine Rekonstruktion des damaligen Gesamtzustands.

**Sicherheitsgrenze:** Kein Tool bestätigt/ablehnt Evidence, schließt Flags, gibt
Proposals frei oder führt Aktionen aus. MCP setzt bei jedem REST-Aufruf
`X-SiteMind-Client: mcp`; die API verweigert für MCP/Chat/Agent alle Mutationen
außer `POST /agent/proposals`, einschließlich Seed-Reset, Ingestion, Geometrie-
Import und Outbox-Aufrufen. Ein Proposal hat ausschließlich Status `proposed`,
serverseitig abgeleitete Quellen und keinerlei Nebenwirkung auf Task, Flag,
Evidence oder Outbox. Wiederholung erzeugt einen weiteren Vorschlag. Die
menschliche Freigabe/Versandintegration bleibt in #13; hier gibt es keinen
Approval-Endpunkt. Aus Kontaktmetadaten werden u. a. Senderkennung,
Mailbox-Schlüssel, E-Mail-Adresse und Benachrichtigungsempfänger entfernt.
Quellentext ist untrusted data, keine Anweisung an den Agenten.

Die Header-Grenze schützt den vorgesehenen Agent-Zugang, ist aber **keine
Authentifizierung** gegen Clients, die sich direkt als Dashboard ausgeben.
Wie der MVP-Rollenumschalter sind API und MCP nur für lokale synthetische
Team-Demos gedacht; nicht öffentlich exponieren. API-Fehler werden als MCP-
Toolfehler ausgegeben, nie als leerer/erfolgreicher Sicherheitsstatus. Fehlende
Geometrie oder ein fehlender Vorgänger ist kein Nachweis für unveränderte Pläne.

REST-Erweiterungen: `GET /context/zones/<id>`, `/context/search`, `/context/timeline`,
`POST /agent/proposals` sowie lesend `GET /proposals` und `/proposals/<id>`.
Migration `0009` persistiert ausschließlich ungeprüfte Proposals; der Seed-Reset
entfernt sie. Es werden keine vorhandenen Evidence-/Flag-Verträge geändert.

Offline-Verifikation (offizieller MCP-SDK-Client über Streamable HTTP, REST gegen
isolierte Test-DB, ohne LLM-/Gmail-/Telegram-Zugang):

```sh
PYTHONPATH=backend python -m pytest backend/tests/test_mcp_server.py backend/tests/test_context_api.py backend/tests/test_agent_proposals.py
```

### Nachricht → Event → Timeline (Issue #6)

Nach `docker compose up --build` und dem Seed-Import kann die synthetische
Hero-Nachricht ohne LLM-Key oder Internet verarbeitet werden:

```sh
curl http://localhost:8000/ingestion/messages \
  -H 'Content-Type: application/json' \
  --data-binary @backend/demo/closing-work.json
```

In PowerShell `curl.exe` verwenden und den Befehl in eine Zeile schreiben.
Bei geändertem `API_PORT` die URL anpassen. Danach das Dashboard neu laden:
Die Event-Timeline zeigt die Arbeitsankündigung für 3B samt Originalquelle und
Zeitfenster am Folgetag. Wiederholtes Senden liefert dieselben Event-IDs.
Irrelevante Nachrichten bleiben als Quellen gespeichert, erzeugen aber keine Events.
Die Timeline nutzt dieselben Zonen-/Datumsfilter wie der Terminplan; ihre Daten
beziehen sich auf den Zeitpunkt der ursprünglichen Nachricht.

`LLM_PROVIDER=cached` nutzt ausdrücklich synthetische Extraktionsergebnisse für
die dokumentierten Hero-Nachrichten. Andere Texte melden `cache_miss`, ohne einen
Live-Aufruf auszulösen. Für beliebige Texte `LLM_PROVIDER=openai_compatible`,
`LLM_BASE_URL`, `LLM_MODEL` und `LLM_API_KEY` für einen JSON-Mode-fähigen Provider
in `.env` setzen und `api` neu erstellen. Nur `api` erhält den LLM-Key.

Abnahme-, Task-Abschluss- und Revisionsbestätigungen aus Nachrichten werden immer
als **unbestätigte Evidence** mit Quelle/Zitat gespeichert. Sie überschreiben keine
vorhandene Bestätigung und geben keine Arbeit frei. Die menschliche Prüfung folgt
in #9. Conflict A und B werden bereits deterministisch geprüft.
Der Seed-Befehl setzt auch die neuen Nachrichten
und Events zurück. REST-Vertrag, Cache-Inhalte, Fehler-/Retry-Verhalten und
Datenschutzgrenzen: [docs/INGESTION.md](docs/INGESTION.md).

### Conflict A und Flag-Inbox (Issue #7)

Nach der Hero-Nachricht zeigt `GET /flags` den offenen Flag A für 3B mit
Quellzitat, betroffener Task, erforderlicher Rohinstallationsabnahme und
verantwortlichem Crew Lead. `GET /flags/{id}` liefert die Details. Wiederholte
Erkennung ergänzt den bestehenden offenen Flag. Die Regel bewertet Nachweise
als erfüllt, nicht erfüllt, unbekannt oder widersprüchlich; eine unbestätigte
Erfolgsmeldung reicht nie als Freigabe. Neue Events und menschliche
Nachweisentscheidungen lösen die Prüfung in derselben Transaktion aus.
Ein später erfüllter Nachweis schließt keinen Flag.

Migration `0005` ergänzt Flags, Quellenverknüpfungen und Audit; der Seed-Reset
entfernt diese Daten mit. Die Inbox ist lesend; menschliche Lifecycle- und Nachweisaktionen ergänzt #9
(siehe unten). Details zu Regel,
Nachweisgültigkeit und Integration für #8/#9/#14: [docs/FLAGS.md](docs/FLAGS.md).

### Flag-Lifecycle und Nachweisprüfung (Issue #9)

`POST /flags/{id}/actions` speichert menschliche Kenntnisnahme (`confirmed`)
oder Abschluss (`resolved` / `false_alarm`) mit Begründung und vollständigem
Audit. `GET /flags?status=closed` hält abgeschlossene Flags samt Feedback
zugänglich. Systemsignale für Benachrichtigung (#10), freigegebene Maßnahmen
(#13) und Eskalation (#14) nutzen den gemeinsamen API-internen Lifecycle.

Die separate Dashboard-Aktion `POST /evidence/{id}/reviews` bestätigt/ablehnt
quellengebundene Nachweise mit genauem Geltungsbereich, auch ohne Flag. Jede
Entscheidung prüft die Regeln erneut; ein erfüllter Nachweis lässt den Flag offen
und setzt nur `awaiting_human_closure`. Kenntnisnahme, Nachweisentscheidung,
Proposal-Freigabe und Abschluss bleiben getrennt. Der Rollenumschalter verwendet
synthetische Identitäten und ist keine produktionsreife Authentifizierung.
MCP/Chat-Kanäle dürfen diese Aktionen nicht ausführen. REST-Payloads,
Übergänge, Rollen und Integrationsgrenzen: [docs/FLAGS.md](docs/FLAGS.md#lifecycle-and-evidence-review-9).
### Conflict B aus Revisionsnotizen (Issue #8)

Nach dem Seed dieselbe Ingestion mit `backend/demo/revision-note.json` aufrufen
(gleicher curl-Befehl wie oben, mit diesem Dateinamen). Die Hero-Notiz von Tag 1,
10:15 Uhr, registriert A-103 Rev D auch ohne CAD-Import und erzeugt Flag B für
die Sanitär-Crew in 3B: bestätigter Empfang C, erforderlich D. Ebenfalls betroffene
geplante Arbeiten werden geprüft. Die Inbox zeigt Crew, Revisionen, Quellen und
den **unbestätigten** Zonenbezug aus der Notiz. Danach die Closing-Work-Nachricht
senden: Für die Trockenbau-Arbeit in 3B erscheinen A und B.

Eine spezifische Empfangsmeldung bleibt unbestätigte Evidence. „Warnung gesehen“
bestätigt keinen Revisionsempfang; auch bestätigter Empfang belegt keine Umsetzung.
Migration `0006` erlaubt `file_name: null` für reine Notizrevisionen und ergänzt
`Flag.context` mit Crew, Plan sowie erforderlicher und bestätigter Revision.
CAD-Import kann die vorläufigen Metadaten derselben Revision vervollständigen;
dabei entstehen weder geometrische Änderungszonen noch Empfangsbestätigungen.
Details und Tests: [docs/FLAGS.md](docs/FLAGS.md).

### Outbox-Vertrag (Issue #10)

Migration `0007` ergänzt optionale `crew_leads.email` (auch im Seed-/Crew-REST-Vertrag)
und eine transaktionale Outbox: genau eine faktische Gmail-Warnung pro neuem Flag.
`GET /outbox?flag_id=…` zeigt Status und Versuche. Der Worker reserviert über
`POST /outbox/claim` eine Nachricht für fünf Minuten und meldet mit Lease-Token
über `POST /outbox/{id}/result` Erfolg oder Fehler. Fehler werden mit Backoff
(60 Sekunden bis eine Stunde) erneut versucht. Nur bestätigter Versand setzt
einen noch `detected` Flag auf `notified`; menschliche Zustände bleiben erhalten.
Versandversuche und Ergebnisse stehen im Flag-Audit. Der Demo-Reset leert die Outbox.

Versand aktivieren: Crew-Lead-Testadresse im Seed hinterlegen, OAuth mit
`python -m app.gmail_auth --send` erneut autorisieren und `GMAIL_SEND_ENABLED=true`
setzen. Fehlende Adressen werden als Versandfehler sichtbar. Einrichtung, Hero-Test
und Grenzen (Gmail-Annahme, mögliche Duplikate bei unklarem Versandresultat):
[docs/GMAIL.md](docs/GMAIL.md#factual-flag-warnings-outbox).

### DXF-Plan-Diff (Issue #17)

Vor dem Hero-Replay mindestens `A-103_RevC.dxf` über den CAD-Import laden.
Die Hero-Mail mit `A-103_RevD.dxf` läuft über `/ingestion/messages`: Der Vergleich
C → D liefert ausschließlich 3B und löst dort Conflict B aus. Die Originalnotiz
bleibt als Erklärung erhalten. `GET /geometry/revisions/A-103-D/diff` liefert
die geänderten Elemente mit alter/neuer Geometrie, gruppiert nach Wohnung.
Identische Geometrie ergibt einen leeren Diff und keine betroffenen Zonen.

Schlägt der Vergleich fehl, prüft B weiter die unbestätigten Notizzonen; die Inbox
zeigt den Fallback samt Fehlergrund. Ein erfolgreicher Diff ersetzt keine
menschlich bestätigte Empfangs-Evidence. Dateinamen, Metadaten, Herkunft und
Fehlerverhalten: [CAD-PIPELINE.md](docs/CAD-PIPELINE.md#plan-diff-17).

### Gmail-Eingang (Issue #11)

Der optionale Worker-Adapter liest ein verifiziertes Projekt-Testpostfach/Label
und übergibt Betreff, Text und Originalanhänge an dieselbe Ingestion. Bereits
verarbeitete Quellen werden über eine exakte REST-Abfrage nach Kanal, Konto und
Gmail-ID übersprungen. Einrichtung und Grenzen: [docs/GMAIL.md](docs/GMAIL.md).
Die OAuth-Zugangsdaten erhält ausschließlich der Worker; ohne Konfiguration
bleibt Gmail deaktiviert.

Kurzsetup: Gmail API im Team-Cloud-Projekt aktivieren, OAuth-Consent im Testmodus
konfigurieren und das Projekt-Testkonto als **Test user** eintragen. Einen OAuth-
Client vom Typ **Desktop app** anlegen; dessen JSON lokal unter
`.gmail/client-secret.json` speichern. Nach Installation der Backend-Abhängigkeiten
vom Repository-Root aus autorisieren:

```powershell
$env:PYTHONPATH = 'backend'
python -m app.gmail_auth
```

Im Browser das Projektkonto auswählen. Danach in `.env` `GMAIL_ENABLED=true`,
`GMAIL_MAILBOX=<Projektkonto>` und optional `GMAIL_LABEL=<exakter Labelname>` setzen;
`GMAIL_POLL_SECONDS=15` steuert die Pause zwischen Polls. Mit
`docker compose up --build -d worker` starten (Seed-Baseline muss vorhanden sein).
Nur `gmail.readonly` wird angefordert. `.gmail/` bleibt lokal und wird nur in den
Worker gemountet. **External/Testing:** Ohne eingetragenen Testnutzer scheitert die
Anmeldung; Refresh-Tokens für Gmail laufen nach **7 Tagen** ab. Dann die lokale
Autorisierung erneut ausführen. Vollständige Schritte, Hero-Mails und Fehlerhilfe:
[docs/GMAIL.md](docs/GMAIL.md).

### Telegram-Ein-/Ausgang (Issue #12)

Opt-in Polling im `worker`, Chat- **und** Nutzer-Allowlist, Transparenz beim
Gruppenbeitritt, private `/my_data`- und `/delete_my_data`-Kommandos sowie
konfigurierbare Rohdaten-Retention. Warnungen und Compliance-Antworten laufen
über die kanalgebundene Outbox; der Bot-Token bleibt ausschließlich im Worker.
Setup, REST-/Schemaänderungen und Grenzen der Löschung: [Telegram](docs/TELEGRAM.md).

### Lokale Checks

Backend (Python 3.13, aus dem Repository-Ordner):

```sh
python -m venv .venv
# Aktivieren: Windows .venv\Scripts\Activate.ps1; Linux/macOS source .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
cd backend
python -m pytest tests
```

Frontend (Node.js 22, aus dem Repository-Ordner):

```sh
cd web
npm ci
npm test
npm run lint
npm run build
```

Compose-Konfiguration (aus dem Repository-Ordner):

```sh
docker compose --env-file .env.example config --quiet
```

Diese Checks laufen bei jedem Pull Request und bei Pushes auf `main` in GitHub Actions.

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

  SEED["Seed-Dateien<br/>Terminplan · Gebäude-Metadaten · DXF-Pläne"]:::ext
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

  ARCH -->|"Mails, DXF-Revisionen"| GMAIL
  CREW <-->|"Chat"| TG
  GMAIL -.->|"Warnungen, Freigabe-Anfragen"| SUP
  SUP <-->|"Raumstatus-Fragen, Links ins Dashboard"| TG
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

Der gemeinsame REST-Eingang ist `POST /ingestion/messages`; `GET /events` liefert
die quellengebundene Timeline. Quellen und Originalanhänge werden vor der
Extraktion gespeichert. Details zum Vertrag: [INGESTION.md](docs/INGESTION.md).

Durchgezogene Pfeile sind der Hauptfluss, gestrichelte die Rückkopplung aus dem Learning Loop. LLM-Events sind Aussagen mit Prüfstatus. Sie dürfen sofort Prüfungen auslösen; als Nachweis zur Erfüllung einer Precondition zählen sie erst nach einer expliziten menschlichen Bestätigung im Dashboard. Bestätigungsstatus und Precondition-Bewertung sind getrennt (PLAN §3.2).

```mermaid
flowchart TD
  classDef llm fill:#ede9fe,stroke:#7c3aed,color:#3b0764
  classDef rule fill:#dbeafe,stroke:#2563eb,color:#1e3a8a
  classDef store fill:#dcfce7,stroke:#16a34a,color:#14532d
  classDef human fill:#fef3c7,stroke:#d97706,color:#78350f

  IN["Source Message<br/>Mail · Chat · Seed · Replay"] --> TYP{"Inhalt?"}
  TYP -->|"Text"| EXTR["LLM-Extraktion<br/>wer · Zone · was · wann · Absicht"]:::llm
  TYP -->|"DXF-Anhang (MVP)"| GEO["Geometrie-Extraktion<br/>Räume · Wände · Bauteile → Zonen"]:::rule
  TYP -.->|"DWG-Anhang (Erweiterung)"| CONV["DWG → DXF<br/>externer Konverter"]:::rule
  CONV -.-> GEO
  GEO --> DIFF["Plan-Diff<br/>zur vorherigen Revision"]:::rule
  EXTR -->|"unbestätigte Aussage"| EV["Event mit Quelle und Herkunft"]
  DIFF -->|"betroffene Zonen"| EV
  GEO -->|"Geometrie für 3D und Agent"| REC
  EV --> REC[("Site Record<br/>Events · Nachweise mit Prüfstatus<br/>Zonen · Tasks · Revisionen · Inspections")]:::store
  REC --> REVIEW["Mensch im Dashboard<br/>Quelle und Geltungsbereich prüfen<br/>auch ohne Flag"]:::human
  REVIEW --> VERIFY["api: bestätigen / ablehnen<br/>Audit: Person · Zeitpunkt · Quelle"]:::rule
  VERIFY -->|"Prüfstatus speichern, erneut prüfen"| REC
  SCAN["Morgen-Scan<br/>täglich, ausgelöst vom worker"] --> RULES
  REC --> RULES{"Regel-Engine<br/>gültige bestätigte Nachweise?<br/>Precondition-Bewertung"}:::rule
  RULES -->|"erfüllt"| OK["kein neuer Flag<br/>bestehender bleibt offen"]
  RULES -->|"nicht erfüllt / unbekannt / widersprüchlich"| DEDUP{"Offener Flag für<br/>denselben Konflikt?"}:::rule
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
  SK -.->|"Kontext und fallbezogene Extraktionskorrektur<br/>keine Regel-Deaktivierung"| EXTR
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
  I -.->|"System: gültiger Nachweis bestätigt,<br/>Precondition erfüllt; kein Abschluss"| I
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
- **Extraktion ist keine Nachweisbestätigung.** Nur ein zuständiger Mensch bestätigt eine LLM-extrahierte Aussage im Dashboard als Nachweis für eine konkrete Precondition. `api` prüft Status und Geltungsbereich; Quelle, Person, Zeitpunkt und Entscheidung werden protokolliert. Hohe Modellkonfidenz genügt nicht. MCP/Chat dürfen Nachweise weder bestätigen noch ablehnen oder ihren Prüfstatus übersteuern; der Rollenumschalter im MVP ersetzt keine produktionsreife Authentifizierung.
- **Fehlende oder widersprüchliche Daten sind keine Freigabe.** Preconditions werden als erfüllt / nicht erfüllt / unbekannt / widersprüchlich bewertet. Nur gültige bestätigte Nachweise erlauben „erfüllt“. Neue Gegenmeldungen gehen in die Prüfung ein, ohne menschliche Bestätigungen durch das LLM zu überschreiben. Nachweisentscheidungen lösen erneut die Regelprüfung aus; bestehende Flags bleiben bis zum menschlichen Abschluss offen.
- **Seed und CAD haben explizite Herkunft.** Synthetische bestätigte Ausgangsnachweise werden als Seed markiert; LLM-Aussagen bleiben auch im Offline-Replay unbestätigt. Deterministische CAD-Events aktualisieren Geometrie/betroffene Zonen, bestätigen aber keine Inspection, Crew-Kenntnisnahme oder Task-Abschlüsse.
- **Learning ersetzt keinen Nachweis.** Im MVP korrigiert Feedback fallbezogen die Extraktion. Es deaktiviert keine Sicherheitsprüfung und umgeht keine Bestätigungspflicht. Änderungen sicherheitsrelevanter Regeln brauchen gesonderte menschliche Freigabe, begrenzten Geltungsbereich und Audit.
- **Der Chat-Agent nutzt dieselben MCP-Tools wie externe Agents.** Was unser Chat kann, kann auch Talonas Agent.
- **Kanal-Zugangsdaten** (Gmail, Telegram) liegen nur im `worker`, der LLM-Key nur in `api`.

## CAD-Eingabe im MVP

Der MVP setzt DXF-Dateien mit der [Layer-Konvention](cad/README.md) voraus.
Die synthetischen Pläne liegen in `cad/plans/`; die Hero-Mail enthält
`A-103_RevD.dxf`. Die CAD-Pipeline (#15) extrahiert daraus die Geometrie.
Originaldatei und Revision bleiben als Quelle erhalten.

DWG-Import und DWG-Export sind außerhalb des MVP. LibreDWG ist als separates
Programm in einem optionalen Compose-Job vorbereitet. Eine spätere Anbindung
kann DWG vor derselben DXF-Extraktion umwandeln; Layer, Beschriftungen, Einheiten
und relevante Geometrie müssen dabei erhalten bleiben.
Setup und bekannte Grenzen: [CAD-Konverter](docs/CAD-CONVERTER.md).
