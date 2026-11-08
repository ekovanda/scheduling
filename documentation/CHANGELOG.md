# Technical Changelog

Developer-facing implementation reference for released changes. This document complements the short, business-facing release history in `app/release_info.py`.

## Versioning conventions

- `X.Y.0` — user-visible feature release.
- `X.Y.Z` — fix or small adjustment without a new feature.
- `X.0.0` — significant product change; `1.0.0` marks the first productive release.
- Entries are newest first. Historical entries group related commits approximately; commit hashes are included where useful for tracing.

## [2.0.2] - 2026-11-08

### Fixed: Real Solver Footer Metrics, `block_gap_days` Wiring, Pre-Assigned Highlighting & Multi-Day Holiday Block Gap Relaxation

- **Echte Solver-Metriken & Quartalsnavigation im Dienstplan (`frontend/src/views/MatrixView.tsx`, `frontend/src/lib/api.ts`, `frontend/src/types/api.ts`, `app/api/v1/quarters.py`):**
  - Fußzeile in `MatrixView.tsx` zeigt die tatsächliche `solve_time_seconds`, den echten CP-SAT-Status (`OPTIMAL`, Smart-Stop-Stagnation oder `FEASIBLE`) sowie die quartalsbezogene Anzahl vorbelegter Schichten anstelle statischer Platzhalterwerte (behebt Review-Finding `B7`).
  - `selectedMonth` wird beim Wechsel von `currentQuarterKey` automatisch auf `'ALL'` zurückgesetzt, damit beim Quartalswechsel keine leere Monatsfilterung stehenbleibt.
  - `isShiftPreAssigned()` prüft vorrangig `shift.is_pre_assigned` und gleicht Tagdienste exakt über `pa.shift_type === shift.shift_type` ab, sodass am Wochenende nur die tatsächlich vorbelegte Einzelschicht grün hervorgehoben wird.
  - `blockGapDays` aus den erweiterten Einstellungen wird über `startSolverJob` und `GenerateScheduleRequest.block_gap_days` an `SchedulerConfig(block_gap_days=...)` im Vorprüfungs- und Solver-Lauf übergeben.
- **Feiertags-Blockabstand für mehrtägige Nachtdienstblöcke (`app/scheduler/solver_cpsat.py`, `app/scheduler/validator.py`):**
  - `_add_3week_block_constraints` in `solver_cpsat.py` und `find_cross_quarter_block_gap_exceptions` in `validator.py` prüfen nun über die gesamte Blocklänge (`d + offset`), ob ein Dienstblock einen vorbelegten Feiertagsdienst enthält, und wenden die 7-Tage-Relaxation (`HOLIDAY_GAP`) konsistent zu `validate_schedule` an (behebt Review-Finding `B8`).
- **Tests (`tests/test_api_v1.py`, `tests/test_release_info.py`):**
  - Neue Tests `test_b7_generate_request_accepts_block_gap_days` und `test_b8_cross_quarter_block_gap_holiday_on_second_day_of_block`.

## [2.0.1] - 2026-11-08

### Fixed: Authenticated Excel Export, Mock Data Removal, Umlaut Entity IDs & Active-Staff Fairness

- **Authentifizierter Excel-Export (`frontend/src/lib/api.ts`, `frontend/src/views/MatrixView.tsx`):**
  - Neuer `exportQuarterSchedule()`-Client nutzt `authFetch` mit `Authorization: Bearer`-Token, lädt den Response-Stream als `Blob` und stößt den Datei-Download über eine temporäre Object-URL an (behebt Review-Finding `B1`).
- **Entfernung stiller Mock-Daten-Fallbacks (`frontend/src/lib/api.ts`):**
  - `MOCK_STAFF`, `MOCK_ABSENCES`, `MOCK_PREASSIGNED` und `getMockSchedule` entfernt; `fetchStaff()`, `fetchAbsences()` und `fetchPreAssigned()` liefern bei leeren Sammlungen ein echtes `[]` zurück statt synthetische 2026-Testdaten einzublenden (behebt Review-Finding `B2`).
- **Einheitliche Umlaut-Validierung in Pfaden und Dateispeicher (`app/persistence/models.py`, `app/persistence/repository.py`, `app/api/v1/staff.py`, `app/api/v1/absences.py`, `app/api/v1/preassigned.py`):**
  - Zentrales `ENTITY_ID_PATTERN = r"^[A-Za-z0-9_äöüÄÖÜß-]{1,64}$"` für Pydantic-Modelle, `FileJsonRepository.ID_PATTERN` sowie FastAPI-Pfadparameter (`StaffIdPath`, `AbsenceIdPath`, `PreassignedIdPath`) vereinheitlicht (behebt Review-Finding `B5`).
- **Fairness-Gruppenmittelwert ohne deaktivierte Mitarbeitende (`app/api/v1/quarters.py`):**
  - `get_quarter_fairness_overview` berücksichtigt nur noch aktive Mitarbeitende (`m.is_active`) oder Personen mit tatsächlichen Schichtzuweisungen im betrachteten Quartal (`m.identifier in assigned_idents`), sodass ausgeschiedene Mitarbeitende mit 0 Diensten den Gruppenschnitt nicht verzerren (behebt Review-Finding `B6`).
- **Tests (`tests/test_api_v1.py`, `tests/test_release_info.py`):**
  - Neue Integrationstests `test_umlaut_entity_ids_crud` und `test_fairness_overview_excludes_deactivated_staff_without_shifts`.

## [2.0.0] - 2026-11-08

### Full Architecture Modernization: React SPA, GCP Cloud Run & Streamlit Retirement

- **Ablösung des Streamlit-Frontends & Bereinigung von Abhängigkeiten (`app/streamlit_app.py`, `pyproject.toml`, `uv.lock`):**
  - Vollständiges Decommissioning des monolithischen Legacy-Frontends (`app/streamlit_app.py`, ~2.000 Zeilen).
  - Bereinigung der Runtime-Dependencies um `streamlit` und `matplotlib` (Entfernung von über 30 transitiven Paketen).
  - Umstellung des Container-Entrypoints (`scripts/entrypoint.sh`) auf direkten Uvicorn-Start als PID 1 mit nativer Signal-Weiterleitung.
- **Moderne Single-Page-Application (SPA) (`frontend/`):**
  - Produktionsreife React 19 + TypeScript + Vite + Tailwind CSS Anwendung im Tierklinik Dr. Trillig Branding.
  - 5 fokussierte Ansichten: Mitarbeiter-Verwaltung (`StaffHubView`), Abwesenheiten (`AbsencesView`), Vorbelegungen (`PreAssignedView`), interaktiver Dienstplan (`MatrixView`) und Fairness-Vektoren (`FairnessView`).
  - Neue UI-Ergonomie: Sofortsuche via `SearchableSelect`, klickbare Schichtkacheln, angepinnte Legende mit kompakter Wochenendschicht-Nummerierung `(1)`–`(4)` und Inline-Bearbeitung mit PUT-Endpunkten.
- **Headless FastAPI REST-Backend & Serverless Cloud Run Hosting (`app/api/`, `Dockerfile`, `scripts/`):**
  - Modulare REST-API unter `/api/v1` für Stammdaten, Abwesenheiten, Vorbelegungen, Dienstpläne und Exporte.
  - Asynchroner CP-SAT-Hintergrund-Solver (`POST /api/v1/quarters/{key}/solve`) mit Live-Polling und sauberem Abbruch (`POST /cancel`).
  - Pre-Flight-Diagnose-Engine zur Vorab-Erkennung und verständlichen Erklärung von Konflikten bei Vorbelegungen.
  - Dual-Driver Persistenzschicht (`app/persistence/`): Unterstützung für Google Cloud Firestore (SSOT) und lokale JSON-Dateien.
  - Rollenbasierte Authentifizierung (`require_planner`) und gehärtete Sicherheitskonfiguration.
- **PRD-Abschluss (`documentation/PRDs/implemented/`):**
  - Vollständige Umsetzung aller Meilensteine (Phase 1, 2, 3A, 3B, 3C) des Architektur-Roadmaps `PRD_gcp_cloud_run_migration_and_modernization.md`.

## [1.13.3] - 2026-11-08

### UI & API: Bearbeitungsfunktion für Abwesenheiten und Vorbelegungen

- **Bearbeiten-Schaltfläche in Abwesenheiten (`frontend/src/views/AbsencesView.tsx`, `frontend/src/lib/api.ts`):**
  - Neuer `Pencil`-Aktionsbutton neben dem Lösch-Icon für jeden Abwesenheitseintrag.
  - Öffnet den Modal-Dialog vorausgefüllt mit Mitarbeiter und Datumsintervall (`handleOpenEditModal`).
  - Reaktive Aktualisierung des lokalen Komponenten-Zustands und Persistenz via `updateAbsence`.
