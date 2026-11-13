# SiteMind – Projektplan (Proximata Hackathon '26, Talona Track)

> Gemeinsamer Rahmen für alle Teammitglieder und ihre Coding Agents.
> Der Plan legt fest, **was** gebaut wird und **welche Grenzen** gelten. **Wie** etwas umgesetzt wird, entscheidet der Agent im jeweiligen Issue.
> Ändert sich etwas an Scope, Domänenbegriffen oder API-Vertrag, wird zuerst dieses Dokument per PR angepasst.

**Code Freeze: Samstag, 14.11., 15:00 (hart).** Abgabe spätestens 14:30.

---

## 1. Problem und Pitch in einem Satz

Auf Baustellen gehen Entscheidungen in Chats, Mails und Tabellen verloren. Eine Crew schließt eine Wand vor der Abnahme oder baut nach einer veralteten Planrevision, und das wird zu Rework.
**SiteMind führt einen lebenden Record der Baustelle, erkennt solche Konflikte, bevor gearbeitet wird, und verfolgt jedes erkannte Problem, bis ein verantwortlicher Mensch es abschließt.**

**Unser Produkt ist die Context Engine, nicht der Agent.** Jeder Agent, später auch Talonas eigener, kann sich per MCP anschließen.

### Belege für den Use Case (vor dem Pitch verifizieren, Quellen zitieren)
- FMI/Autodesk, *Harnessing the Data Advantage in Construction* (2021): 1,85 Bio. USD Kosten durch schlechte Daten (2020).
- FMI/PlanGrid, *Construction Disconnected* (2018): ca. 31 Mrd. USD Rework in den USA durch schlechte Daten und Miskommunikation; ca. 14 h/Woche für Suchen und Konfliktlösung.
- Rework-Anteil laut CII bzw. Love et al.: grob 5–12 % der Projektkosten.
- **Realer Bauablauf** als Grundlage der synthetischen Daten: Rohinstallation → Abnahme Rohinstallation → Dämmung → Abnahme Dämmung → Trockenbau. Die Abnahmen vor dem Verschließen („cover inspections“) sind reale Praxis. Unsere Vorbedingungen stammen also aus der Baupraxis, nicht aus Intuition.
- **Mentor-Interview mit Talona (Kacper):** Welche Fehlerbilder sind am häufigsten bzw. teuersten? Ergebnis hier festhalten und im Pitch als „validiert mit Talona“ nutzen.

---

## 2. Domänensprache (verbindlich, auch für Agents)

| Begriff | Bedeutung |
|---|---|
| **Site** | Die Baustelle (1 Projekt im MVP) |
| **Zone** | Räumliche Einheit, hierarchisch: Gebäude → Etage → Wohnung → Raum/Bauteil (z. B. „Wand Bad 3B“) |
| **Task** | Geplanter Arbeitsschritt aus dem Terminplan (Gewerk, Zone, Zeitraum, Vorgänger) |
| **Crew** | Ausführende Gruppe eines Gewerks mit einem **Crew Lead** |
| **Superintendent** | Bauleiter, trifft Entscheidungen |
| **Revision** | Version eines Plans/Planblatts; betrifft Zonen; Crews **bestätigen** Revisionen |
| **Inspection** | Abnahme einer Zone (ausstehend / bestanden / nicht bestanden) |
| **Source Message** | Rohe eingehende Nachricht (Mail, Telegram, Seed), immer mit Herkunft |
| **Event** | Strukturierte Information, die aus einer Source Message extrahiert wurde (wer, Zone, was, wann, Absicht) |
| **Precondition** | Bedingung, die erfüllt sein muss, bevor ein Task in einer Zone starten darf |
| **Flag** | Erkanntes Problem. Bewusst **nicht** „Issue“, um Verwechslung mit GitHub-Issues zu vermeiden |
| **Proposal** | Handlungsvorschlag des LLM zu einem Flag, braucht menschliche Freigabe |
| **Feedback** | Abschluss-Bewertung eines Flags: *bestätigt / Fehlalarm / erledigt*, plus Begründung |
| **Site Knowledge** | Aus Feedback gelerntes Wissen (Begriffe, Ausnahmen, Unterdrückungen) |

---

## 3. Kernkonzepte

### 3.1 Ein Muster für alle Konflikte
Jeder Konflikt hat dieselbe Form: **In Zone X steht Arbeit Y an, aber Precondition Z ist nicht erfüllt.**
Ein neuer Konflikttyp ist damit nur eine neue Precondition, keine neue Architektur.

