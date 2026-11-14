# Hero-Replay und Reset (#22)

Der gefuehrte Replay spielt den synthetischen Hero aus PLAN Abschnitt 7 mit
simulierter Uhr durch. Ein Aufruf setzt den Demo-Stand zurueck, importiert die
vier Rev-C-Plaene und startet die Nachrichtenfolge. Rev D kommt erst mit der
Architekten-Mail. Der Client schreibt ausschliesslich ueber bestehende REST-APIs;
DB-Zugriff und fachliche Regeln bleiben in der API.

**Stand der Q&A-Abhaengigkeit:** #20 ist noch offen. Die beiden Hero-Fragen werden
als Fragen ingestiert; der Client zeigt den echten, rein lesenden Record-Kontext
fuer `3B-BATH`. Das ist keine Telegram-Antwort. Versand und Inhalt echter
Chat-Antworten sind damit noch nicht end-to-end verifiziert. Das Abschlussprotokoll
weist dies mit `telegram_answers_verified: false` aus. Der Replay implementiert
keinen Ersatz fuer #20.

## Vorbereitung

Eine eigene synthetische Demo-Instanz verwenden: Der Reset ersetzt den Site Record
inklusive Nachrichten, Evidence-Pruefhistorie, Flags, Proposals, Outbox, Learning
und Geometrie. Keine Instanz mit aufzubewahrenden Daten verwenden.

Die bestehende `.env` wie in README beschrieben vorbereiten, mit
`LLM_PROVIDER=cached` fuer die API. Das gilt auch online: Der absichtliche
Extraktionsfehler und die anschliessende Lernkorrektur sollen reproduzierbar sein.
`GET /replay/config` gibt dafuer nur `offline_ready` zurueck; der Client aendert
keine Provider-Einstellungen und verweigert einen Reset bei Live-LLM-Konfiguration.
Die Standard-Caches im Image verwenden. Alle benoetigten DXFs werden vor dem
Reset auf Vorhandensein geprueft.

```sh
docker compose up --build -d db api web
docker compose build worker
docker compose stop worker
```

Der normale Worker muss waehrend des Replay gestoppt sein. Sonst konkurrieren
Polling und Replay um dieselben echten Nachrichten, und normale Scan-Jobs greifen
mit der realen Uhr ein. Das Dashboard bleibt unter http://localhost:3000 offen.
Die folgenden Befehle laufen im Repository-Root mit interaktivem Terminal.

## Offline: ein Befehl fuer Reset und Replay

```sh
docker compose run --rm --no-deps -v ./cad:/cad:ro -v ./.replay:/replay-output worker python -m app.replay --mode offline --speed 3600 --output /replay-output/hero.jsonl
```

Kein Gmail-/Telegram-Konto ist erforderlich. Nachrichten gehen mit Kanal `replay`
in `POST /ingestion/messages`; Extraktion und Advisor nutzen lokale Caches.
Outbox-Zustellungen werden explizit als `synthetic_delivery` im lokalen JSONL
protokolliert und mit `synthetic-replay:`-Referenz in der Outbox quittiert.
Der Replay verwendet hier keine externen Provider-Clients. API und Dashboard
muessen lokal erreichbar sein; andere parallel laufende Worker ausschalten.

Alternativ mit bereits eingerichteter Python-Umgebung unter PowerShell:

```powershell
$env:PYTHONPATH = "backend"
python -m app.replay --mode offline --api http://localhost:8000 --speed 3600
```

`--speed` bezeichnet simulierte Sekunden pro realer Sekunde; `3600` macht aus einer
Stunde eine Sekunde. Dashboard-Pausen zaehlen nicht mit. Ohne `--output` entsteht
`.replay/<run-id>.jsonl`; dieses Verzeichnis wird von Git ignoriert.

Nur auf Seed und Rev-C-Geometrie zuruecksetzen:

```sh
docker compose run --rm --no-deps -v ./cad:/cad:ro -v ./.replay:/replay-output worker python -m app.replay --reset-only --output /replay-output/reset.jsonl
```

Das entfernt auch gelernte Korrekturen und stellt die synthetischen
Ausgangsnachweise mit `seed_baseline`, Import-Referenz und Seed-Audit wieder her.
Es werden keine menschlichen Freigaben erfunden.

## Online: echte Testnutzer und bestehende Adapter