- **Bearbeiten-Schaltfläche in Vorbelegungen (`frontend/src/views/PreAssignedView.tsx`, `frontend/src/lib/api.ts`):**
  - Neuer `Pencil`-Aktionsbutton in der Tabelle der Vorbelegungen (`handleOpenEditModal`).
  - Vorbelegung mit Mitarbeiter, Datum, Schichtkachel, Feiertags-Status und Notiz wird im Dialog editierbar gemacht.
  - Lokale Zustandsaktualisierung und synchrone Persistenz via `updatePreAssigned`.
- **REST-API Erweiterungen (`app/api/v1/absences.py`, `app/api/v1/preassigned.py`):**
  - Neuer Endpunkt `PUT /api/v1/absences/{absence_id}` zur Aktualisierung bestehender Abwesenheiten.
  - Neuer Endpunkt `PUT /api/v1/preassigned/{preassigned_id}` zur Aktualisierung bestehender Vorbelegungen.
  - Vollständige Validierung von Pfad- und Payload-IDs, Existenzprüfungen sowie Absicherung durch `require_planner`.
  - Erweiterung der API-Integrationstests in `tests/test_api_v1.py`.

## [1.13.2] - 2026-11-08

### UI: Kompakte Schichtnummerierung, angepinnte Legende & Intern-Bereinigung im Dienstplan

- **Kompakte Wochenendschicht-Nummerierung (`frontend/src/views/MatrixView.tsx`):**
  - Mitarbeiternamen und -kürzel stehen in Spalte 2 an erster Stelle und im klaren visuellen Fokus.
  - Ersatz der breiten Schichttext-Badges durch kompakte, farblich abgestimmte Ziffern-Tags `(1)` bis `(4)`:
    - `(1)`: Frühdienst (`Sa 10–21`, `So/FT 8–20`)
    - `(2)`: Spätdienst Azubi (`Sa 10–19`)
    - `(3)`: Rufbereitschaft (`Sa/So 10–22`)
    - `(4)`: Azubi Rufbereitschaft (`So 8–20:30`)
  - Tooltips auf den Ziffern-Tags zeigen bei Mouseover die vollständige Schichtbezeichnung und Arbeitszeiten.
- **Angepinnte Schicht-Legende (`frontend/src/views/MatrixView.tsx`):**
  - Neue sticky Legende (`sticky top-14 z-30`) über der Dienstplantabelle bleibt beim vertikalen Scrollen dauerhaft unterhalb der Navigationsleiste verankert.
  - Bietet direkte Übersicht über alle Wochenendschichten, Nachtdienste, Interns sowie Vorbelegungs-Markierungen.
- **Intern-Tagdienst Spaltenbereinigung (`frontend/src/views/MatrixView.tsx`):**
  - Entfernung redundanter `08:30–20:30`- und `[Intern]`-Badges aus den einzelnen Tabellenzeilen der Spalte 3.
  - Der Tabellenkopf `🎓 Intern Tagdienst` weist die einheitliche Schichtzeit (`08:30–20:30`) zentral aus; Zeileneinträge konzentrieren sich rein auf die eingeteilte Person.

## [1.13.1] - 2026-11-08

### UI & Workflow: Klickbare Schicht-Kacheln & Wochentagsanzeige in Vorbelegungen

- **Klickbare Schicht-Kacheln (`frontend/src/views/PreAssignedView.tsx`, `frontend/src/types/api.ts`):**
  - Dropdown im Dialog „Dienst vorab zuweisen“ durch dynamische, interaktive Kacheln mit Piktogrammen, Schichtzeiten und Tooltips ersetzt.
  - Tagesabhängige Schichtfilterung (`getShiftOptionsForDate`): Zeigt für Samstage, Sonntage oder Feiertage/Werktage nur die jeweils an diesem Tag relevanten Schichten an (z. B. `Sa_10-21`, `So_8-20`, `So_10-22`, `So_8-20:30`, `Sa_Intern`, `So_Intern`, `N_*`).
  - Strikte Übergabe der tatsächlichen CP-SAT-Schicht-Identifier anstelle ungenauer Sammelbegriffe.
- **Wochentagsanzeige in Vorbelegungen (`frontend/src/views/PreAssignedView.tsx`):**
  - Neue Tabellenspalte „Wochentag“ mit farbcodierten Wochentags-Badges (Amber für Sa/So, Purple für Fr, Stone für Mo–Do) zur schnellen Nachvollziehbarkeit.
- **Datumsfeld-Initialisierung & Fokus (`frontend/src/views/PreAssignedView.tsx`, `frontend/src/views/AbsencesView.tsx`):**
  - Formulare starten mit unbefülltem Datumsfeld; beim Anklicken des Kalenders öffnet sich der Datepicker direkt zum Start des Planungsjahres (01.01.2027) via `min="2027-01-01"` und automatischem Fokus/`.showPicker()`.

## [1.13.0] - 2026-11-08

### UI & Workflow: Fokussierte Ansichten, Sofortsuche & Dienstplan-Neugestaltung

- **Dienstplan-Spaltenneugestaltung (`frontend/src/views/MatrixView.tsx`):**
  - **Spalte 1 (`🌙 Nacht`)**: Bündelt alle Nachtschichten für Tierärzte, TFAs und Nacht-Interns.
  - **Spalte 2 (`☀️ Sa/So Dienst & Rufbereitschaft`)**: Vereint Wochenend-Tagdienste und Rufbereitschaften sortiert nach Schichtabfolge (Früh -> Spät -> Ruf) mit farbcodierten Badges und exakten Arbeitszeiten (`Früh 10–21`, `Spät 10–19`, `Ruf 10–22`, `Früh 8–20`, `Ruf 8–20:30`).
  - **Spalte 3 (`🎓 Intern Tagdienst`)**: Dedizierte Spalte für Wochenend-Tagdienste der Interns (`08:30–20:30`).
- **Header-Bereinigung (`frontend/src/components/Navbar.tsx`):**
  - Redundanten Geburtstags-Hinweis aus der oberen Navigations-/Reiterleiste entfernt zur Fokussierung auf Planungsquartal und Kernnavigation.
- **Mitarbeiter-Sofortsuche & Autocomplete (`frontend/src/components/ui/SearchableSelect.tsx`):**
  - Neue barrierefreie `SearchableSelect`-Komponente mit Tastaturnavigation (`ArrowUp`/`ArrowDown`/`Enter`/`Escape`), Rollen-Badges und Sofortfilterung nach Name oder Kürzel.
  - Ersetzt unübersichtliche 40-Personen-Dropdowns in den Eingabedialogen für Abwesenheiten (`AbsencesView.tsx`) und Vorbelegungen (`PreAssignedView.tsx`).
- **Fokussierte Abwesenheiten-Ansicht & Filterung (`frontend/src/views/AbsencesView.tsx`):**
  - Verschlankung auf die reine, übersichtliche Ansicht nach Person (Entfernung redundanter Kalender- und Tabellenmodi).
  - Neues Live-Filterfeld im Kopfbereich zur sofortigen Suche nach Namen und Kürzeln mit reaktiver Aktualisierung der Personenkarten und KPI-Kennzahlen.
- **Listenfokussierung & Nachtdienst-Korrektur in Vorbelegungen (`frontend/src/views/PreAssignedView.tsx`, `frontend/src/lib/utils.ts`):**
  - Reduktion auf die tabellarische Listenansicht für maximale Übersichtlichkeit.
  - Zentrale Hilfsfunktion `isNightShift` in `lib/utils.ts` erkennt CP-SAT-Schichten (`N_*`) sowie Bezeichnungen wie `"Nachtdienst"` zuverlässig.
  - Korrektur der KPI-Zählung und Darstellung aller Nachtdienste mit Indigo-Mond-Badge statt fälschlichem "Wochenende Tag".
- **Dienstplan-Korrekturen & visuelle Aufwertung (`frontend/src/views/MatrixView.tsx`):**
  - **Namensanzeige**: `getStaff()` um case-insensitives Matching für IDs und Kürzel erweitert. Behebt den Bug, dass "Volle Namen anzeigen" für Mitarbeiter nicht griff.
  - **Dynamische Rollen-Zuordnung**: Rollen-Badges werden strikt aus `stf.beruf` abgeleitet. Behebt falsche Bezeichnungen (z.B. LiM als TFA statt Azubi bei Paaren).
  - **Grüne Vorbelegungs-Hervorhebung**: Alle fest vorgegebenen Dienste (Ärzte, TFAs, Azubis und Interns) werden durchgehend smaragdgrün hinterlegt (`bg-emerald-100/90 text-emerald-950 border-emerald-300`) mit Stecknadel-Icon. Wochentags-Feiertage mit Tagdiensten werden nicht mehr fälschlich ausgegraut.
  - **Prominenter Planungs-Button**: Umbenennung von "Neu berechnen" zu "Neues Quartal planen" mit primärem Farb-Highlight (`bg-[#324b9b]`) und Sparkles-Icon zur klaren Abgrenzung.