| Typ | Precondition | Status |
|---|---|---|
| **A: Wand zu vor Abnahme** | Die nötige Inspection der Zone ist bestanden | MVP |
| **B: Änderung nicht angekommen** | Die ausführende Crew hat die neueste Revision der betroffenen Zone bestätigt | MVP |
| **C: Falsche Reihenfolge** | Vorgänger-Task(s) laut Terminplan abgeschlossen | Stretch |

### 3.2 Wer entscheidet was (Autonomie-Grenze)
- **LLM:** Extraktion (Source Message → Event), Erklärung von Flags, Proposals, Beantwortung von Fragen. **Rein beratend. Das LLM trifft keine Entscheidungen und löst keine Aktionen aus, die über Information hinausgehen.**
- **Regeln (deterministisch):** Prüfen Preconditions und erzeugen Flags. Dadurch reproduzierbar und erklärbar.
- **Automatisch (ohne Mensch):** Prüfung bei jedem neuen Event, täglicher Morgen-Scan („Was ist morgen gefährdet?“), **faktische Benachrichtigung** der verantwortlichen Person mit Quelle, Eskalation bei ausbleibender Reaktion.
- **Nur mit menschlicher Freigabe:** Jede Handlung (Task verschieben, Crew umplanen, Arbeit stoppen) und jeder Abschluss eines Flags.

### 3.3 Flag-Lebenszyklus: nichts geht verloren
`erkannt → benachrichtigt → zur Kenntnis genommen → in Bearbeitung → erledigt | Fehlalarm`

- Jeder Flag hat **eine verantwortliche Person** (über Zone und Gewerk der Crew Lead; Entscheidungen liegen beim Superintendent).
- Ein Flag bleibt **sichtbar offen**, bis eine verantwortliche Person ihn schließt. Schließen nur mit **Feedback**.
- **Das System schließt nie selbst.** Ist eine Precondition nachträglich erfüllt, markiert es den Flag nur als „Vorbedingung erfüllt, wartet auf Bestätigung“.
- **Eskalation:** Bleibt ein Flag X Stunden ohne Reaktion, geht er an die nächsthöhere Stelle. X ist konfigurierbar.
- **Deduplizierung:** Wird derselbe Konflikt erneut erkannt, wird das an den bestehenden offenen Flag angehängt, kein neuer Flag.
- **Audit-Trail:** Jede Zustandsänderung mit *wer, wann, über welchen Kanal, auf Basis welcher Quelle*. Jeder Flag verweist auf die auslösenden Source Messages (mindestens als Zitat).

### 3.4 Learning Loop
- Feedback (*bestätigt / Fehlalarm / erledigt* + Begründung) wird zu **Site Knowledge**. Beispiele: „‚die B-Wohnungen‘ = 2B, 3B, 4B“, „Inspektor Y gibt mündliche Freigaben, die zählen als bestanden“.
- Site Knowledge wirkt zurück auf die **LLM-Extraktion und -Erklärung** (als Kontext) und auf die **Regeln** (Unterdrückung bzw. Anpassung bekannter Fehlalarme).
- **Ziel:** Gleiche Fehler bzw. Fehlalarme treten nicht wieder auf. Im Dashboard sichtbar als Kennzahl (Anteil bestätigter Flags über die Zeit).
- **Vision (nur im Pitch):** Lernen über Projekte hinweg, Fotos gegen Pläne prüfen, Kontext für Roboter.

---

## 4. Scope

### MVP (muss stehen)
1. Gebäudemodell und Seed-Daten (Gebäude, Zonen, Terminplan, Crews, Revisionen, Inspections, Hero-Szenario)
2. Ingestion-Eingang, unabhängig von der Quelle, mit LLM-Extraktion
3. Regel-Engine mit Konflikttypen A und B, Prüfung bei jedem Event und Morgen-Scan
4. Flag-Lebenszyklus mit Audit-Trail, Eskalation, Deduplizierung
5. **Gmail** ein und aus (Revisionen und Inspektionsergebnisse rein; Warnungen und Freigabe-Anfragen raus)
6. **Telegram** ein und aus (Gruppenchat mitlesen, Warnungen und Antworten an Crew Leads), inkl. Compliance (§6)
7. Terminplan als Seed-Datei (CSV oder Export im MS-Project-Stil)
8. Dashboard: Übersicht, Flag-Inbox mit Detail, Quellen und Feedback, Freigabe von Proposals, Timeline der Änderungen und Entscheidungen
9. 3D-Ansicht (einzige räumliche Ansicht)
10. REST-API und **MCP-Server**
11. Learning Loop (§3.4)
12. Replay-Skript mit Reset
13. Chat (Dashboard und Telegram-Q&A) über die eigenen MCP-Tools. **Erst nach Abnahme der kritischen Pakete.**

