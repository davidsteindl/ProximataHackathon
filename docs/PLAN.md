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
| **Plan** | CAD-Zeichnung eines Planblatts (im MVP DXF), z. B. Grundriss 3. OG. Räumliche Quelle für Zonen, Bauteile und das 3D-Modell |
| **Layer** | CAD-Ebene, die den Typ eines Elements festlegt (Wand, Tür, Sanitär, Raumstempel …) |
| **Plan-Diff** | Strukturierter Unterschied zwischen zwei Revisionen eines Plans: welche Elemente in welchen Zonen hinzugekommen, entfernt oder verschoben sind |
| **Task** | Geplanter Arbeitsschritt aus dem Terminplan (Gewerk, Zone, Zeitraum, Vorgänger) |
| **Crew** | Ausführende Gruppe eines Gewerks mit einem **Crew Lead** |
| **Superintendent** | Bauleiter, trifft Entscheidungen |
| **Revision** | Version eines Plans/Planblatts; betrifft Zonen; eine aus Nachrichten extrahierte Crew-Bestätigung zählt erst nach menschlicher Nachweisbestätigung (§3.2) |
| **Inspection** | Abnahme einer Zone (ausstehend / bestanden / nicht bestanden); ein extrahiertes Ergebnis ist zunächst eine unbestätigte Aussage, kein erfüllungsrelevanter Nachweis |
| **Source Message** | Rohe eingehende Nachricht (Mail, Telegram, Seed), immer mit Herkunft |
| **Event** | Strukturierte Information mit Quelle (wer, Zone, was, wann, Absicht). LLM-extrahierte Aussagen sind zunächst unbestätigt; deterministische Events, z. B. Plan-Diffs, bleiben als solche gekennzeichnet |
| **Evidence (Nachweis)** | Quellengebundener Beleg für eine konkrete Precondition (Zone, Inspection/Task bzw. Crew und Revision); LLM-extrahierte Aussagen zählen erst nach ausdrücklicher menschlicher Bestätigung. Prüfstatus: unbestätigt / bestätigt / abgelehnt; Bestätigung mit Person, Zeitpunkt und Quelle |
| **Precondition** | Bedingung vor dem Start eines Tasks in einer Zone; Bewertung: erfüllt / nicht erfüllt / unbekannt / widersprüchlich. Nur gültige Nachweise können sie erfüllen (§3.2) |
| **Flag** | Erkanntes Problem. Bewusst **nicht** „Issue“, um Verwechslung mit GitHub-Issues zu vermeiden |
| **Proposal** | Handlungsvorschlag des LLM zu einem Flag, braucht menschliche Freigabe |
| **Feedback** | Menschliche Bewertung eines Flags, plus Begründung: *bestätigt* (Problem ist echt; beim Übergang zu „zur Kenntnis genommen“), *Fehlalarm* oder *erledigt* (beide schließen den Flag) |
| **Site Knowledge** | Aus Feedback gelerntes Wissen, z. B. Begriffe und fallbezogene Extraktionskorrekturen; ersetzt keine Nachweisbestätigung und deaktiviert keine Sicherheitsprüfung |

---

## 3. Kernkonzepte

### 3.1 Ein Muster für alle Konflikte
Jeder Konflikt hat dieselbe Form: **In Zone X steht Arbeit Y an, aber Precondition Z ist nicht erfüllt.**
Ein neuer Konflikttyp ist damit nur eine neue Precondition, keine neue Architektur.

| Typ | Precondition | Status |
|---|---|---|
| **A: Wand zu vor Abnahme** | Die nötige Inspection der Zone ist durch gültigen Nachweis als bestanden bestätigt | MVP |
| **B: Änderung nicht angekommen** | Für die ausführende Crew liegt ein gültiger Nachweis der Bestätigung der neuesten Revision der Zone vor | MVP |
| **C: Falsche Reihenfolge** | Abschluss der Vorgänger-Task(s) laut Terminplan ist durch gültige Nachweise bestätigt | Stretch |

### 3.2 Wer entscheidet was (Autonomie-Grenze)
- **LLM:** Extraktion (Source Message → Event), Erklärung von Flags, Proposals, Beantwortung von Fragen. **Rein beratend. Das LLM trifft keine Entscheidungen und löst keine Aktionen aus, die über Information hinausgehen.**
- **Regeln (deterministisch):** Prüfen Preconditions anhand gültiger Nachweise und erzeugen Flags. Dadurch reproduzierbar und erklärbar. Ein LLM-Event allein kann keine Precondition erfüllen.
- **Automatisch (ohne Mensch):** Prüfung bei jedem neuen Event, täglicher Morgen-Scan („Was ist morgen gefährdet?“), **faktische Benachrichtigung** der verantwortlichen Person mit Quelle, Eskalation bei ausbleibender Reaktion. *(Stretch)* Faktischer Hinweis an Crew Lead und Crew-Gruppe der **blockierten Tasks** (Tasks der Zone und ihre Nachfolger laut Terminplan): welche Precondition fehlt, Quelle, „vor Beginn mit dem Superintendent abstimmen“. Das ist eine Information, keine Arbeitsanweisung.
- **Nur mit menschlicher Freigabe:** Jede Handlung (Task verschieben, Crew umplanen, Arbeit stoppen), die Bestätigung extrahierter Nachweise und jeder Abschluss eines Flags. Die ausdrückliche Anweisung „Tasks pausiert, nicht ohne Rücksprache mit dem Superintendent fortsetzen“ geht erst nach Freigabe des entsprechenden Proposals raus.