## [1.12.5] - 2026-11-08

### Serving Architecture, Concurrency & Solver Transparency (Findings C1, C2, C3)

- **Single-Worker Cloud Run Deployment (`scripts/deploy_cloud_run.sh`, `scripts/deploy_cloud_run.ps1`) (Finding C1):**
  - Cloud Run Dienstbereitstellung auf `--min-instances=1 --max-instances=1` fixiert. Dies verhindert den Verlust aktiver Hintergrund-Solver-Threads (`_active_jobs`), Fehler durch fehlende Session-Affinity bei Polling-Anfragen und unzeitiges Scale-to-Zero während mehrminütiger Berechnungen.
  - Das robuste Multi-Worker-Zielmodell mit Cloud Tasks / Cloud Run Jobs, Heartbeats und Firestore-Transaktions-Locks wurde als Verbesserungsvorschlag im Backlog (`issues.md`) hinterlegt.
- **Globale Nebenläufigkeitsbegrenzung & CPU-Ressourcenschutz (`app/api/v1/quarters.py`, `app/scheduler/solver_cpsat.py`, `app/scheduler/solver.py`) (Finding C2):**
  - Globaler Concurrency-Guard in `generate_quarter_schedule`: Läuft bereits eine Hintergrund-Berechnung für ein Quartal, wird bei weiteren Aufrufen für andere Quartale sofort HTTP 429 (Too Many Requests) gemeldet.
  - Bereinigung terminierter Threads aus dem In-Memory-Tracking `_active_jobs` vor jeder Prüfung.
  - OR-Tools Worker-Allokation: `num_workers` kann konfiguriert werden und wird standardmäßig im API-Layer auf 2 Threads begrenzt, um CPU-Drosselung und OOM auf 2-vCPU Cloud Run Instanzen zu verhindern.
  - Synchroner Timeout-Schutz: Bei `sync=true` wird `max_solve_time_seconds > 850s` mit HTTP 400 abgewiesen, um Cloud Run HTTP-Request-Timeouts (900s) abzufangen. Thread-Join-Timeout auf maximal 880s gekappt.
  - Validierung des Quartalsjahres in `_parse_quarter_key`: Gültigkeitsbereich 2020–2100 strikt validiert (HTTP 400 bei unzulässigen Jahreszahlen).
- **Transparenz für Solver-Status, Best-Bound & Optimalitätslücke (`app/scheduler/solver_cpsat.py`, `app/persistence/models.py`, `app/api/v1/quarters.py`, `frontend/src/types/api.ts`) (Finding C3):**
  - `SolverResult` erfasst den exakten CP-SAT-Lösungsstatus (`status_name`, z.B. `OPTIMAL` oder `FEASIBLE`), `objective_value`, `best_objective_bound`, `num_workers` sowie das Stagnations-Abbruchflag `stopped_due_to_stagnation`.
  - `SolverJobRecord` und `QuarterScheduleDocument.solver_metrics` speichern `status_name`, `is_optimal`, `best_objective_bound`, `objective_value`, `optimality_gap` (Differenz zwischen Zielwert und Schranke) und `stopped_due_to_stagnation`.
  - Anpassung der Dokumentation (`PROBLEM_DESCRIPTION.md`, `ARCHITECTURE.md`): Klarstellung, dass der Solver mathematisch optimierte Dienstpläne (bewiesen optimal oder bestmögliche gefundene Lösung innerhalb der Zeit-/Stagnationsgrenze) generiert.

## [1.12.4] - 2026-11-08

### Constraints & Data Integrity: Mitarbeiter-Validierung & Abteilungs-Grenzschutz (Findings B8, B9)

- **Stammdaten-Validierung & Identifikator-Schutz (`app/persistence/models.py`, `app/api/v1/staff.py`, `app/scheduler/models.py`) (Finding B8):**
  - Pydantic-Feldgrenzen für `StaffMember`: `hours` (0–168), `nd_min_consecutive` (1–7), `nd_max_consecutive` (1–7), und Geburtstags-Muster `MM-DD`.
  - Modellvalidierung erzwingt `hours > 0` für Nicht-Tierärzte (`Beruf != Beruf.VET`), `nd_min_consecutive <= nd_max_consecutive` sowie Wochentags-Werte `1 <= d <= 7` für `nd_exceptions`.
  - Direkte Vorab-Prüfung bei der Datenerfassung gegen das Scheduler-Domänenmodell `to_scheduler_staff()`, wodurch ungültige Stammdaten den Solver-Thread nicht mehr nachträglich zum Absturz bringen können.
  - Zentrale Eindeutigkeitsprüfung `check_identifier_unique` verhindert Namenskürzel-Kollisionen bei `POST /api/v1/staff`, `PUT /api/v1/staff/{id}` und `POST /api/v1/staff/bulk-import` (HTTP 409 Conflict).
- **Abteilungs-Trennung über Quartalsgrenzen (`app/scheduler/solver_cpsat.py`, `app/scheduler/validator.py`) (Finding B9):**
  - Berücksichtigung des Vorquartalskontexts (`previous_context.trailing_assignments`): Wenn ein Mitarbeiter aus OP oder Station die letzte Nacht des Vorquartals gearbeitet hat, darf am ersten Tag des neuen Quartals kein anderer Mitarbeiter derselben Abteilung eingeteilt werden (H17/H18).
  - Der CP-SAT-Solver fixiert die Entscheidungsvariablen anderer Abteilungsmitglieder in Nacht 1 auf `0`.
  - Der Validator prüft die Quartalsgrenze und meldet `Abteilung Consecutive Days`-Verletzungen bei Abteilungs-Konflikten zwischen Vorquartal und neuem Plan.

## [1.12.3] - 2026-11-08

### Constraints & Scheduling: Dienstplan-Horizont, Schichtabdeckung & Feiertags-Validierung (Findings B1, B3, B5, B7)

- **Exakter Kalenderquartal-Horizont (`app/scheduler/models.py`, `app/api/v1/quarters.py`) (Finding B1):**
  - `generate_quarter_shifts` akzeptiert optionales `quarter_end` und leitet bei `None` das echte kalendarische Quartalsende ab (31. März, 30. Juni, 30. September, 31. Dezember).
  - Feste 91-Tage-Schleife durch inklusiven Datumsvergleich (`current_date <= quarter_end`) ersetzt, wodurch der 30. September und 31. Dezember vollständig geplant und Doppelplanungen zum 1. April vermieden werden.
  - Randabsicherung bei gekoppelten Intern-Wochenenden am Quartalsende gegen Indexüberschreitung.
- **Erzwungene Schichtabdeckung in Solver und Validator (`app/scheduler/solver_cpsat.py`, `app/scheduler/validator.py`) (Finding B3):**
  - Keine stillschweigende Nicht-Erstellung von Schicht-Constraints im CP-SAT-Solver bei fehlendem Personal; stattdessen explizite Unlösbarkeits-Constraints (`model.Add(0 == target)`), die Lücken sofort aufdecken.
  - Geschlossene Nächte ohne wählbare Nicht-Azubis werden im Solver als unlösbar markiert, und Azubi-Zuweisungen werden auf `0` fixiert, falls keine Begleitperson existiert.
  - `_check_shift_coverage` im Validator prüft alle Soll-Schichten aus `generate_quarter_shifts` gegen die tatsächlichen Belegungen und moniert unbesetzte Wochenendschichten, unbesetzte Nächte sowie Nächte ohne Fachpersonal (H12).
- **Strikte Bindung des Solver-Erfolgs an die Validierung (`app/scheduler/solver_cpsat.py`, `app/api/v1/quarters.py`) (Finding B5):**
  - `SolverResult` transportiert `hard_violations` aus der Post-Solve-Validierung. Bei harten Regelverletzungen wird `success=False` gesetzt.
  - Im Hintergrund-Worker `_execute_solver_worker` führt jede harte Validierungsverletzung zum Status `FAILED` des Solver-Jobs und verhindert das Speichern inkonsistenter Dienstpläne.
- **Vorab zugewiesene Schichten & Feiertags-Lockerung (`app/persistence/models.py`, `app/api/v1/preassigned.py`, `app/api/v1/quarters.py`, `app/scheduler/validator.py`) (Finding B7):**
  - Validierung von `PreAssignedShiftRecord.shift_type` via Pydantic-Validator gegen `ShiftType`-Enums und `"nacht"`.
  - Vorab-Prüfung bei der Anlage von Schichten (`POST /api/v1/preassigned`) auf Existenz des Mitarbeiters (`422 Unprocessable Entity`).
  - Erweiterung von `ShiftAssignmentRecord` um `is_pre_assigned: bool`, sodass der Status bei Persistierung und Rekonstruktion erhalten bleibt.
  - Implementierung der 7-Tage-Lockerung (`holiday_gap_days`) in der 3-Wochen-Block-Validierung (`_check_three_week_block_constraint`), wenn vorab zugewiesene Feiertagsdienste involviert sind.