### Stretch (nur wenn das MVP zuverlässig läuft)
- Konflikttyp C (falsche Reihenfolge)
- Fotos aus Telegram per Vision-LLM als Beleg („Wand ist zu“)

### Bewusst out of scope
- BIM/IFC-Import. *Begründung:* Talonas Zielkunden (kleine und mittlere GCs) arbeiten meist mit PDF-Plänen.
- Automatischer Vergleich von Plänen per Vision
- WhatsApp (Twilio-Sandbox kann keine Gruppen). In Production über denselben Adapter wie Telegram.
- Echtes Nachtrainieren von Modellen
- Vollständiges Auth- und Rechte-System im Dashboard. Im MVP gibt es einen Rollen-Umschalter (Superintendent / Crew Lead), in `COMPLIANCE.md` als Production-Lücke dokumentiert.

---

## 5. Architektur und Stack (gesetzt)

| Dienst (docker compose) | Aufgabe | Stack |
|---|---|---|
| `db` | Persistenz | PostgreSQL |
| `api` | REST-API, Regel-Engine, Flag-Lebenszyklus, Learning Loop | Python, FastAPI |
| `worker` | Gmail- und Telegram-Polling, Morgen-Scan, Eskalationstimer | Python, gleiche Codebasis wie `api` |
| `mcp` | MCP-Server für externe Agents. Spricht **nur über die REST-API**, nie direkt mit der DB | Python, offizielles MCP-SDK |
| `web` | Dashboard, Chat, 3D-Ansicht | Next.js, React, Three.js |

Grundsätze:
- **Alles startet per `docker compose up`.** Die Jury muss es nach README nachvollziehen können.
- **Der API-Vertrag ist die OpenAPI-Spezifikation von FastAPI.** Das Frontend arbeitet gegen diesen Vertrag.
- **Alle Quellen laufen über denselben Ingestion-Eingang.** Ein neuer Kanal ist nur ein neuer Adapter.
- **Polling statt Webhooks** (keine öffentliche URL nötig, lokales Deployment).
- **LLM-Provider austauschbar über die Konfiguration.** Voraussetzungen: strukturierte Ausgaben und Tool-Calling; bevorzugt mit EU-Region.
- **Für die Demo funktioniert alles auch offline:** Replay direkt in den Ingestion-Eingang, LLM-Antworten des Demo-Szenarios gecacht.

---

## 6. Compliance (Telegram, Gmail, LLM)

**Implementieren:**
- **Transparenzhinweis:** Der Bot postet beim Beitritt zur Gruppe, was er verarbeitet, wozu, wie lange und wer verantwortlich ist. Dazu ein Befehl für Auskunft und Löschung.
- **Allowlist:** Nur freigegebene Gruppen und Nutzer werden verarbeitet und bekommen Antworten.
- **Zweckbindung:** **Keine Kennzahlen oder Auswertungen pro Person.** Flags hängen an Zonen, Tasks und Gewerken.
- **Datenminimierung:** Ans LLM nur Nachrichtentext und Rolle, keine Telefonnummern oder Usernamen. Rohnachrichten mit konfigurierbarer Löschfrist; Flags behalten nur das relevante **Zitat**.
- **Gmail mit minimalen Scopes** (lesen und senden) und nur ein dediziertes Projektpostfach bzw. Label.
- **Audit-Trail** (§3.3)
- **Keine Secrets im Repo**, nur `.env.example`

**Dokumentieren in `COMPLIANCE.md`:**
- Rechtsgrundlage
- Betriebsvereinbarung (AT: ArbVG §96/§96a), da das System potenziell Leistung überwachen könnte
- Auftragsverarbeitungsvertrag, EU-Region und Zero Data Retention beim LLM-Provider
- Telegram: Server außerhalb der EU, keine Ende-zu-Ende-Verschlüsselung → in Production WhatsApp Business oder Teams
- Prompt Injection: Das Risiko ist begrenzt, weil das LLM nur berät
- Fehlende Dashboard-Authentifizierung

**Demo:** Ausschließlich synthetische Daten und Test-Accounts aus dem Team.

---

## 7. Hero-Szenario (Basis für Seed, Replay, Video)

Fiktives Projekt: Wohnbau, 1 Gebäude, 4 Etagen, je 4 Wohnungen (A–D). Detailliert modelliert sind nur die Hero-Zonen (Wohnung 3B mit Wänden).