**Nachweisbestätigung (verbindlich für alle Precondition-Typen):**

- Das LLM erzeugt Aussagen mit Quelle und relevantem Zitat; auch hohe `confidence` ist keine Bestätigung. Eine Meldung „Inspection bestanden“, „Rev D gelesen“ oder „Task fertig“ bleibt unbestätigt, bis ein zuständiger Mensch sie im Dashboard anhand der Quelle prüft und ausdrücklich bestätigt oder ablehnt. Nicht jedes Event braucht diese Prüfung: Arbeitsankündigungen dürfen sofort die Regelprüfung auslösen.
- Die Bestätigung bezieht sich auf eine konkrete Aussage und ihren Geltungsbereich: Zone, erforderliche Inspection bzw. Task oder Crew und konkrete Revision. Veraltete oder unpassende Nachweise erfüllen die Precondition nicht. Die API validiert Geltungsbereich und Prüfstatus; LLM, Chat und MCP können Nachweise weder bestätigen noch ablehnen oder ihren Prüfstatus übersteuern. Im MVP ist dies eine explizite menschliche Dashboard-Aktion mit Rollenumschalter (§4), keine Behauptung produktionsreifer Authentifizierung.
- Prüfstatus des Nachweises und Bewertung der Precondition sind getrennt: **erfüllt** = gültiger bestätigter positiver Nachweis; **nicht erfüllt** = gültiger bestätigter negativer Nachweis; **unbekannt** = kein ausreichender Nachweis; **widersprüchlich** = relevante Aussagen/Nachweise stehen ungeklärt im Widerspruch. Relevante neue Gegenmeldungen werden zur Prüfung sichtbar gemacht; das LLM überschreibt oder widerruft keine menschlichen Bestätigungen. Solange der Widerspruch ungeklärt ist, gilt die Precondition nicht als erfüllt.
- Bei anstehender oder beginnender Arbeit führen **nicht erfüllt**, **unbekannt** und **widersprüchlich** zur Konfliktprüfung und ggf. zum deduplizierten Flag. Die Erklärung unterscheidet „nicht bestanden“, „Nachweis fehlt/unbestätigt“ und „Angaben widersprüchlich“. Fehlende Daten sind keine Freigabe.
- Nachweise können auch ohne bestehenden Flag geprüft werden. Nach jeder Bestätigung, Ablehnung oder Klärung wird die Regelprüfung erneut ausgeführt; Audit-Einträge enthalten Person, Zeitpunkt, Quelle, Geltungsbereich und Entscheidung. Nachweisbestätigung, Kenntnisnahme eines Flags, Proposal-Freigabe und Flag-Abschluss sind getrennte Aktionen.
- **Seed/Replay:** Explizit gekennzeichnete synthetische Ausgangsnachweise dürfen den bestätigten Demo-Ausgangsstand herstellen; Herkunft und Import werden protokolliert, ohne eine menschliche Bestätigung zu erfinden. Neu eingespielte LLM-Aussagen bleiben auch offline unbestätigt. **Deterministische CAD-Events** dürfen Geometrie und betroffene Zonen aktualisieren und Prüfungen auslösen; sie bestätigen weder Abnahmen noch Crew-Kenntnisnahmen oder Task-Abschlüsse.

### 3.3 Flag-Lebenszyklus: nichts geht verloren
`erkannt → benachrichtigt → zur Kenntnis genommen → in Bearbeitung → erledigt | Fehlalarm`

- Jeder Flag hat **eine verantwortliche Person** (über Zone und Gewerk der Crew Lead; Entscheidungen liegen beim Superintendent).
- Ein Flag bleibt **sichtbar offen**, bis eine verantwortliche Person ihn schließt. Schließen nur mit **Feedback** (*erledigt* oder *Fehlalarm*). Das Feedback *bestätigt* („Problem ist echt“) gehört zum Übergang „zur Kenntnis genommen“.
- **Das System schließt nie selbst.** Ist eine Precondition nach Prüfung gültiger Nachweise nachträglich erfüllt, markiert es den Flag nur als „Vorbedingung erfüllt, wartet auf menschlichen Flag-Abschluss“. Eine unbestätigte LLM-Aussage erzeugt diesen Erfüllt-Hinweis nicht. Die Nachweisbestätigung schließt keinen Flag; Feedback „bestätigt“ am Flag bestätigt umgekehrt keinen Nachweis.
- **Eskalation:** Bleibt ein Flag X Stunden ohne Reaktion, geht er an die nächsthöhere Stelle. X ist konfigurierbar.
- **Deduplizierung:** Wird derselbe Konflikt erneut erkannt, wird das an den bestehenden offenen Flag angehängt, kein neuer Flag.
- **Audit-Trail:** Jede Zustandsänderung mit *wer, wann, über welchen Kanal, auf Basis welcher Quelle*. Jeder Flag verweist auf die auslösenden Source Messages (mindestens als Zitat).