## [1.12.2] - 2026-11-08

### Security: Session-Härtung, Pfad-Validierung & Container-Bereinigung (Findings A3, A4, A5, A7)

- **Auth Fail-Closed & Firestore-Umgebungs-Isolierung (Finding A3):**
  - `is_auth_required()` schützt die API standardmäßig (`True`), Bypass via `ALLOW_INSECURE_DEV=1` wird in Cloud Run (`K_SERVICE` gesetzt) strikt ignoriert.
  - `FirestoreRepository` unterstützt isolierte `collection_prefix`-Namespaces (z.B. `dev_`) und alternative Datenbanken via `FIRESTORE_DATABASE`, womit Entwickler-Deployments Produktionsdaten nicht überschreiben können.
  - `deploy_cloud_run.sh --dev` deployt standardmäßig mit `STORAGE_BACKEND=file`.
- **Zeitlich begrenzte Tokens, Kennwort-Hashing & Brute-Force-Schutz (Finding A4):**
  - Signierte, zeitlich limitierte Tokens via `itsdangerous.URLSafeTimedSerializer` mit 12 Stunden maximaler Gültigkeit (`TOKEN_MAX_AGE_SECONDS`).
  - Automatische Ungültigmachung aktiver Sitzungstokens bei Kennwort-Änderung über Kennwort-Prägungsstempel (`stamp`).
  - Sichere Kennwort-Ableitung mit `hashlib.scrypt` (N=16384, r=8, p=1) inklusive Abwärtskompatibilität für bestehende SHA-256 Hashes.
  - Fehlgeschlagene Login-Versuche werden verzögert (`_throttle_failed_login`), um Brute-Force-Angriffe einzudämmen.
  - Automatisierte Bereitstellung und Injektion eines persistenten `SESSION_SECRET` in den Cloud Run Deploy-Skripten.
- **Pfad-Validierung & Schutz vor Directory Traversal (Finding A5):**
  - Pydantic-Validierung aller Datastore-IDs (`StaffMember`, `AbsenceRecord`, `PreAssignedShiftRecord`, `SolverJobRecord`, `QuarterScheduleDocument`) via Regex `^[A-Za-z0-9_-]{1,64}$`.
  - Path-Parameter-Validierung auf API-Routenebene (`Path(pattern=...)`) in `staff.py`, `absences.py`, `preassigned.py`.
  - Zentraler `_safe_path()`-Sicherheitscheck in `FileJsonRepository`, der Traversierungsversuche (`../`) mit `ValueError` abwehrt.
- **Ausschluss sensibler Klinikdaten aus Container-Builds (Finding A7):**
  - `.dockerignore` und `.gcloudignore` schließen `data/` vollständig aus (unter Ausnahme der synthetischen `data/staff_sample.csv`).
  - `Dockerfile` kopiert nur noch `data/staff_sample.csv`, wodurch reale Mitarbeiter- und Dienstplandaten nicht mehr in Container-Images oder Cloud Build Buckets gelangen.

## [1.12.1] - 2026-11-08

### Security: API-Zugriffskontrolle & Fail-Closed Deployment-Härtung (Findings A1, A2)

- **Router-Level Authentifizierungsschutz (`app/api/v1/router.py`, `staff.py`, `absences.py`, `preassigned.py`, `quarters.py`):**
  - Alle Lese- und Berechnungs-Endpunkte (`GET /api/v1/staff`, `GET /api/v1/absences`, `GET /api/v1/preassigned`, `GET /api/v1/quarters/*`, `POST /validate`, `POST /validate-feasibility`, `GET /export`) erfordern nun eine autorisierte Planer-Sitzung via `require_planner`.
  - Redundante Parameter `_planner: PlannerDep` in den Route-Handlern entfernt; Authentifizierung wird zentral auf Router-Ebene deklariert.
  - Automatisierte Coverage-Testsuite (`tests/test_api_auth_coverage.py`), die dynamisch alle 32 API-Routen prüft und bei unauthentifiziertem Zugriff einen 401 garantiert.
- **Entfernung hartkodierter Standard-Passwörter & Fail-Closed Schutz (`app/api/v1/auth.py`, `app/api/main.py`):**
  - Standard-Passwort-Hash `_DEFAULT_PASSWORD_HASH` ("Trillig2026!") vollständig aus dem Quellcode entfernt.
  - Startup-Validierung (`validate_auth_config`): Startet die Anwendung mit `AUTH_REQUIRED=true` ohne konfiguriertes `PASSWORD_HASH` oder `APP_PASSWORD`, wird der Start sofort verweigert (Fail-Closed).
  - Anmeldeversuche ohne hinterlegtes Secret scheitern deterministisch mit 401.
  - Frontend-Komponente `LoginGate.tsx` von fest verdrahteten Standard-Passwörtern bereinigt.
- **Cloud Run Deployment-Skripte (`scripts/deploy_cloud_run.sh`, `scripts/deploy_cloud_run.ps1`):**
  - Abbruch mit klarer Fehlermeldung, falls ein Produktions-Deploy (`AUTH_REQUIRED=true`) ohne gesetztes `APP_PASSWORD` oder `PASSWORD_HASH` angestoßen wird.

## [1.12.0] - 2026-11-07

### Added: Produktions-Cutover & Firebase Hosting Pipeline (Phase 3C)

- **Cloud Run Deployment Cutover (`scripts/deploy_cloud_run.sh`, `scripts/deploy_cloud_run.ps1`):**
  - Standard-Target für `dienstplan-app` (Produktion) auf `fastapi` umgestellt, womit der FastAPI-Server sowohl die API-Endpunkte unter `/api/v1` als auch die kompilierte React-SPA unter `/` ausliefert.
  - Automatische Übermittlung von `AUTH_REQUIRED=true` im Produktionsbetrieb und `AUTH_REQUIRED=false` für `dienstplan-dev`.
- **Firebase Hosting CDN Routing (`firebase.json`):**
  - Konfiguration von `public: frontend/dist` mit globalem CDN Edge-Caching für statische Assets.
  - API-Proxy-Rewrites für `/api/**` an den Cloud Run Service `dienstplan-app` in `europe-west3` (Frankfurt) mit gesetzlichen DSGVO-Garantien.
  - Client-Side SPA Fallback-Routing (`**` -> `/index.html`).
- **Container Hardening (`Dockerfile`, `entrypoint.sh`):**
  - Vollständige Verzeichnis-Initialisierung für alle Datastore-Entitäten (`staff`, `absences`, `schedules`, `jobs`, `preassigned`) für den Non-Root-Container-User `appuser` (UID 10001).
- **Automatisierte Frontend-Deploy-Pipeline (`scripts/deploy_firebase.sh`):**
  - Neues Skript zur 1-Klick-Erstellung des optimierten Vite-Produktionsbundles und Bereitstellung auf Firebase Hosting (`dienstplan-tierklinik-trillig`).

### Removed: Legacy Streamlit Decommissioning

- **Streamlit Codebase Removal (`app/streamlit_app.py`):**
  - Vollständige Löschung des veralteten Streamlit-Frontends (`app/streamlit_app.py`) nach erfolgreichem Cutover auf die FastAPI- und React-Architektur.
- **Dependency & Lockfile Pruning (`pyproject.toml`, `uv.lock`):**
  - Entfernung von `streamlit>=1.57.0` und `matplotlib>=3.8.0` sowie 28 transitiven Paketen (Tornado, Altair, pydeck, blinker, kiwisolver, pillow etc.), wodurch das Docker-Image und die Installationszeiten signifikant verkleinert werden.
- **Container & Deployment Simplification (`Dockerfile`, `entrypoint.sh`, `deploy_cloud_run.sh`, `deploy_cloud_run.ps1`, `run.bat`):**
  - Bereinigung des Container-Healthchecks auf direkten Probe von `/api/v1/health` (Entfernung des Streamlit-Fallbacks).
  - Entfernung der `--legacy-streamlit` und `-LegacyStreamlit` CLI-Schalter in den Deployment-Skripten.
  - Umstellung des lokalen Windows-Launchers (`run.bat`) auf Uvicorn (`app.api.main:app`).

## [1.11.0] - 2026-11-07

### Added: Planer-Authentifizierung & Schneller Entwickler-Modus (Phase 3B)

- **Backend Authentifizierungs- & Autorisierungs-Dependency (`app/api/v1/auth.py`):**
  - `require_planner` (`require_auth`): Schützt alle schreibenden Operationen (`staff.py`, `absences.py`, `preassigned.py`, `quarters.py`) vor unbefugtem Zugriff via HMAC-SHA256 Bearer Token.
  - Reibungsloser Entwicklermodus: Wenn `AUTH_REQUIRED=false` (Standard für lokales Testen und Pytest), werden Anfragen ohne Token direkt autorisiert, wodurch 100% der bestehenden Tests ohne Header-Aufwand grün bleiben.
  - Endpoints `POST /api/v1/auth/login`, `GET /api/v1/auth/status` und `GET /api/v1/auth/verify`.
  - Auflösung eines zirkulären Imports zwischen `app.persistence.models` und `app.scheduler.feasibility`.