Zusaetzlich zur Offline-Vorbereitung die bestehenden Gmail- und Telegram-Adapter
konfigurieren, siehe [GMAIL.md](GMAIL.md) und [TELEGRAM.md](TELEGRAM.md).
Insbesondere:

- Worker: eigene Projekt-Testmailbox mit `GMAIL_MAILBOX`, OAuth-Datei unter
  `.gmail/`, `GMAIL_SEND_ENABLED=true` und Lese-/Sendeberechtigung.
  `GMAIL_SENDER_ROLES_JSON` ordnet echte Test-Absender `architect` bzw. `inspector`
  zu. Die Label-Konfiguration muss eingehende Testmails erfassen.
- Worker: `TELEGRAM_BOT_TOKEN`, zugelassene private Chats und Nutzer sowie
  `TELEGRAM_SENDER_ROLES_JSON` und `TELEGRAM_SENDER_CREWS_JSON` fuer die
  Testpersonen: Crew Leads fuer `plumbing` und `drywall`, dazu `superintendent`.
  Die bestehenden Datenschutz-/Compliance-Einstellungen gelten weiterhin.
- API: `SUPERINTENDENT_EMAIL` fuer die Freigabeanfrage und zustaendige
  Crew-Lead-Empfaenger. Der Seed hat keine Crew-Mailadressen. Fuer diese Demo
  kann `TELEGRAM_CREW_LEADS_JSON` die IDs `lead-plumbing`, `lead-insulation`,
  `lead-drywall` auf zugelassene private Test-Chats/Nutzer abbilden
  (Format siehe Telegram-Dokumentation). Auch Insulation braucht einen
  Empfaenger, weil die Rev-D-Aenderung dessen Kenntnisnahme prueft.

Nach Aenderungen der API-Umgebung den API-Container neu erstellen. Credentials
bleiben im Worker; der Replay fuegt keine Zugangsdaten in API oder Frontend ein.
Die API verwendet weiterhin die gecachten LLMs, die Transporte sind echt.

```sh
docker compose run --rm --no-deps -v ./cad:/cad:ro -v ./.replay:/replay-output worker python -m app.replay --mode online --speed 3600 --timeout 180 --output /replay-output/hero-online.jsonl
```

Bei jedem Schritt zeigt das Terminal Kanal, Rolle, Crew, exakten Text und ggf.
Betreff/Anhang. Erst nach dieser Aufforderung sendet die entsprechende Testperson
die Nachricht aus ihrem echten Mail- oder Telegram-Client. Keine Signatur oder
zusaetzlichen Texte anhaengen; Mails als Klartext senden. Die Rev-D-Mail braucht
die unveraenderte Datei `cad/plans/A-103_RevD.dxf`. Fuer den Lernvergleich dieselbe
Frage erneut senden, mit einer neuen echten Nachrichten-ID.

Gmail laeuft durch MIME-Decodierung und den bestehenden Polling-Adapter,
Telegram durch den bestehenden Allowlist-/Rollen-Adapter. Bot-Nachrichten zaehlen
nicht als eingehende Testnutzer-Nachrichten. Nur neue, zum aktuellen Schritt
passende Nachrichten werden uebernommen; nach `--timeout` Sekunden bricht der
Lauf sichtbar ab. Bestehende Nachrichten werden nicht als neue Eingaben gewertet.

Der Replay erhaelt Kanal, Absender und echte Provider-ID, setzt `sent_at` auf die
Szenariouhr und legt die originale Transportzeit sowie Szenariozeit, Run-ID und
Schritt als `replay-transport.json`-Quellanhang ab. Ausgehende Warnungen,
Freigabeanfragen und freigegebene Follow-ups verwenden die bestehenden
Outbox-Sender. `real_delivery` wird erst nach erfolgreicher Provider-Quittierung
protokolliert. Fehlende Empfaenger oder Versandfehler werden nicht als Zustellung
simuliert: Der Client pausiert, nach Korrektur und Backoff versucht Enter die
Zustellung erneut, `q` stoppt. Eine Mail ohne die unveraenderte DXF wird
ignoriert, die Mail kann im selben Schritt erneut gesendet werden.
Telegram-Befehle (`/privacy`, `/my_data`, `/delete_my_data`) und Beitritts-Hinweise
zugelassener Nutzer gehen waehrend des Replay normal an die API; andere, nicht
zum Schritt passende Nachrichten werden nicht ingestiert.

## Ablauf und menschliche Entscheidungen