### 3.4 Learning Loop
- Feedback (*bestätigt / Fehlalarm / erledigt* + Begründung) wird zu **Site Knowledge**. Beispiele: „‚die B-Wohnungen‘ = 2B, 3B, 4B“ oder eine quellengebundene Korrektur einer falsch erkannten Arbeitsankündigung. Eine Aussage über mündliche Freigaben ersetzt niemals die Bestätigung eines konkreten Nachweises (§3.2).
- Site Knowledge wirkt zurück auf die **LLM-Extraktion und -Erklärung** (als Kontext). Fallbezogene Extraktionskorrekturen dürfen einen belegten Fehlalarm im Replay vermeiden, mit sichtbarem Bezug auf Quelle und Feedback. Ein einzelnes Feedback bestätigt keine anderen Nachweise und unterdrückt keine künftigen echten Konflikte.
- **Keine automatische Abschwächung von Sicherheitsprüfungen:** Änderungen an sicherheitsrelevanten Regeln oder Nachweisanforderungen sind gesondert menschlich freizugeben, eng im Geltungsbereich zu begrenzen und zu auditieren. Die Nachweisbestätigungspflicht bleibt bestehen. Im MVP korrigiert der Learning Loop die Extraktion, statt Sicherheitsregeln automatisch zu ändern.
- **Ziel:** Gleiche Fehler bzw. Fehlalarme treten nicht wieder auf. Im Dashboard sichtbar als Kennzahl (Anteil bestätigter Flags über die Zeit).
- **Vision (nur im Pitch):** Lernen über Projekte hinweg, Fotos gegen Pläne prüfen, Kontext für Roboter.