- **Frontend Authentifizierungs-Gate & Token-Injection (`LoginGate.tsx`, `api.ts`, `Navbar.tsx`):**
  - Zentraler `authFetch`-Wrapper in `frontend/src/lib/api.ts` injiziert automatisch den Bearer-Token in alle API-Aufrufe und fängt `401 Unauthorized` ab.
  - Intelligentes `LoginGate`: Prüft beim Laden automatisch den Serverstatus (`/auth/status`). Bei deaktivierter Authentifizierung entfällt der Login-Schritt komplett.
  - **1-Klick-Entwickler-Login**: Bietet bei aktiver Authentifizierung einen Schnellzugriffs-Button für lokale Tests ohne manuelles Passwort-Eintippen.
  - Header-Integration: Abmelde-Aktion im `Navbar`-Menüband integriert.

## [1.10.0] - 2026-11-07

### Added: Pre-Flight Machbarkeitsprüfung & Infeasibility Explainability (`feasibility.py`, `quarters.py`, `MatrixView.tsx`)

- **Deterministische Vorprüfungs- & Diagnose-Engine (`app/scheduler/feasibility.py`):**
  - `validate_pre_assigned_consistency`: Prüft vor dem Solverlauf deterministisch alle mathematisch unlösbaren Vorbelegungs-Konflikte:
    - Doppelbelegungen am selben Kalendertag (`PREASSIGNED_SAME_DAY`).
    - Überschreitung der konfigurierten Höchstgrenze aufeinanderfolgender Nächte `nd_max_consecutive` (`PREASSIGNED_CONSECUTIVE_CAP`).
    - Verletzung der 11h-Ruhezeit bei Wochenenddiensten (`PREASSIGNED_WEEKEND_ISOLATION`).
    - Kollisionen mit gesperrten Wochentagen `nd_exceptions` (`PREASSIGNED_BLOCKED_WEEKDAY`).
    - Kollisionen mit genehmigtem Urlaub bzw. Abwesenheiten (`PREASSIGNED_VACATION_COLLISION`).
    - Nachtdienst-Qualifikationen: Ungedeckte Schließnächte bei `nd_alone=False` (`NIGHT_SOLO_INCAPABLE`) und unzulässige Nachtpaarungen (`NIGHT_PAIRING_UNQUALIFIED`, z. B. zwei Azubis oder fehlende TFA).
  - `diagnose_structured_infeasibility`: Erzeugt strukturierte Fehlerkarten mit konkreten Handlungsempfehlungen (`remediation_hint`) und betroffenen Mitarbeitern (`affected_staff_ids`), falls der CP-SAT Solver auf Grund komplexer Konstellationen infeasible meldet.
  - Makro-Kapazitätsprüfungen (`validate_capacity_and_coverage`) als nicht-blockierende Warnungen klassifiziert.
- **Backend API-Integration (`app/api/v1/quarters.py`, `app/persistence/models.py`):**
  - Neuer Endpoint `POST /api/v1/quarters/{quarter_key}/validate-feasibility` liefert den vollständigen `FeasibilityReportRecord` in sub-5ms ohne Solver-Belastung.
  - Fast-Fail-Schutz im Solver-Dispatch: Bei harten Vorbelegungs-Konflikten schlägt der Solver-Job sofort mit Status `FAILED` fehl und hängt die Diagnose-Karten direkt an den `SolverJobRecord` an.
- **Frontend MatrixView Integration (`MatrixView.tsx`, `api.ts`, `types/api.ts`):**
  - Neuer Button **"Machbarkeit prüfen"** in der Setup-Menüleiste mit modalem Diagnose-Report (`FeasibilityModal`).
  - Solver-Fortschritts-Modal rendert bei Fehlschlag sofort interaktive Warn- und Fehlerkarten mit Ursache, betroffenen Mitarbeitern und Lösungsvorschlag.
- **Vorbereitung Swap-Entkopplung (`MatrixView.tsx`):**
  - Entfernung der temporären Tausch-Aktionen aus der MatrixView-Tabelle; dedizierter Backend- und UI-Workflow auf Phase 4 vertagt.

## [1.9.0] - 2026-11-07

### Added: Vorher-Nachher Ausgleichs-Pfeile & Fairness-Vektoren (`FairnessView.tsx`)

- **Vorher-Nachher Vektor-Visualisierung (Ausgleichs-Pfeile):**
  - Neuer Visualisierungs-Modus `arrows` in `FairnessView.tsx`, der für jede Person den Ausgangszustand vor der Einteilung (Vorquartals-Saldo / Guthaben als ausgegrauter Punkt) und den neuen Netto-Saldo nach der Planung (farbiger Punkt) verbindet.
  - Dynamisch gefärbte SVG-Ausgleichsvektoren mit Pfeilspitzen (`#10b981` grün bei Annäherung an Null, `#f43f5e` rot bei Entfernung, gestrichelt bei Verharren).
  - Zielkorridor ($\pm 0.5$ Dienste auf 40h-Basis) mit weicher grüner Schattierung und neutraler Nullachse.
- **Erfolgs-KPIs & Richtungsanalyse:**
  - 3 zusammenfassende Metriken über dem Plot:
    1. **Korrektur-Erfolg**: Zeigt absolut und prozentual, wie viele Mitarbeitende sich der Nulllinie angenähert haben oder im Idealbereich geblieben sind.
    2. **Zielkorridor-Quote**: Anteil der Mitarbeitenden im Toleranzband $\pm 0.5$ inkl. Ausreißer-Counter ($> 1.0$).
    3. **Unwucht-Reduktion**: Mittlerer absoluter Abstand zur Nulllinie vor der Einteilung im direkten Vergleich zum Zustand nach der Einteilung (Prozentuale Reduktion).
- **Zwei komplementäre Darstellungsformen:**
  - **Einzel-Vektoren (Dumbbell-Plot)**: Jede Person in einer eigenen horizontalen Spur ohne Überlappungen; sortierbar nach größter Verbesserung, höchster Vorbelastung, Rest-Saldo oder Name; filterbar nach Vorbelasteten, Verbesserten oder Ausreißern.
  - **Konvergenz-Trichter (Parallel Coordinates)**: Zeigt auf zwei vertikalen Achsen (Vorher vs. Nachher) die globale Kompression des gesamten Teams in den schmalen grünen Zielkorridor.
- **Interaktiver Detail-Inspector:**
  - Nahtlose Verknüpfung mit Tooltips und dem bestehenden Mitarbeiter-Inspektor bei Klick oder Hover.

## [1.8.0] - 2026-11-07

### Added: Transparente Fairness-Übersicht & L1-Ausgleichsoptimierung im Solver

- **Transparente 3-Spalten-Fairness (`FairnessView.tsx`, `quarters.py`):**
  - Intuitive, kliniknahe Aufbereitung der Dienstverteilung nach der 3-Spalten-Formel:
    1. **Plan vs. Soll** (relative Abweichung bezogen auf den Berufsgruppen-Sollwert auf 40h-Vollzeit-Basis).
    2. **Vorquartals-Saldo** (Guthaben oder Schuld aus dem vorherigen Quartal).
    3. **Netto-Gesamtsaldo** (Summe beider Werte: zeigt sofort, ob das Saldo fair ausgeglichen wird).
  - Gruppenspezifische Tabs zur getrennten Betrachtung von `TFA`, `Azubi`, `Intern` und `Tierarzt (Vet)`.
  - Detail-Inspektor-Karte für einzelne Mitarbeitende mit Schichtaufschlüsselung, Teilzeitfaktor und Anwesenheitsquote.
- **Interaktive Visualisierungen (`FairnessView.tsx`):**
  - **Option 1: Balance-Balken (Diverging Bar Chart)**: Horizontal ausgerichteter Abweichungsbalken mit grünem $\pm 0.5$-Toleranzkorridor.
  - **Option 2: 2D-Ausgleichs-Scatterplot**: Visualisiert Plan-Abweichung vs. Vorquartals-Saldo mit mathematisch korrekter Ausgleichsdiagonale $y = -x$ von oben links nach unten rechts inkl. Quadranten-Beschriftungen.
  - **Option 3: Dichte-Streifen (Strip Plot)**: Zeigt die Streuung und Schwarmdichte des gesamten Teams auf einer kontinuierlichen Skala.