| Zeitpunkt (simuliert) | Quelle | Was passiert | Erwartete Reaktion |
|---|---|---|---|
| Tag 1, 07:00 | Terminplan | Trockenbau 3. OG startet an Tag 3 | – |
| Tag 1, 10:15 | Gmail (Architekt) | Rev D: Badwand 3B um 30 cm verschoben, Abwasserleitung neu geführt | Event Revision → **Flag B**: Installateur-Crew hat nur Rev C bestätigt → Warnung an den Crew Lead |
| Tag 1, 11:00 | Telegram | Crew Lead der Installateure bestätigt | Flag B „zur Kenntnis genommen“ |
| Tag 2, 16:40 | Gmail (Inspektor) | Abnahme der Rohinstallation im 3. OG verschoben auf Tag 4 | Event Inspection ausstehend |
| Tag 2, 18:05 | Telegram (Trockenbau-Gruppe) | „morgen früh machen wir 3B zu, platten sind da“ | **Flag A (kritisch)**: Abnahme offen und Rev D noch nicht umgesetzt → 3D: Wand 3B rot → Superintendent bekommt Proposal „Trockenbau 3B verschieben, Crew auf 3A/3C umplanen“ → Freigabe → Crew Lead informiert |
| Tag 2, 18:30 | Telegram | Crew fragt: „welcher plan gilt für 3B?“ | Antwort aus dem Record mit Quelle (Rev D, Mail vom Tag 1) |
| Tag 3 | Dashboard | Superintendent schließt Flag A als *erledigt* mit Begründung | Audit-Trail vollständig |
| Learning-Loop-Moment | Telegram + Dashboard | Eine Nachricht erzeugt einen Fehlalarm; der wird als *Fehlalarm* mit Grund geschlossen; Replay neu | Derselbe Fall wird nicht mehr geflaggt |

Das Replay-Skript spielt diese Abfolge über die **echten** Kanäle ein (echte Mails von einem Test-Account, echte Telegram-Nachrichten) und hat einen Offline-Modus (§5).

---

## 8. Arbeitspakete (werden zu GitHub-Issues)

Keine feste Rollenverteilung, jeder nimmt sich Issues selbst. Die Abhängigkeiten bestimmen die Reihenfolge.

| ID | Paket | Abhängig von | Meilenstein |
|---|---|---|---|
| WP0 | Repo-Grundgerüst: Compose mit allen 5 Diensten (lauffähige Hüllen), minimale CI, `.env.example`, README-Grundgerüst | – | M0 |
| WP1 | Domänenmodell, DB-Schema und API-Vertrag (Entitäten aus §2) | WP0 | M0 |
| WP2 | Seed-Daten: Gebäude-JSON, Terminplan, Crews, Revisionen, Inspections, Hero-Szenario aus §7. Inhalte können sofort als Dateien entstehen | WP1 (für den Import) | M0 |
| WP3 | Ingestion-Eingang und LLM-Extraktion (Source Message → Event, Zuordnung zu Zonen) | WP1 | M1 |
| WP4 | Regel-Engine: Preconditions A und B, Prüfung bei jedem Event, Morgen-Scan | WP1, WP2 | M1 |
| WP5 | Flag-Lebenszyklus: Zustände, Verantwortliche, Audit-Trail, Deduplizierung, Eskalation, Proposals | WP1 | M1 |
| WP6 | Gmail-Adapter ein und aus | WP3, WP5 | M1 |
| WP7 | Telegram-Adapter ein und aus, inkl. Compliance-Features (§6) | WP3, WP5 | M2 |
| WP8 | Dashboard: Übersicht, Flag-Inbox, Detail mit Quellen, Feedback, Freigabe, Timeline | WP1 (Vertrag), WP5 | M1 (Grundversion) / M2 |
| WP9 | 3D-Ansicht: prozedural aus Gebäude-JSON, Färbung nach Flag-Status, Klick öffnet Detail. Prototyp mit Mock-Daten sofort möglich | WP2 (JSON), WP5 | M2 |
| WP10 | MCP-Server: Tools u. a. Zonenstatus, offene Flags, Änderungshistorie, Suche/Frage, Proposal anlegen | WP1, WP5 | M2 |
| WP11 | Chat-Agent für Dashboard und Telegram-Q&A über die eigenen MCP-Tools | WP10, WP7 | M3 |
| WP12 | Learning Loop: Feedback → Site Knowledge → Extraktion und Regeln; Kennzahl im Dashboard | WP3, WP4, WP5 | M2/M3 |
| WP13 | Replay-Skript mit simulierter Uhr, Reset, Offline-Modus | WP2, WP6, WP7 | M2 |
| WP14 | Research, Mentor-Interview, Pitch, 3-Min-Video, `COMPLIANCE.md`, finale README, Abgabe | läuft parallel | M4 |
| S1 | Stretch: Konflikttyp C | WP4 | M3 |
| S2 | Stretch: Fotos als Beleg (Vision) | WP7 | M3 |