Die genauen Texte und Zeitpunkte stehen in
[`backend/demo/hero-scenario.json`](../backend/demo/hero-scenario.json).
Jede Dashboard-Pause nennt Flag-Link, erforderliche Aktion und ggf. konkrete
Evidence-IDs. Enter prueft nur den gespeicherten Zustand. Es bestaetigt, genehmigt
oder schliesst nichts. Bei noch fehlender Entscheidung wartet der Client erneut.

| Schritt | Erwartetes Verhalten / Dashboard-Aktion |
| --- | --- |
| Tag 1: Rev D mit DXF | C-zu-D-Diff betrifft 3B; Flag B warnt ueber fehlenden Crew-Erhalt. |
| Warnung gesehen | Keine automatische Kenntnisnahme der Revision. Mensch quittiert Flag B separat; kein Erledigt-Status. |
| Tag 2: Abnahme verschoben, danach "Abnahme duerfte passen" | Beide Aussagen bleiben unbestaetigt; die mehrdeutige Aussage erfuellt keine Precondition. |
| Trockenbau angekuendigt | Flag A trotz mehrdeutiger Erfolgsmeldung. Mensch quittiert und genehmigt den Verschiebe-Proposal separat; erst danach geht das Follow-up raus. |
| Zwei Hero-Fragen | Frage-Events und echter Record-Kontext; Telegram-Antworten warten auf #20. |
| Tag 3: Arbeit verschoben | Mensch schliesst das erste A mit Feedback. Keine Abnahme wird dadurch bestaetigt. |
| Lernmoment: Frage als Ankuendigung missverstanden | Mensch setzt den neuen Flag auf Fehlalarm und waehlt explizit das fehlerhafte Event als Extraktionskorrektur. |
| Dieselbe Frage erneut | Frage statt Arbeitsankuendigung; Site Knowledge verweist sichtbar auf Originalquelle und Feedback. Kein neuer A-Flag. |
| Echte Ankuendigung "heute frueh ..." | Echter Konflikt erzeugt weiterhin A. "Heute" referenziert den im Seed fuer Tag 3 geplanten Trockenbau. |
| Tag 4: konkretes Abnahmeergebnis | Zunaechst unbestaetigt. Mensch prueft und bestaetigt genau dessen Evidence. Auch das negative synthetische Widerspruchsbeispiel `example-contradictory-negative` im Seed muss explizit geprueft/abgelehnt werden. Erst dann ist die Precondition erfuellt; A bleibt offen. |
| Expliziter Rev-D-Erhalt | Mensch bestaetigt genau den Plumbing-Erhalt fuer A-103-D/3B. B bleibt quittiert/offen; Erhalt beweist keine bauliche Umsetzung. |
| Abschluss | Mensch quittiert den verbleibenden A, genehmigt dessen Proposal separat und schliesst A separat. B bleibt offen bei erfuellter Precondition. |

Die widerspruechlichen Seed-Beispiele werden weder beim Replay noch beim Reset
heimlich entfernt oder bestaetigt. Die Pruefung einer anderen positiven
Seed-Aussage ersetzt nicht die verlangte Pruefung der konkreten Tag-4-Quelle.

`q`, EOF, fehlende Voraussetzungen oder nicht behebbare Providerfehler stoppen mit erhaltenem
Zwischenstand. Es gibt kein Resume: Ein neuer kompletter Aufruf beginnt wieder
mit Reset. Der lokale JSONL-Transcript enthaelt Reset, Nachrichtenreferenzen,
Zustellungen, menschliche Checkpoints und Abschluss; er ersetzt nicht den
Quellen-/Feedback-Audit im Site Record.

## Verifikation

```powershell
$env:PYTHONPATH = "backend;backend/tests"
python -m pytest backend/tests/test_replay.py backend/tests/test_replay_channels.py -q
```

Der Offline-Integrationstest durchlaeuft CAD, Ingestion, gecachte Extraktion,
Regeln, Advice, Outbox, Lernkorrektur und erneuten Reset. Nur der Testcallback
uebernimmt dabei ausdrueckliche menschliche Aktionen; der Replay selbst schreibt
keine Entscheidungs-Endpunkte. Externe Provider-Transporte sind im Offline-Test
gesperrt. Online-Adaptertests verwenden echte Decoder/Handler mit simulierten
HTTP-Providerantworten und pruefen auch Versandfehler. Ein Live-Lauf mit echten
Testkonten bleibt eine manuelle Integrationspruefung.