- **CP-SAT Solver: L1-Summenfairness & Gewichtungshierarchie (`solver_cpsat.py`):**
  - Implementierung von $L_1$-Summenfairness ($\sum_i |\Delta_i|$) über alle Mitarbeitenden ergänzend zum Chebyshev-Min-Max-Term. Dadurch erhält jeder einzelne Mitarbeiter einen aktiven Gradienten zur Kompensation seines Vorquartals (behebt das Bottleneck, bei dem nur die extremsten 2 Mitarbeiter optimiert wurden).
  - Neujustierung der Penalty-Gewichte: `RANGE_WEIGHT = 50`, `L1_WEIGHT = 10` (zuvor `1`), um dem Notdienst-Ausgleich im CP-SAT-Zielfunktions-Gefüge das notwendige Gewicht gegenüber reinen Schichtabstands-Boni zu verleihen.
  - Statistische Validierung: Korrelation $r(\text{Vorquartal}, \text{Plan})$ sinkt bei TFAs von $+0.13$ auf $-0.32$, bei Azubis von $-0.15$ auf $-0.63$ und bei Interns auf $-1.00$ (vollständiger Netto-Ausgleich).

## [1.7.0] - 2026-11-06

### Changed: UI-Verschlankung Dienstplan, Solver Smart-Stop (10 Min.), Personal-Flow & Schichtanzeige

- **Dienstplan-Lifecycle & Empty State (`MatrixView.tsx`, `frontend/src/lib/api.ts`):**
  - `fetchSchedule()` liefert bei nicht-existentem oder leerem Plan `null` statt eines synthetischen Dummy-Plans.
  - Wenn kein Plan vorliegt, öffnet `MatrixView` direkt in der schlanken Erstellungsansicht (`pageMode = 'setup'`) mit synchronisiertem Quartals-Selector aus der globalen Navigationsleiste.
- **Kliniknahe Fachbegriffe (`MatrixView.tsx`):**
  - Ersetzung technischer Bezeichnungen: "Plan-Matrix" wurde zu **"Dienstplan"**, "Vorplan-Übertrag" zu **"Vorquartal & Ausgleich"**.
  - Bereinigung interner Tabellenbegriffe: "Übertrag-Delta" zu "Ausgleichs-Saldo", "Grenz-Restriktion" zu "Gesetzliche Schutzregel".
- **CP-SAT Solver Smart-Stop & 10-Minuten Obergrenze (`solver_cpsat.py`, `solver.py`, `quarters.py`, `MatrixView.tsx`):**
  - Obergrenze auf standardmäßig 10 Minuten (600 Sek., konfigurierbar bis 20 Min.) erweitert, da Quartalsplanungen selten stattfinden und tiefere Suchläufe signifikante Fairnessgewinne erzielen.
  - Plateau- & Stagnationserkennung (30 Sek.) im Progress-Callback bricht automatisch ab, sobald keine weiteren Verbesserungen mehr erzielt werden.
  - Klappbare Einstellungen für Mindest-Blockabstand, Vorquartals-Einbeziehung und maximale Suchdauer.
- **Dienstplan-Tabelle & Schichtanzeige (`MatrixView.tsx`):**
  - Beseitigung der leeren Striche `—`: Dynamische Filterung nach Schichtpräfix (`N_`) und Wochenend-Schichttypen (`Sa_10-21`, `So_8-20` etc.).
  - Echte Rufbereitschaftsbesetzung: Ersetzung des statischen Dummy-Texts `"Ruf aktiv"` durch die real eingeteilten Tierärzte (`Sa_10-22`, `So_10-22`, `So_8-20:30`).
  - Unterstützung für geteilte Nachtdienste: Anzeige beider Diensthabenden mit TFA-Qualifikationsabzeichen.
- **Personalansicht & Neuanlage-Workflow (`StaffView.tsx`, `Badge.tsx`, `colors.ts`):**
  - 1-Klick 3-Stufen-Wahl für Nachtdienstfähigkeit: `Kein Nachtdienst`, `Zu zweit`, `Alleine` mit automatischem JArbSchG-Schutz für Minderjährige.
  - Reduktion des Abteilungsfelds auf constraint-relevante Stationen (`Station`, `OP` oder `—`) zur Vermeidung von visueller Unruhe.
  - 1-Klick Wochentagsmatrix zur intuitiven Auswahl verfügbarer Wochentage ohne verschachtelte Modi.
  - Eigene Tabellenspalten für Volljährig, Nachtdienst und Anmeldung.
- **Geburtstags-Hinweis (`Navbar.tsx`, `MatrixView.tsx`):**
  - Dezente Geburtstagskachel im Leerraum der Navigationsleiste sowie im Header des Dienstplans.
- **Bugfix Rollover Staff-ID Casing & Live-Berechnung (`rollover.py`, `models.py`):**
  - Case-insensitive Zuordnung von `actual_staff_id` auf `staff.identifier` verhindert Null-Salden bei gemischter Groß-/Kleinschreibung.
  - Vorquartals-Salden (z. B. AA: `+2.22`, Caroline B.: `+8.55`) und 21-Tage-Ruhezeiten greifen reproduzierbar im Produktivbetrieb.

## [1.6.0] - 2026-11-06

### Added: Web-Plattform (FastAPI + React), Firestore SSOT, 2027-Q1 Baseline & Feiertagsdienste

- **GCP Cloud Run & Firestore SSOT Architektur:**
  - Modernisierte Full-Stack-Architektur auf GCP Cloud Run mit FastAPI-Backend (`app/api/`) und React/TypeScript SPA (`frontend/`).
  - Single Source of Truth Persistenz (`app/persistence/`): Duale Repository-Implementierung mit Firestore (`FirestoreRepository`) für Cloud-Betrieb und dateibasiertem JSON-Fallback (`FileJsonRepository`) für lokale Entwicklung.
  - Multi-Stage Dockerfile mit distroless/unprivileged `appuser` (UID 10001), `uv sync --frozen` Dependency-Locking und integriertem Healthcheck.
- **2027-Q1 Baseline-Datenübernahme:**
  - Ingestion von 46 aktiven Mitarbeitenden aus `data/2027-Q1/MA_excel.xlsx` mit automatischer Deaktivierung ausgeschiedener Mitarbeitender (`AN`, `JH`, `NoK`).
  - Ingestion von 139 Abwesenheiten aus `data/2027-Q1/Urlaube_excel.xlsx`.
  - Ingestion von 201 realisierten Diensten aus `data/2027-Q1/Q4_Arbeitseinsätze1.xlsx` in den Vorquartalsplan `2026-Q4` (Status `CLOSED`), wodurch automatischer Carry-Forward-Fairnessausgleich und 21-Tage-Ruhezeitgrenzen für Q1 2027 nahtlos greifen.
- **Vorgegebene Feiertagsdienste & Konfliktvalidierung:**
  - Neue API-Routen unter `/api/v1/preassigned` und `PreAssignedShiftRecord` Modell zur Verwaltung vorgegebener Feiertagsdienste (Ostern 2027).
  - Erweiterung von `validate_pre_assigned()` zur automatischen Erkennung von Doppelbuchungen am selben Kalendertag sowie Überschreitungen der maximalen Nachtdienst-Folgetage (`nd_max_consecutive`).
- **Resilienter Excel-Streaming-Parser (`file_loader.py`):**
  - Migration von `pd.read_excel()` auf streaming-basiertes `openpyxl(read_only=True, data_only=True)` mit Schwellenwert-Abbruch für leere Folgezeilen; parst Excel-Dateien mit über 1 Mio. Leerzeilen in 28ms statt OOM/Hang.
  - Normalisierung von Schichtnamen-Aliassen (`Sa_8-20` -> `Sa_10-21`, `So_09:30-21:30` -> `So_8-20:30`) und Korrektur von Datums-Tippfehlern in Vorquartals-Nachtdiensten.

## [1.5.2] - 2026-11-02

### Fixed: Intern-Wochenendzählung und Fairness-Einheiten (Finding B4 & F1)

- **Gekoppelte Wochenend-Einheiten (`Schedule.count_weekends`, `count_intern_weekends`):**
  - Gekoppelte Intern-Wochenenden (`Sa_Intern` + `So_Intern`) werden nun konsistent als 1 vollständiger Wochenend-Dienstblock (0–3 Blöcke pro Quartal) gezählt statt als 2 Einzelschichten.
  - `Schedule.count_intern_weekends` zählt Schichten auf Basis von `ShiftType.SATURDAY_INTERN`.
  - `Schedule.count_weekends` differenziert rollenbasiert (Interns: Wochenend-Blöcke; TFA/Azubi: Einzelschichten).
  - `Schedule.count_total_notdienst` summiert für Interns effektive Nächte + Wochenend-Blöcke.
- **Solver Track 2 Fairness (`solver_cpsat.py`):**
  - Das Min-Max-Fairnessziel für Intern-Wochenenden summiert nun direkt die Samstags-Variablen (`Sa_Intern`) der gekoppelten Blöcke.
  - Die Spanne (`we_range`) misst die Differenz in echten Wochenenden ($0..3$), wodurch die Gewichtung $W_{\text{intern\_we\_fairness}} = 100$ exakt pro Wochenende greift (zuvor $4\times$ überhöht durch 4 Halb-Einheiten pro Wochenende).