**Sofort parallel zu WP0/WP1 (keine Code-Abhängigkeit):** Google-Cloud-Projekt und Gmail-OAuth einrichten (OAuth-Testmodus: Test-User eintragen; Refresh-Tokens laufen nach 7 Tagen ab), Telegram-Bot anlegen (Privacy Mode aus), LLM-Key besorgen, Seed-Inhalte schreiben, 3D-Prototyp, Research und Mentor-Interview.

### Inhalt jedes Issues (Template)
- **Ziel:** Was danach möglich ist, aus Sicht des Nutzers bzw. des Systems
- **Akzeptanzkriterien:** Prüfbar, inkl. erwarteter Unit-Tests
- **Abhängigkeiten**
- **Out of Scope**
- **Bezug zum Plan:** Abschnitt in diesem Dokument

---

## 9. Timeline

| Meilenstein | Bis | Ergebnis |
|---|---|---|
| **M0 Fundament** | Fr ~19:30 | WP0–WP2 gemergt; Accounts und Keys vorhanden |
| **M1 Tracer Bullet** | Sa ~01:00 | Mail rein → Event → Flag → sichtbar im Dashboard → Warnmail raus, einmal durchgehend |
| **M2 Breite** | Sa ~09:00 | Telegram, Lebenszyklus komplett, 3D eingebunden, MCP, Replay, Morgen-Scan, Eskalation |
| **M3 Feature Freeze** | Sa 12:00 | Chat, Learning Loop, Stretch falls Zeit. **Danach keine neuen Features.** |
| **M4 Abgabe** | Sa 14:30 | Bugfixes, Video (bis ~13:30), README, `COMPLIANCE.md`, `.env.example`, Submission |

Schlaf in Schichten, sodass nachts immer jemand reviewen und mergen kann.

---

## 10. Arbeitsweise

- **Ablauf:** Issue → Branch → PR (verlinkt das Issue) → **1 Approver** → Merge. Kein Review durch alle.
- **CI (minimal, muss grün sein):** Backend-Tests, Frontend-Build und Lint, Prüfung der Compose-Konfiguration. Ein kaputter `main` blockiert alle.
- **Tests:** Jede Logik bekommt Unit-Tests, vor allem Regel-Engine, Lebenszyklus, Deduplizierung, Eskalation, Extraktion (mit gemocktem LLM) und Learning Loop. LLM-Aufrufe sind in Tests immer gemockt.
- **Schema-Owner:** Wer gerade WP1 hält, koordiniert DB-Migrationen. Migrationen von parallelen PRs kollidieren sonst (gleiche Nummer).
- **Änderungen am API-Vertrag oder Schema:** Kurzer Hinweis an alle, bevor gemergt wird.
- **Definition of Done:** Akzeptanzkriterien erfüllt, Tests grün, läuft per `docker compose up`, keine Secrets im Code.

---

## 11. Bezug zu den Bewertungskriterien

| Kriterium | Punkte | Abgedeckt durch |
|---|---|---|
| Technical implementation | 35 | Hybride Architektur (LLM-Extraktion + deterministische Regeln), echte Integrationen, MCP, CI und Tests, Compose |
| Autonomous operation & impact | 30 | Automatische Prüfung bei jedem Event und Morgen-Scan, automatische Benachrichtigung und Eskalation, Human-in-the-Loop für Entscheidungen |
| Learning loop & vision | 15 | Feedback → Site Knowledge → weniger Fehlalarme (messbar); Vision-Folie |
| Demo & presentation | 20 | Hero-Szenario, 3D-Ansicht, belegter Use Case, Compliance-Story |

---

## 12. Offene Punkte

- [ ] LLM-Provider und Key (Discord nach Sponsor-Credits fragen)
- [ ] Mentor-Interview mit Talona: Ergebnis in §1 eintragen
- [ ] Studienzahlen aus §1 mit Originalquellen verifizieren
- [ ] Klären, ob das private Repo in eine Talona- bzw. proximata-Org übertragen werden muss
- [ ] Eskalationsfrist und Löschfrist für die Demo festlegen