### 3.5 Baupläne (DXF im MVP) als räumliche Grundlage
- **Der MVP setzt DXF-Dateien mit der dokumentierten Layer-Konvention voraus**, ein Plan pro Etage. Neue Revisionen kommen als DXF-Anhang per Mail oder als Seed. DWG-Import und DWG-Export gehören zu einer späteren Erweiterung.
- **Aus einem Plan entstehen strukturierte Daten:** Räume/Wohnungen (geschlossene Polylinien plus Raumstempel-Text), Wände, Türen, Sanitär- und Elektro-Elemente. Welcher Layer was bedeutet, regelt eine **Layer-Konvention** (orientiert an AIA/US National CAD Standard bzw. ISO 13567, z. B. `A-WALL`, `A-DOOR`, `P-PLUM`). Die synthetischen Pläne halten sich daran.
- **Layer-Konvention (festgelegt, Details und Generator in [`cad/README.md`](../cad/README.md)):**

  | Layer | Element | Darstellung |
  |---|---|---|
  | `A-WALL-EXTR` | Außenwand | Polylinie auf der Wandachse, Breite = Wandstärke |
  | `A-WALL` | Innen-, Trenn- und Flurwand | Polylinie auf der Wandachse, Breite = Wandstärke; Türöffnungen sind Lücken |
  | `A-DOOR` | Tür | Block `DOOR` am Anschlag, Skalierung = Türbreite |
  | `A-AREA-UNIT` / `A-AREA-UNIT-IDEN` | Wohnung | Geschlossene Polylinie / Text = Zonen-ID (z. B. `3B`) |
  | `A-AREA` / `A-AREA-IDEN` | Raum | Geschlossene Polylinie / Raumstempel-Text = Zonen-ID (z. B. `3B-BATH`) |
  | `P-FIXT` | Sanitärobjekt | Block `WC`, `SINK`, `SHOWER` |
  | `P-SANR` | Abwasser | Polylinie = Leitung, Block `STACK` = Fallstrang |
  | `A-ANNO-TTLB` | Plankopf (Blatt, Etage, Revision) | Text; wird beim Parsen und im Plan-Diff ignoriert |

  Zonen-IDs aus dem Seed (#5): `B1` → `F1`–`F4` → Wohnungen `1A`–`4D` → Räume `<Wohnung>-<LIV|BED|KIT|HALL|BATH|STOR>`; Flure sind gezeichnet, aber ohne Zone. Plan `A-10<n>` gehört zu Etage `F<n>`. Jedes Element trägt eine über Revisionen stabile ID als XDATA (`SITEMIND`); die in Rev D verschobene Badwand trägt die Element-Zone `3B-BATH-WALL`.
- **Synthetische DXF-Pläne:** `cad/plans/` enthält Rev C für alle Etagen und Rev D für A-103. Seed-Revisionen verweisen auf `.dxf`; die Hero-Mail hängt `A-103_RevD.dxf` an.
- **Separat in Gebäude-Metadaten:** Etagenhöhen, Zuordnung Plan → Etage, Zonen-IDs. Die Zonenhierarchie ist also unabhängig vom CAD-Parsing sofort verfügbar. Das Parsing füllt die Geometrie nach und verknüpft sie über den Raumstempel mit den Zonen-IDs.
- **Gemeinsame Zonen-IDs für #3/#5:** Gebäude `B1`, Etagen `F1`–`F4`, Wohnungen `1A`–`4D`, je Wohnung die Räume `LIV`, `BED`, `KIT`, `HALL`, `BATH`, `STOR` (z. B. Hero-Bad `3B-BATH`), Badwand `3B-BATH-WALL`. CAD-Stempel verwenden exakt die IDs. Hierarchie, Plan-Zuordnung und Seed-Vertrag stehen in [SITE_RECORD.md](SITE_RECORD.md).
- **Eine Quelle für alle:** Die extrahierte Geometrie wird über die API bereitgestellt. Die 3D-Ansicht (Wände auf Etagenhöhe extrudiert) und der Agent nutzen **dieselben** Daten. Der Agent bekommt nie rohe CAD-Dateien, sondern Abfragen wie „Was ist in Zone X?“ oder „Was hat sich zwischen Rev C und Rev D in Zone X geändert?“.
- **Geometrievertrag (#15):** `/geometry` liefert die höchste importierte Revision je Plan oder eine explizite `revision_id`, gefiltert nach Etage/Zone. Koordinaten und Etagen-Metadaten sind in Metern; Original-DXF und Geometrie werden je Revision gespeichert. Neue CAD-Revisionen erzeugen keine Bestätigungen/Nachweise; ihre betroffenen Zonen (`Revision.zone_ids`) bleiben bis zur Ermittlung durch #17 leer. Vollständiger Import-, Speicher- und REST-Vertrag: [CAD-PIPELINE.md](CAD-PIPELINE.md).
- **Plan-Diff statt Vision:** Eine neue Revision wird geometrisch mit der vorherigen verglichen. Das Ergebnis sind die betroffenen Zonen, und das ist der deterministische Auslöser für Konflikttyp B. Die Revisionsnotiz in der Mail dient dem LLM nur zur Erklärung. **Fallback**, falls der Diff nicht rechtzeitig steht: Die betroffenen Zonen kommen aus der Revisionsnotiz (LLM-Extraktion). Diese Angaben bleiben als unbestätigt gekennzeichnet und dürfen Warnungen auslösen, aber keine Crew-Bestätigung oder andere Precondition erfüllen.
- **Erweiterung für DWG:** Ein separater Konverter kann DWG vor derselben DXF-Extraktion umwandeln. Dabei müssen Layer, Beschriftungen, Einheiten und relevante Geometrie erhalten bleiben; das Original-DWG bleibt als Quelle gespeichert. Der bestehende LibreDWG-Prototyp aus #4 ist vorbereitet, seine automatische Anbindung ist außerhalb des MVP. Auch bei direktem DXF-Import bleibt die Originaldatei mit ihrer Revision als Quelle erhalten.


### 3.6 Raumansicht, Raumstatus und Neuigkeiten
- **Raumansicht im Dashboard:** Jeder Raum bzw. jede Zone ist per URL `/zones/<zoneId>` aufrufbar (z. B. `/zones/3B-BATH`). Links: 3D-Ansicht (#16), Etage isoliert und in der Draufsicht, ausgewählter Raum hervorgehoben. Rechts: Seitenleiste mit Widgets, oben breit **Zustand** (Precondition-Bewertungen, offene Flags), unten **anstehende Tasks** und **Plan & Abnahmen** (aktuelle Revision, Kenntnisnahmen, Inspections mit Nachweisstatus). Die genaue Gestaltung legt das Mockup (#35) fest.
- **Raumstatus per Telegram:** Fragt der Superintendent per Telegram nach einem Raum, bekommt er eine strukturierte Antwort mit denselben Inhalten wie die Widgets, jeweils mit Quelle, plus Link auf die Raumansicht. Die Inhalte stammen nur aus dem Record (MCP-Tools, §5); unbestätigte Aussagen und Widersprüche werden als solche gekennzeichnet.
- **Neuigkeiten-Feed:** Startseite für den Superintendent: chronologisch neue Events, Revisionen, Nachweisentscheidungen, Flag-Änderungen und abgeschlossene Tasks, filterbar nach Zone, jeweils mit Link zur Raumansicht bzw. zum Flag. Ein Task gilt nur mit bestätigtem Nachweis als abgeschlossen; unbestätigte Abschlussmeldungen erscheinen als solche gekennzeichnet. Keine Auswertungen pro Person (§6).

---

## 4. Scope

### MVP (muss stehen)
1. Gebäude-Metadaten und Seed-Daten (Zonen, Terminplan, Crews, Revisionen, Inspections, Hero-Szenario), dazu **synthetische DXF-Pläne** pro Etage inkl. Rev C und Rev D für 3B
2. **CAD-Pipeline:** DXF → strukturierte Geometrie mit Zonenzuordnung; Plan-Diff zwischen Revisionen (§3.5)
3. Ingestion-Eingang, unabhängig von der Quelle, mit LLM-Extraktion und Weitergabe von DXF-Anhängen aus Mails an die CAD-Pipeline; Aussagen mit Prüfstatus, Quelle und Zitat
4. Regel-Engine mit Konflikttypen A und B, Nachweisprüfung gemäß §3.2, Prüfung bei jedem Event, jeder Nachweisentscheidung und Morgen-Scan
5. Flag-Lebenszyklus mit Audit-Trail, Eskalation, Deduplizierung
6. **Gmail** ein und aus (Revisionen als DXF und Inspektionsergebnisse rein; Warnungen und Freigabe-Anfragen raus)
7. **Telegram** ein und aus (Gruppenchat mitlesen, Warnungen und Antworten an Crew Leads), inkl. Compliance (§6). Der Superintendent kann per Telegram den **Zustand eines Raums** abfragen und bekommt eine strukturierte Antwort aus dem Record plus Link auf die Raumansicht im Dashboard (§3.6)
8. Terminplan als Seed-Datei (CSV oder Export im MS-Project-Stil)
9. Dashboard: Übersicht, Flag-Inbox mit Detail, Quellen und Feedback, separate Prüfung/Bestätigung/Ablehnung von Nachweisen (auch ohne Flag), Freigabe von Proposals, Timeline der Änderungen und Entscheidungen. Startseite für den Superintendent mit **Neuigkeiten-Feed** (§3.6)
10. 3D-Ansicht, **erzeugt aus der Geometrie der DXF-Pläne** (einzige räumliche Ansicht). **Raumansicht:** ausgewählter Raum hervorgehoben (Etage isoliert, Draufsicht), daneben eine Seitenleiste mit Widgets; per URL direkt aufrufbar (§3.6)
11. REST-API und **MCP-Server** (inkl. Abfragen zu Plänen und Plan-Diffs)
12. Learning Loop (§3.4)
13. Replay-Skript mit Reset
14. Chat (Dashboard und Telegram-Q&A) über die eigenen MCP-Tools. **Erst nach Abnahme der kritischen Pakete.**

### Stretch (nur wenn das MVP zuverlässig läuft)
- Konflikttyp C (falsche Reihenfolge)
- Fotos aus Telegram per Vision-LLM als Beleg („Wand ist zu“)
- Blockierte Tasks bei einem Konflikt ermitteln und deren Crews faktisch benachrichtigen; „pausiert“-Hinweis nach Proposal-Freigabe (§3.2)

### Bewusst out of scope
- Automatischer DWG-Import und DWG-Export. Der MVP nimmt DXF nach Layer-Konvention an; der LibreDWG-Prototyp bleibt als Grundlage für die spätere Konverter-Anbindung erhalten.
- BIM/IFC-Import. *Begründung:* Bei Talonas Zielkunden (kleine und mittlere GCs) liegen Pläne als 2D-CAD (DWG) bzw. PDF vor, nicht als BIM.
- Beliebige CAD-Pläne fremder Architekten ohne Layer-Konvention. In Production bräuchte es eine Layer-Zuordnung pro Architekt (später ein Kandidat für Site Knowledge).
- PDF-Pläne und Vergleich von Plänen per Vision (wir vergleichen CAD-Geometrie, siehe §3.5)
- WhatsApp (Twilio-Sandbox kann keine Gruppen). In Production über denselben Adapter wie Telegram.
- Echtes Nachtrainieren von Modellen
- Vollständiges Auth- und Rechte-System im Dashboard. Im MVP gibt es einen Rollen-Umschalter (Superintendent / Crew Lead), in `COMPLIANCE.md` als Production-Lücke dokumentiert.

---

## 5. Architektur und Stack (gesetzt)

| Dienst (docker compose) | Aufgabe | Stack |
|---|---|---|
| `db` | Persistenz | PostgreSQL |
| `api` | REST-API, Regel-Engine, Flag-Lebenszyklus, Learning Loop, CAD-Pipeline (DXF-Parsing, Plan-Diff) | Python, FastAPI |
| `worker` | Gmail- und Telegram-Polling, Morgen-Scan, Eskalationstimer | Python, gleiche Codebasis wie `api` |
| `mcp` | MCP-Server für externe Agents. Spricht **nur über die REST-API**, nie direkt mit der DB | Python, offizielles MCP-SDK |
| `web` | Dashboard, Chat, 3D-Ansicht | Next.js, React, Three.js |

Grundsätze:
- **Alles startet per `docker compose up`.** Die Jury muss es nach README nachvollziehen können.
- **Der API-Vertrag ist die OpenAPI-Spezifikation von FastAPI.** Das Frontend arbeitet gegen diesen Vertrag.
- **Statischer Site Record (#5):** SQLAlchemy + Alembic (ein Migrations-Head); API-Start migriert, Seed-Import erfolgt explizit und ersetzt den statischen Ausgangszustand atomar. Schema- und REST-Vertrag einschließlich Zonen-IDs: [SITE_RECORD.md](SITE_RECORD.md). Noch keine Events, Flags oder CAD-Geometrie.
- **Evidence-Vertrag (#5, Alignment #30):** Nachweis, extrahierte Aussage und Domänen-Ergebnis bleiben getrennt. Quellen/Zitate, genauer Geltungsbereich und append-only Prüf-Historie sind über `/evidence` lesbar. Nur explizite synthetische Seed-Ausgangsnachweise starten bestätigt, mit Import-Herkunft ohne menschlichen Prüfer. Gegenbeispiele starten unbestätigt; keine automatische Übernahme in Inspection-/Task-/Crew-Ergebnisse. Speicherung und Übergabe an Extraktion (#6) sowie menschliche Prüf-Aktion (#9): [SITE_RECORD.md](SITE_RECORD.md#evidence-confirmation-contract-alignment-30).
- **`api` ist der einzige Dienst mit Zugriff auf die DB.** `worker`, `mcp` und `web` sprechen ausschließlich über die REST-API.
- **Alle Quellen laufen über denselben Ingestion-Eingang.** Ein neuer Kanal ist nur ein neuer Adapter.
- **Ingestion-Vertrag (#6):** `Source Message` speichert Kanal, Quellkonto/Chat, externe ID, Zeit, Text und Originalanhänge. `(channel, source_key, external_id)` ist eindeutig. Extrahierte `Event`s verweisen mit Zitat auf diese Quelle; erfüllungsrelevante Aussagen verweisen auf separate, zunächst unbestätigte `Evidence`. Tabellen und REST-Vertrag sind in [INGESTION.md](INGESTION.md) dokumentiert.
- **Gmail inbound (#11):** Der `worker` liest nur das verifizierte Projektkonto/Label mit `gmail.readonly` und übergibt Betreff, Text und Originalanhänge an die Ingestion. Die exakte Quellenabfrage (`GET /source-messages`) überspringt verarbeitete Quellen ohne Worker-DB-Zugriff. Vertrag: [INGESTION.md](INGESTION.md#gmail-adapter-identity-lookup-11); Setup: [GMAIL.md](GMAIL.md).
- **Ausgehende Nachrichten laufen über eine Outbox:** `api` legt jede Nachricht an, `worker` versendet sie und meldet den Status zurück. Keine Benachrichtigung geht verloren, jede steht im Audit-Trail.
- **Der Chat-Agent lebt in `api` als MCP-Client** des eigenen `mcp`-Servers. Er nutzt dieselben Tools wie externe Agents.
- **Kanal-Zugangsdaten** (Gmail, Telegram) liegen nur im `worker`, der LLM-Key nur in `api`.
- **Diagramme:** siehe [README → Architektur](../README.md#architektur). Plan und Diagramme werden gemeinsam geändert.
- **CAD-Eingang im MVP: DXF direkt in die Extraktion.** Für die spätere DWG-Erweiterung ist LibreDWG (`dwg2dxf`, GPL-3.0-or-later) als separates Programm in einem optionalen Container vorbereitet. Entscheidung, Testanleitung und bekannte Grenzen: [CAD-Konverter](CAD-CONVERTER.md). Die Extraktion bleibt unabhängig davon, ob eine DXF-Datei direkt geliefert oder konvertiert wurde.
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
- **Lizenzen der CAD-Werkzeuge:** Der Code gehört Talona und ist proprietär. GPL-Werkzeuge (z. B. LibreDWG) nur als **separates Programm** aufrufen, nie als Library einbinden. Die ODA-Lizenz vor Nutzung prüfen. Python-Libraries für DXF nur mit permissiver Lizenz.

**Dokumentieren in `COMPLIANCE.md`:**
- Rechtsgrundlage
- Betriebsvereinbarung (AT: ArbVG §96/§96a), da das System potenziell Leistung überwachen könnte
- Auftragsverarbeitungsvertrag, EU-Region und Zero Data Retention beim LLM-Provider
- Telegram: Server außerhalb der EU, keine Ende-zu-Ende-Verschlüsselung → in Production WhatsApp Business oder Teams
- Prompt Injection und Extraktionsfehler: LLM-Ausgaben bleiben unbestätigte Aussagen; Nachweisbestätigung und API-Prüfungen begrenzen den Einfluss auf Preconditions (§3.2). Die Beratungsrolle allein garantiert keine korrekten Eingangsdaten.
- Fehlende Dashboard-Authentifizierung

**Demo:** Ausschließlich synthetische Daten und Test-Accounts aus dem Team.

---

## 7. Hero-Szenario (Basis für Seed, Replay, Video)

Fiktives Projekt: Wohnbau, 1 Gebäude, 4 Etagen, je 4 Wohnungen (A–D). Pro Etage ein synthetischer DXF-Grundriss. Detailliert gezeichnet (Wände, Sanitär) ist mindestens die Hero-Wohnung 3B, in Rev C und Rev D.

| Zeitpunkt (simuliert) | Quelle | Was passiert | Erwartete Reaktion |
|---|---|---|---|
| Tag 1, 07:00 | Terminplan | Trockenbau 3. OG startet an Tag 3 | – |
| Tag 1, 10:15 | Gmail (Architekt) | Mail mit `A-103_RevD.dxf`: Badwand 3B um 30 cm verschoben, Abwasserleitung neu geführt | Plan-Diff Rev C → Rev D ergibt Zone 3B → **Flag B**: Installateur-Crew hat nur Rev C bestätigt → Warnung an den Crew Lead; 3D zeigt die geänderte Wand |
| Tag 1, 11:00 | Telegram + Dashboard | Crew Lead: „Warnung gesehen“ | Flag B wird durch menschliche Aktion „zur Kenntnis genommen“; dies ist kein Nachweis, dass Rev D gelesen oder umgesetzt wurde |
| Tag 2, 16:40 | Gmail (Inspektor) | Abnahme der Rohinstallation im 3. OG verschoben auf Tag 4 | Unbestätigtes Event „Inspection ausstehend“; keine erfüllte Precondition |
| Tag 2, 17:00 | Telegram | „Abnahme dürfte passen“ | Unklare Aussage bleibt unbestätigt; ersetzt den fehlenden Abnahmenachweis nicht |
| Tag 2, 18:05 | Telegram (Trockenbau-Gruppe) | „morgen früh machen wir 3B zu, platten sind da“ | **Flag A (kritisch)**: Abnahme nicht nachgewiesen und Kenntnisnahme von Rev D nicht bestätigt → 3D: Wand 3B rot → Superintendent bekommt Proposal „Trockenbau 3B verschieben, Crew auf 3A/3C umplanen“ → Freigabe → Crew Lead informiert |
| Tag 2, 18:30 | Telegram | Crew fragt: „welcher plan gilt für 3B?“ | Antwort aus dem Record mit Quelle (Rev D, Mail vom Tag 1) |
| Tag 2, 18:45 | Telegram (Superintendent) | „wie ist der Stand im Bad 3B?“ | Strukturierte Antwort: Revision und Kenntnisnahmen, Inspection mit Nachweisstatus, offener Flag A, anstehende Tasks, letzte Änderungen, jeweils mit Quelle; Link auf `/zones/3B-BATH` im Dashboard, dort ist das Bad in der Draufsicht hervorgehoben |
| Tag 3 | Dashboard | Superintendent schließt Flag A als *erledigt* mit Begründung „Trockenbau verschoben“ | Audit-Trail vollständig; Abschluss bestätigt keine Inspection und erfüllt keine andere Precondition |
| Nach Abnahme an Tag 4 | Gmail + Dashboard | Eindeutiges positives Abnahmeergebnis trifft ein; zuständiger Mensch prüft Quelle und bestätigt den Nachweis für die konkrete Inspection in 3B | Erst danach ist Precondition A erfüllt; ein ggf. noch offener Flag bleibt bis zum separaten menschlichen Abschluss offen |
| Learning-Loop-Moment | Telegram + Dashboard | Eine als Arbeitsankündigung fehlinterpretierte Frage erzeugt einen Fehlalarm; menschliches Feedback korrigiert die Extraktion; Replay neu | Derselbe Fall wird mit sichtbarem Quellen-/Feedback-Bezug richtig interpretiert; echte Arbeitsankündigungen ohne bestätigten Nachweis erzeugen weiterhin Flags |

Das Replay-Skript spielt diese Abfolge über die **echten** Kanäle ein (echte Mails von einem Test-Account, echte Telegram-Nachrichten) und hat einen Offline-Modus (§5). Bei menschlichen Entscheidungen pausiert es für die Dashboard-Aktion; es bestätigt weder Nachweise noch Proposals oder Flag-Abschlüsse automatisch.

---

## 8. Arbeitspakete (werden zu GitHub-Issues)

Keine feste Rollenverteilung, jeder nimmt sich Issues selbst. Die Abhängigkeiten bestimmen die Reihenfolge.

| ID | Paket | Abhängig von | Meilenstein |
|---|---|---|---|
| WP0 | Repo-Grundgerüst: Compose mit allen 5 Diensten (lauffähige Hüllen), minimale CI, `.env.example`, README-Grundgerüst | – | M0 |
| WP1 | Domänenmodell, DB-Schema und API-Vertrag inkl. Nachweis-Prüfstatus, Geltungsbereich, menschlicher Bestätigungsaktion und Audit (§2/§3.2) | WP0 | M0 |
| WP2 | Seed-Daten: Gebäude-Metadaten (Zonen-IDs, Etagenhöhen, Plan ↔ Etage), Terminplan, Crews, Revisionen, Inspections, Hero-Szenario aus §7. explizit gekennzeichnete synthetische Ausgangsnachweise und unbestätigte Gegenbeispiele; Inhalte können sofort als Dateien entstehen | WP1 (für den Import) | M0 |
| WP15 | Synthetische DXF-Pläne nach Layer-Konvention (§3.5): pro Etage ein Grundriss, für 3B Rev C und Rev D. Raumstempel passen zu den Zonen-IDs aus WP2 | – (sofort startbar) | M0 |
| WP16 | CAD-Pipeline: DXF-Extraktion von Räumen, Wänden und Bauteilen, Zuordnung zu Zonen, Geometrie über die API | WP1, WP15 | M1 |
| WP17 | Plan-Diff zwischen Revisionen → betroffene Zonen als Event (Auslöser für Konflikttyp B) | WP16, WP3 | M2 (bis dahin Fallback über Revisionsnotiz) |
| WP3 | Ingestion-Eingang und LLM-Extraktion (Source Message → unbestätigtes Event, Quelle/Zitat, Zuordnung zu Zonen; keine automatische Nachweisbestätigung) | WP1 | M1 |
| WP4 | Regel-Engine: Preconditions A und B, gültige Nachweise und vier Bewertungen (§3.2); Prüfung bei Events, Nachweisentscheidungen und Morgen-Scan | WP1, WP2 | M1 |
| WP5 | Flag-Lebenszyklus: Zustände, Verantwortliche, Audit-Trail, Deduplizierung, Eskalation, Proposals; Flag-Abschluss getrennt von Nachweisbestätigung | WP1 | M1 |
| WP6 | Gmail-Adapter ein und aus | WP3, WP5 | M1 |
| WP7 | Telegram-Adapter ein und aus, inkl. Compliance-Features (§6) | WP3, WP5 | M2 |
| WP8 | Dashboard: Übersicht, Flag-Inbox, Detail mit Quellen, Feedback, separate Nachweisprüfung auch ohne Flag, Freigabe, Timeline | WP1 (Vertrag), WP5 | M1 (Grundversion) / M2 |
| WP9 | 3D-Ansicht: extrudiert aus der Plan-Geometrie der API (Wände auf Etagenhöhe), Färbung nach Flag-Status, Klick öffnet Detail. Prototyp mit Mock-Geometrie sofort möglich | WP16 (Geometrie), WP5 | M2 |
| WP10 | MCP-Server: Tools u. a. Zonenstatus, offene Flags, Änderungshistorie, Plan-Inhalt einer Zone, Plan-Diff, Suche/Frage, Proposal anlegen; Prüfstatus in Antworten, keine Nachweisbestätigung durch Agents | WP1, WP5, WP16 | M2 |
| WP11 | Chat-Agent für Dashboard und Telegram-Q&A über die eigenen MCP-Tools | WP10, WP7 | M3 |
| WP12 | Learning Loop: Feedback → Site Knowledge → fallbezogene Extraktionskorrektur; keine automatische Abschwächung von Sicherheitsregeln; Kennzahl im Dashboard | WP3, WP4, WP5 | M2/M3 |
| WP13 | Replay-Skript mit simulierter Uhr, Reset, Offline-Modus; menschliche Nachweisbestätigung und unsichere Gegenbeispiele | WP2, WP6, WP7 | M2 |
| WP14 | Research, Mentor-Interview, Pitch, 3-Min-Video, `COMPLIANCE.md`, finale README, Abgabe | läuft parallel | M4 |
| S1 | Stretch: Konflikttyp C mit gültigen Abschlussnachweisen gemäß §3.2 | WP4 | M3 |
| S2 | Stretch: Fotos als Beleg (Vision); LLM-Befunde bleiben unbestätigte Aussagen gemäß §3.2 | WP7 | M3 |
| WP18 | Neuigkeiten-Feed: chronologische Übersicht für den Superintendent über Events, Revisionen, Nachweisentscheidungen, Flag-Änderungen und abgeschlossene Tasks; API + Dashboard-Startseite (§3.6) | WP3, WP5 | M3 |
| S3 | Stretch: blockierte Tasks bei Konflikten + faktische Hinweise an deren Crews; „pausiert“-Hinweis nach Proposal-Freigabe (§3.2) | WP4, WP5, WP6 | M3 |

**Sofort parallel zu WP0/WP1 (keine Code-Abhängigkeit):** WP15 (synthetische DXF-Pläne), Google-Cloud-Projekt und Gmail-OAuth einrichten (OAuth-Testmodus: Test-User eintragen; Refresh-Tokens laufen nach 7 Tagen ab), Telegram-Bot anlegen (Privacy Mode aus), LLM-Key besorgen, Seed-Inhalte schreiben, 3D-Prototyp, Research und Mentor-Interview.

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
| **M0 Fundament** | Fr ~19:30 | WP0–WP2 gemergt; synthetische DXFs (WP15) liegen vor; Accounts, Keys und Konverter-Wahl geklärt |
| **M1 Tracer Bullet** | Sa ~01:00 | Mail rein → Event → Flag → sichtbar im Dashboard → Warnmail raus, einmal durchgehend; Plan-Geometrie über die API abrufbar |
| **M2 Breite** | Sa ~09:00 | Telegram, Lebenszyklus komplett, 3D eingebunden, MCP, Replay, Morgen-Scan, Eskalation |
| **M3 Feature Freeze** | Sa 12:00 | Chat, Learning Loop, Stretch falls Zeit. **Danach keine neuen Features.** |
| **M4 Abgabe** | Sa 14:30 | Bugfixes, Video (bis ~13:30), README, `COMPLIANCE.md`, `.env.example`, Submission |

Schlaf in Schichten, sodass nachts immer jemand reviewen und mergen kann.

---

## 10. Arbeitsweise

- **Ablauf:** Issue → Branch → PR (verlinkt das Issue) → **1 Approver** → Merge. Kein Review durch alle.
- **CI (minimal, muss grün sein):** Backend-Tests, Frontend-Build und Lint, Prüfung der Compose-Konfiguration. Ein kaputter `main` blockiert alle.
- **Tests:** Jede Logik bekommt Unit-Tests, vor allem Regel-Engine, Lebenszyklus, Deduplizierung, Eskalation, Extraktion (mit gemocktem LLM), CAD-Extraktion und Plan-Diff (gegen die synthetischen Pläne) und Learning Loop. LLM-Aufrufe sind in Tests immer gemockt.
- **Pflichtfälle zur Nachweisgrenze:** Unbestätigte Erfolgsmeldung (auch mit hoher Modellkonfidenz), fehlender Nachweis, falsche Zone/Revision, veralteter Nachweis und widersprüchliche Angaben erfüllen keine Precondition. Menschliche Bestätigung/Ablehnung löst eine erneute Prüfung aus; Bestätigung schließt keinen Flag, Flag-Feedback bestätigt keinen Nachweis. MCP/Chat können keine Bestätigung ausführen. Seed/Reset und Offline-Replay erhalten die Herkunft; Learning korrigiert den Fehlalarm, während echte Konflikte weiterhin geflaggt werden.
- **Schema-Owner:** Wer gerade WP1 hält, koordiniert DB-Migrationen. Migrationen von parallelen PRs kollidieren sonst (gleiche Nummer).
- **Änderungen am API-Vertrag oder Schema:** Kurzer Hinweis an alle, bevor gemergt wird.
- **Definition of Done:** Akzeptanzkriterien erfüllt, Tests grün, läuft per `docker compose up`, keine Secrets im Code.

---

## 11. Bezug zu den Bewertungskriterien

| Kriterium | Punkte | Abgedeckt durch |
|---|---|---|
| Technical implementation | 35 | Hybride Architektur (LLM-Extraktion + deterministische Regeln), CAD-Pipeline mit Plan-Diff, echte Integrationen, MCP, CI und Tests, Compose |
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
- [x] DWG-Konverter gewählt: LibreDWG als separater Prozess; Details in docs/CAD-CONVERTER.md. Lizenz und Plattformen dokumentiert.
- [x] Layer-Konvention für die synthetischen Pläne festgelegt und in §3.5 eingetragen (Details: `cad/README.md`)
- [ ] Mentor fragen: Wie liegen Pläne bei Talonas Kunden typischerweise vor (DWG, PDF, beides)?