- **UI & Validator-Korrektur (`streamlit_app.py`, `validator.py`):**
  - Die Spalte "WE" und die KPI-Kacheln ("Track 2: Ø WE", "WE-Spread") zeigen nun für Interns echte Wochenenden ($0..3$) statt verdoppelter Schichten ($0..6$).
  - Der Qualitäts-Penalty-Score in `validator.py` berechnet die Standardabweichung der Intern-Wochenenden auf Basis ganzer Blöcke.
- **Dokumentations-Harmonisierung (F1):**
  - `documentation/CONSTRAINTS.md` und `documentation/ARCHITECTURE.md` synchronisiert: Track 2 Fairness ist ein Soft-Ziel mit Gewichtung 100 pro Wochenende.

## [1.5.1] - 2026-11-01

### Changed: Rollen-Klarstellung Vets / Interns & Strikte Personal-Validierung

- **Rollen-Disambiguierung & D1-Bereinigung:**
  - Eindeutige Begriffs- und Rollentrennung: Vollapprobierte Entlastungs-Tierärzte heißen im gesamten Code und in der Dokumentation ausschließlich `Vet` (`Beruf.VET`). Tierärzte in Ausbildung / Weiterbildung heißen ausschließlich `Intern` (`Beruf.INTERN`).
  - Die mehrdeutigen Abkürzungen `TA` und `Tierarzt` wurden vollständig entfernt und werden beim Import explizit mit `StaffValidationError` zurückgewiesen.
  - Duplizierte Rollen-Normalisierung in `app/scheduler/file_loader.py` entfernt; `Staff.parse_beruf` dient als zentrale Source of Truth.
  - UI-Kennzeichnung in der Kalenderansicht auf `🩺 [Vet]` aktualisiert; Statistiken und Metriken verwenden einheitlich `Vet`/`Vets`.
- **Eingabevalidierung & ZeroDivisionError-Fix (B1):**
  - Neues Ausnahme-Modul `app/scheduler/exceptions.py` mit `StaffValidationError`, `ColumnMappingError`, `FileFormatError`.
  - Non-Vet-Mitarbeitende (TFA, Intern, Azubi) erfordern zwingend positive Wochenstunden (`hours > 0`) sowie vollständige Stammdaten (`adult`, `reception`, `nd_possible`, `nd_alone`). Leere oder 0-Stunden werden vor Solver-Start abgefangen.
  - Defensiver Guard gegen `ZeroDivisionError` in den Fairness-Zielen des CP-SAT-Solvers (`solver_cpsat.py`).
  - Einheitliches Boolean- und Stunden-Parsing in `file_loader.py` und `models.py:load_staff_from_csv`.
- **Tests & Regression:**
  - Neue Test-Suite `tests/test_staff_validation.py` zur Verifizierung von Non-Vet-Validierung, Vet-Defaults und Deprecation von `TA`/`Tierarzt`.

## [1.5.0] - 2026-11-01

### Added: Offene/Geschlossene Nächte, Intern-Wochenenden & Vet-Entlastung

> **Hinweis zur Versionshistorie:** Die in den einzelnen Feature-PRDs separat avisierten Zwischenversionen v1.3.0 (`PRD_FEATURE_OPEN_CLOSED_NIGHTS`), v1.4.0 (`PRD_INTERN_WEEKEND_SHIFTS`) und v1.5.0 (`PRD_tierarzt_nachtdienst_entlastung`) wurden in diesem konsolidierten Release v1.5.0 direkt zusammengeführt.

Umfassendes Release mit drei zentralen Erweiterungen der Dienstplanungslogik zur Entlastung des Teams und präzisen Abbildung des klinischen Notdienstbetriebs:

#### 1. Offene und geschlossene Nachtdienste (`PRD_FEATURE_OPEN_CLOSED_NIGHTS`)
- **Schicht-Kategorisierung:**
  - **Offene Nächte:** Sonntag→Montag (`N_So-Mo`) und Montag→Dienstag (`N_Mo-Di`) mit aktivem Klinik-/Praxisbetrieb erfordern zwingend eine Kopfzahl von exakt 2 Personen.
  - **Geschlossene Nächte:** Dienstag→Mittwoch bis Samstag→Sonntag (`N_Di-Mi`, `N_Mi-Do`, `N_Do-Fr`, `N_Fr-Sa`, `N_Sa-So`).
- **Besetzungsregeln & Qualifikation:**
  - Auf offenen Nächten ist mindestens eine erfahrene TFA verpflichtend (`Open Night Missing TFA`).
  - Zulässige Besetzungen für offene Nächte: TFA + TFA, TFA + Intern, TFA + Azubi. Verboten: Intern + Intern sowie Intern + Azubi.
  - Mitarbeiter mit `nd_alone=True` dürfen auf offenen Nächten im Team eingeteilt werden (auf geschlossenen Nächten müssen sie weiterhin strikt allein arbeiten).
- **Differenzierte Fairness-Gewichtung:**
  - Auf offenen Nächten zählt der Dienst für TFAs als halber Notdienst (Gewichtung 0.5×), für Azubis und Interns jedoch voll (Gewichtung 1.0× als Ausbildungs-/Weiterbildungsdienst).

#### 2. Intern-Wochenenddienste & 2-Track-Fairness (`PRD_INTERN_WEEKEND_SHIFTS`)
- **Spezifische Wochenendschichten:**
  - Einführung von `ShiftType.SATURDAY_INTERN` (`Sa_Intern`) und `ShiftType.SUNDAY_INTERN` (`So_Intern`).
  - Strikte Rollen-Exklusivität: Nur Interns dürfen diese Schichten besetzen; reguläre Wochenendschichten (`Sa_10-21`, `So_8-20` etc.) bleiben TFAs und volljährigen Azubis vorbehalten.
- **Atomare Wochenend-Kopplung (H-INT-1):**
  - Samstag und Sonntag eines Wochenendes werden stets als unteilbares Paar an denselben Intern vergeben; Einzeltage und gesplittete Wochenenden sind ausgeschlossen.
- **Monatliche Obergrenze & Mindestabstand (H-INT-2 & H-INT-4):**
  - Maximal 1 Intern-Wochenende pro Kalendermonat (ca. 3 Wochenenden pro Quartal bei 4 Interns).
  - Interns erhalten einen verkürzten Mindestabstand zwischen Einsätzen von 10 Tagen (im Vergleich zu 21 Tagen bei TFAs/Azubis).
- **Zwei-Track-Fairness:**
  - Track 1 steuert die Nachtdienste (strikter Korridor von 6–9 Nächten pro Quartal).
  - Track 2 steuert die Intern-Wochenenden mit gleichmäßiger Verteilung (Soft-Minimierung der Wochenend-Differenz, Gewichtung 100).

#### 3. Tierarzt-Nachtdienst-Entlastung (`PRD_tierarzt_nachtdienst_entlastung`)
- **Neue Mitarbeiterrolle `Beruf.VET` ("Vet"):**
  - Feste Invarianten über Modell-Validierung: `adult=True`, `hours=0`, `abteilung=OTHER`, `reception=False`, `nd_possible=True`, `nd_alone=True`, `nd_min_consecutive=2`, `nd_max_consecutive=2`.
  - Rollen-Synonyme ("Vet", "Tierarzt", "TA_Entlastung") werden beim Datenimport automatisch normalisiert.
- **Gezielte Midweek-Entlastung (Dienstag–Donnerstag):**
  - Tierärzte dürfen ausschließlich geschlossene Nächte im Zeitfenster `N_Di-Mi`, `N_Mi-Do`, `N_Do-Fr` übernehmen.
  - **Exakte 2-Nächte-Blöcke:** Einsätze erfolgen zwingend als 2-Nächte-Block am Stück (Di+Mi oder Mi+Do); Einzeltage oder 3er-Blöcke sind unzulässig.
  - **Strikter Alleindienst:** Bei Tierarzt-Einsatz ist die Kopfzahl exakt 1 (keine Begleitung durch TFA, Intern oder Azubi).
- **Häufigkeitsgrenze & Quartalsübergang:**
  - Maximal 1 Block alle 2 Monate pro Tierarzt (strikte Kalendermonatsgrenze: Einsatz im Monat $m$ sperrt $m+1$).
  - Historische Dienste am Ende des Vorquartals werden über `PreviousPlanContext.vet_active_last_month_ids` importiert und sperren den Tierarzt im ersten Monat des Folgequartals.
- **Solver-Priorisierung & Ausweichlogik:**
  - Hohe Zielgewichtung ($-100\,000$ pro Block) maximiert die TFA-Entlastung durch verfügbare Tierärzte; Sekundärziel ($500$) sorgt für faire Verteilung unter Tierärzten.
  - In Wochen ohne verfügbaren Tierarzt greifen nahtlos die regulären TFA/Intern-Besetzungsregeln.
- **Kapazitätsanalyse (Check F):**
  - Neuer Check F in der Machbarkeitsprüfung quantifiziert verfügbare Tierärzte, Entlastungsblöcke und Nächte und rechnet diese auf den geschlossenen Nachtbedarf an.
- **UI- und Export-Anpassungen:**
  - Anzeige von Tierärzten in der Personal- und Kalenderansicht (Präfix `🩺 [TA]`).
  - Eigene Tierarzt-Statistiktabelle ohne Division durch 0-Stunden.
  - Vollständiger Re-Import und Excel-Export von Tierarzt-Einsätzen.

## [1.2.0] - 2026-07-31

### Added: visual review of cross-quarter block-gap exceptions

Current working-tree change set; intended release commit has not yet been created.

- Added `CrossQuarterBlockGapException` and `find_cross_quarter_block_gap_exceptions()` in `app/scheduler/validator.py`.
  - The display-only analysis reconstructs block starts from the generated schedule and imported trailing assignments, using the active `SchedulerConfig` gap values.
  - It identifies only the solver's relaxed Q2→Q3 block-gap cases; a continuous block across the quarter boundary is not reported.
- Updated `page_plan_anzeigen()` in `app/streamlit_app.py`:
  - Affected calendar cells display `⚠️` with an orange highlight and a legend entry.
  - An expander lists the employee, previous and current block start, and actual versus required gap for each exception.
  - The export path is unchanged; indicator data is derived only while displaying the plan.
- Added `TestCrossQuarterBlockGapDisplay` in `tests/test_carry_forward.py` for a detected relaxed gap and a non-flagged continuous boundary block.
- Updated `tests/test_release_info.py`, `pyproject.toml`, `uv.lock`, and `app/release_info.py` for version `1.2.0`.

## [1.1.0] - 2026-07-31

### Added: dedicated About page and release metadata

Current working-tree change set; intended release commit has not yet been created.

- Added `app/release_info.py` as the application-level release metadata source:
  - `APP_NAME` and `CURRENT_VERSION` expose the display values.
  - Immutable `Release` dataclass stores a version, German display date, short expander-heading summary, and one to three user-facing highlights.
  - `RELEASES` is sorted newest first and contains the reconstructed product history.
- Replaced the sidebar expander with `page_about()` in `app/streamlit_app.py`:
  - Adds **Über diese App** to `nav_options` and routes it to the new page.
  - Displays the current version and release date with Streamlit metrics.
  - Renders the current release summary/highlights directly above the history, then one collapsed Streamlit expander per `RELEASES` entry using version, date, and short summary in the heading.
- Set the release version to `1.1.0` in `pyproject.toml`, `uv.lock`, and `app/release_info.py`.
- Added `tests/test_release_info.py` coverage for semantic version format, current-release ordering, the `1.0.0` productive milestone, uniqueness/readability of release entries, and package/display version alignment.
- Added `.github/skills/versioning/SKILL.md` to define the version bump, business changelog, validation, and release-maintenance workflow.

## [1.0.3] - 2026-07-12

### Fixed: predefined holiday shifts on weekends

Source commit: `0368547`.

- Updated `get_pre_assigned_holiday_dates()` and `generate_quarter_shifts()` in `app/scheduler/models.py`.
- A pre-assigned holiday on Saturday is now classified as a holiday before the ordinary Saturday branch is evaluated. This generates the required holiday/Sunday-pattern slots so the existing CP-SAT pinning constraints can bind the assignment.
- Sunday remains excluded from the extra holiday-date generation because normal Sunday slots already exist.

## [1.0.2] - 2026-05-31

### Added: previous-plan import and cross-quarter planning support

Primary source commits: `9c3ad57`, `9878c09`, `ff6ebb0`, `230bc30`, `be350e9`, `b502c55`, `b014261`, `3f1b2ca`, `adc8533`, `20bc00a`.

- Replaced the JSON carry-forward upload workflow with `build_previous_context_from_xlsx()` and Excel parsing in `app/scheduler/models.py` and `app/scheduler/file_loader.py`.
  - Import reconstructs trailing assignments and FTE-normalized carry-forward deltas from a prior schedule export.
  - Parser supports the export's multiple worksheets while retaining compatibility with earlier layouts.
- Extended cross-quarter solver handling in `app/scheduler/solver_cpsat.py`:
  - Applies the boundary block-gap logic between consecutive quarters.
  - Avoids treating trailing assignments from the same quarter as cross-quarter data.
  - Softens the boundary 3-week block constraint when a hard constraint would make an otherwise viable schedule infeasible.
- Added `Staff.available_from` and blocks assignment before an employee's start date in the planning and feasibility paths.
- Consolidated the Streamlit input flow into the upload page and moved related review views into tabs on the staff page.
- Split the Excel export into night-duty and weekend-duty worksheets, updated the parser to concatenate them during import, and refined export/fairness display columns.
- Completed the rules-page documentation and persisted the soft-penalty score so the fairness view can show a score breakdown.

## [1.0.1] - 2026-05-31

### Added: feasibility diagnostics and solver controls

Primary source commits: `68c4bb9`, `211e98a`, `02d68e8`.

- Added `app/scheduler/feasibility.py` with a pre-solve capacity analysis that checks viable night-duty blocks and reports errors or warnings before launching CP-SAT.
- Added `SchedulerConfig` and exposed configuration, random seed, quarter/year selection, and solve-time choices through the Streamlit UI.
- Added solver convergence logging via a CP-SAT callback and rendered progress/convergence information in the application.
- Improved infeasibility diagnostics and added tests for the new constraint/configuration paths.
- Standardized Excel export column order to `Wochentag`, `Datum`, `Mitarbeiter`, `Schicht`, and `Paarweise`.

## [1.0.0] - 2026-03-24

### First productive release

Primary source commits: `2150e28`, `89fa0bc`.

- Added flexible CSV/XLSX ingestion in `app/scheduler/file_loader.py`:
  - Normalizes column headers and resolves aliases instead of requiring one exact spelling.
  - Parses staff, vacation, and optional pre-assignment input files into scheduler models.
  - Added focused loader tests for the supported header and input variants.
- Added `PreAssignedShift` support across models, upload UI, validation, and the CP-SAT solver.
  - Pre-assigned duties are translated into fixed assignment constraints when their corresponding schedule slots are generated.
  - Upload and validation feedback exposes conflicts before scheduling.

## [0.3.0] - 2026-02-20

### Added: access control and review improvements

Primary source commits: `f6ac188`, `c8e12cc`, `8408e8d`, `48314ec`, `d5b487d`.

- Added optional login handling in `app/streamlit_app.py`:
  - Reads `password_hash` from Streamlit secrets or `PASSWORD_HASH` from the environment.
  - Compares SHA-256 hashes and gates all scheduling UI behind `st.session_state.authenticated` when configured.
- Removed the heuristic scheduling path and retained the CP-SAT solver behind the simpler facade in `app/scheduler/solver.py`.
- Corrected validator handling of staff-specific `nd_min_consecutive` values and exposed quick/thorough solve-time options.
- Added an optional birthday field to `Staff`; the solver treats the birthday as unavailable for all duty types.
- Refined plan-review and fairness UI components.

## [0.2.0] - 2026-01-31

### Added: operational constraint and fairness framework

Primary source commits: `143a9d4`, `0434158`, `a801397`, `9e368e6`, `bd3db9e`, `67583ca`, `d3c2f6b`, `c967dd6`.

- Expanded CP-SAT coverage, eligibility, pairing, rest, and workload constraints in `app/scheduler/solver_cpsat.py` and mirrored validation in `app/scheduler/validator.py`.
- Added department (`abteilung`) data to `Staff` and prevents incompatible department combinations on the same night duty.
- Added effective night-duty weighting for paired assignments and used role-aware FTE normalization in the fairness objective and review UI.
- Enforced the three-week night-duty block gap and a maximum fairness deviation, with employee-specific minimum consecutive night settings.
- Added vacation handling, duty-type balancing, calendar improvements, and general plan-review UI updates.

## [0.1.0] - 2026-01-25

### Initial internal prototype

Primary source commits: `87fe728`, `0633bad`, `8571576`, `f232ddf`, `62c2ab3`, `9c1f2e7`.

- Established the Streamlit application shell and package structure under `app/`.
- Introduced core scheduler models for staff, shifts, assignments, schedules, vacations, and role/eligibility metadata.
- Implemented initial quarter shift generation, schedule validation, and a CP-SAT-based scheduling path using OR-Tools.
- Added the first data upload, schedule review, fairness, and calendar views; later January prototype commits iterated on constraint strictness and review behavior.
