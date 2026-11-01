# Product Requirements Document (PRD)
# Feature: Offene und geschlossene Nachtdienste (Open & Closed Night Shifts)

**Dokument-Version:** 1.2 (Technisch spezifiziert & Codebase-abgeglichen)  
**Status:** Approved / Bereit zur Implementierung  
**Datum:** 01.11.2026  
**Zielversion:** 1.3.0 (Branch 1 von 3)  
**Ziel-Module:** `app/scheduler/models.py`, `app/scheduler/solver_cpsat.py`, `app/scheduler/validator.py`, `app/scheduler/feasibility.py`, `app/streamlit_app.py`  
**Verfasser:** Antigravity / Senior Python Engineer & Data Science Architect  

---

## 1. Übersicht & Geschäftskontext (Business Context)

In der Tierklinik wird der Notdienst (24/7) in zwei Betriebsmodi unterteilt:

1. **Offene Nächte (Open Nights):**
   - **Zeitraum:** Sonntag auf Montag (`N_So-Mo`) und Montag auf Dienstag (`N_Mo-Di`).
   - **Hintergrund:** An diesen Abenden/Nächten hat die Tierklinik regulären Praxisbetrieb. Daher fällt ein deutlich höheres Patienten- und Arbeitsaufkommen an als im reinen Notbetrieb.
   - **Besetzung:**
     - 1 Tierarzt (wird separat und manuell eingeteilt; nicht Teil dieser Software).
     - **Immer exakt 2 Personen** aus dem Mitarbeiterpool:
       - **Zwingend 1 TFA** als voll ausgebildete, feste Fachkraft.
       - **Genau 1 weitere Person**, wählbar aus: **TFA**, **Intern** oder **Azubi** (`1 TFA + 1 TFA/Intern/Azubi`).
       - Es werden **immer genau 2 Personen** eingeteilt – weder Alleindienste (1 Person) noch 3-Personen-Besetzungen sind zulässig. Azubis kommen nicht zusätzlich "on top", sondern besetzen den zweiten Schichtplatz an der Seite einer TFA.
   - **`nd_alone`-Regelung:** Für offene Nächte ist das Alleinarbeitsgebot (`nd_alone = True`) aufgehoben. Jeder Mitarbeiter kann an offenen Nächten im 2er-Team arbeiten, unabhängig vom Status `nd_alone`.
   - **Fairness-Bewertung:**
     - **TFAs** erhalten an offenen Nächten eine **halbe Nacht (0,5 effektive Nächte = 1 Half-Unit)** in der Fairness-Bewertung angerechnet, da der Dienst geteilt wird.
     - **Interns** erhalten für offene Nächte **1,0 effektive Nacht (2 Half-Units)** in der Fairness-Betrachtung angerechnet (keine Reduktion auf 0,5).
     - **Azubis** erhalten wie im gesamten Modell üblich stets **1,0 effektive Nacht (2 Half-Units)**.

2. **Geschlossene Nächte (Closed Nights):**
   - **Zeitraum:** Dienstag auf Mittwoch (`N_Di-Mi`) bis Samstag auf Sonntag (`N_Sa-So`) (5 Nächte pro Woche).
   - **Hintergrund:** Reiner Notdienstbetrieb für Notfälle.
   - **Besetzung:** 1–2 Personen (mindestens 1 Nicht-Azubi; bzw. 1 Tierarzt allein bei Di–Do-Entlastung gemäß Vet-PRD).
   - **`nd_alone`-Regelung:** Bleibt strikt bestehen:
     - `nd_alone = True`: Muss **komplett alleine** arbeiten (kein Partner, kein Azubi).
     - `nd_alone = False`: Muss **gepaart** arbeiten (mit Azubi oder weiterem Nicht-Azubi).

---

## 2. Detaillierte Fachanforderungen (Requirements)

### FR-1: Klassifizierung der Nachtschichten
- Jede Nachtschicht im Quartal wird automatisch typisiert:
  - `N_So-Mo` und `N_Mo-Di` = **Offene Nacht**
  - `N_Di-Mi`, `N_Mi-Do`, `N_Do-Fr`, `N_Fr-Sa`, `N_Sa-So` = **Geschlossene Nacht**

### FR-2: Besetzungsregeln für offene Nächte

- **FR-2.1 (Exakte Kopfzahl: Genau 2 Personen):**
  - Jede offene Nacht muss zwingend mit **exakt 2 Personen** besetzt sein ($\text{Headcount} = 2$).
  - Einzelbesetzungen (1 Person) sind verboten.
  - Besetzungen mit 3 Personen (z. B. 2 Nicht-Azubis + 1 Azubi) sind verboten.

- **FR-2.2 (Zwingende TFA-Beteiligung: Mindestens 1 TFA):**
  - An jeder offenen Nacht muss **mindestens eine Tiermedizinische Fachangestellte (`Beruf.TFA`)** eingeteilt sein ($\sum_{\text{TFA}} \ge 1$).

- **FR-2.3 (Zulässige Besetzungskombinationen):**
  Durch die Regel *„1 TFA + 1 TFA, Intern oder Azubi bei genau 2 Personen“* sind ausschließlich folgende 3 Paarungen zulässig:
  1. **TFA + TFA:** Zwei TFAs teilen sich die Nacht.
  2. **TFA + Intern:** Eine TFA wird von einem Intern begleitet.
  3. **TFA + Azubi:** Eine TFA wird von einem Azubi begleitet.

- **FR-2.4 (Unzulässige Kombinationen):**
  Folgende Besetzungen sind strikt ausgeschlossen:
  - ❌ **Intern + Intern:** Verboten, da keine TFA anwesend ist (Verletzung von FR-2.2).
  - ❌ **Intern + Azubi:** Verboten, da keine TFA anwesend ist (Verletzung von FR-2.2 und Azubi-Aufsichtspflicht).
  - ❌ **Azubi + Azubi:** Verboten (H4: niemals zwei Azubis auf einer Schicht; keine TFA).
  - ❌ **TFA solo:** Verboten (FR-2.1: Headcount muss 2 sein).
  - ❌ **2 TFAs + 1 Azubi:** Verboten (FR-2.1: Headcount muss 2 sein).

- **FR-2.5 (Azubi-Regeln auf offenen Nächten):**
  - Maximal 1 Azubi pro offener Nacht ($\sum_{\text{Azubi}} \le 1$).
  - Durch die zwingende TFA-Präsenz ist der Azubi stets mit einer Fachkraft gepaart (H3 erfüllt).
  - Azubis zählen als vollwertige 2. Person der Schicht (keine Begleitperson "on top").

- **FR-2.6 (Interns auf offenen Nächten):**
  - Maximal 1 Intern pro offener Nacht ($\sum_{\text{Intern}} \le 1$), da der Partner zwingend eine TFA sein muss.
  - Einsätze von Interns an offenen Nächten zählen regulär in ihr Quartalskontingent von 6–9 Nächten (H23).

- **FR-2.7 (Aufhebung der Alleinarbeit H6):**
  - An offenen Nächten greift die Solo-Einschränkung für `nd_alone = True` nicht.
  - Auch zwei Mitarbeiter mit `nd_alone = True` können gemeinsam eingeteilt werden, da offene Nächte durch das hohe Patientenaufkommen als Teamdienst definiert sind.

- **FR-2.8 (Abteilungstrennung H17 / H18 bleibt aktiv):**
  - **H17:** Zwei Mitarbeiter aus derselben Abteilung (`op` oder `station`) dürfen **nicht** in derselben offenen Nacht eingeteilt werden (z. B. dürfen nicht zwei OP-TFAs gemeinsam Dienst haben).
  - **H18:** Zwei Mitarbeiter aus derselben Abteilung dürfen nicht an aufeinanderfolgenden Tagen Nachtdienst haben.

- **FR-2.9 (Mindestblocklänge H7 bleibt aktiv):**
  - Die Mindestanzahl aufeinanderfolgender Nächte (`nd_min_consecutive`) bleibt bestehen.
  - Für Mitarbeiter mit `nd_min_consecutive = 2` decken die zwei aufeinanderfolgenden offenen Nächte (So–Mo + Mo–Di) exakt einen gültigen Block ab.
  - Mitarbeiter mit `nd_min_consecutive = 3` (z. B. Anika Alles) können an offenen Nächten nur eingeteilt werden, wenn der Block durch angrenzende geschlossene Nächte (z. B. Sa–So oder Di–Mi) auf ≥3 Nächte verlängert wird.

### FR-3: Feiertagsregelung & Vorab-Zuweisungen
- Gesetzliche Feiertage an Sonntagen oder Montagen gelten grundsätzlich als reguläre offene Nächte.
- Vorab manuell festgelegte Feiertagsdienste (`PreAssignedShift`) werden wie bisher als fixe Belegungen in das Modell geladen und vorrangig respektiert.

### FR-4: Fairness & Arbeitslast-Berechnung
- **FR-4.1 (0,5 Gewichtung für TFAs):**
  - TFAs erhalten für eine geteilte offene Nacht **0,5 effektive Nächte** (1 Half-Unit im CP-SAT-Modell).
- **FR-4.2 (1,0 Gewichtung für Interns):**
  - Interns (`Beruf.INTERN`), die an einer offenen Nacht arbeiten, erhalten für die Fairness-Betrachtung und das Quartalskontingent **1,0 effektive Nacht** (2 Half-Units im CP-SAT-Modell) und **nicht** eine halbe Nacht.
- **FR-4.3 (1,0 Gewichtung für Azubis):**
  - Ein Azubi (`Beruf.AZUBI`) auf einer offenen Nacht erhält stets **1,0 effektive Nacht** (2 Half-Units), analog zur bestehenden Azubi-Fairness-Logik.
- **FR-4.4 (Konsistenz über das Gesamtsystem & Solver-Modellierung):**
  - Da an offenen Nächten immer 2 Personen arbeiten, gilt für jede Zuweisung an einer offenen Nacht formal `is_paired = True`.
  - In der Half-Unit-Berechnung für Fairness und Kontingente:
    - TFA: 1 Half-Unit (0,5 effektive Nächte).
    - Intern: 2 Half-Units (1,0 effektive Nächte; offene Nächte zählen für Interns voll als 1 Nacht).
    - Azubi: 2 Half-Units (1,0 effektive Nächte).
  - Solver-Zielfunktion (Minimierung der FTE-Spreizung).
  - Solver Hard-Tolerance-Ceiling (`max_fte - min_fte <= tolerance`).
  - Validator Soft-Penalty (`_calculate_soft_penalty`).
  - Excel-Export (`Paarweise = "Ja"`).
  - Übertrag ins Folgequartal (`carry_forward_delta`).

### FR-5: Keine separate Ausweisung des externen Tierarztes
- Da der externe Tierarzt für offene Nächte separat/manuell geplant wird, erfolgt keine Anzeige oder Spalte für diese Tierärzte in der UI oder im Excel-Export. (Tierärzte zur Midweek-Entlastung Di–Do werden hingegen separat über das Vet-Feature geplant).

---

## 3. Technische Spezifikation & Code-Änderungen

### 3.1 Datenmodelle (`app/scheduler/models.py`)
1. **Hilfsmethoden auf `Shift`:**
   ```python
   def is_open_night(self) -> bool:
       """Check if this is an open night (Sun-Mon or Mon-Tue)."""
       return self.shift_type in (ShiftType.NIGHT_SUN_MON, ShiftType.NIGHT_MON_TUE)

   def is_closed_night(self) -> bool:
       """Check if this is a closed night (Tue-Wed through Sat-Sun)."""
       return self.is_night_shift() and not self.is_open_night()
   ```
2. **Rollenspezifische Gewichtung effektiver Nächte (`Staff.effective_nights_weight` & `Schedule.count_effective_nights`):**
   - Da an offenen Nächten stets 2 Personen eingeteilt sind (`Assignment.is_paired == True`), muss `Staff.effective_nights_weight` um den Parameter `is_open_night: bool = False` erweitert werden, damit Interns an offenen Nächten trotz `is_paired=True` mit **1,0** statt **0,5** gewichtet werden:
     ```python
     def effective_nights_weight(self, is_paired: bool, is_open_night: bool = False) -> float:
         """Calculate effective night weight for fairness.

         - Azubis always count as 1.0 effective night (even when paired).
         - Interns on open nights (N_So-Mo, N_Mo-Di) count as 1.0 effective night.
         - Non-Azubis on closed nights (and TFAs on open nights): paired = 0.5, solo = 1.0.
         """
         if self.beruf == Beruf.AZUBI:
             return 1.0
         if self.beruf == Beruf.INTERN and is_open_night:
             return 1.0
         return 0.5 if is_paired else 1.0
     ```
   - In `Schedule.count_effective_nights(self, staff_identifier: str, staff: Staff | None = None) -> float` wird `a.shift.is_open_night()` übergeben:
     ```python
     if staff is not None:
         return sum(
             staff.effective_nights_weight(a.is_paired, is_open_night=a.shift.is_open_night())
             for a in night_assignments
         )
     ```
   - Dadurch sind `Schedule.count_total_notdienst()`, `compute_carry_forward()`, `validator._calculate_soft_penalty()` sowie die Fairness-Tabellen in `streamlit_app.py` automatisch konsistent mit dem CP-SAT-Solver.
3. **In `Assignment`:** Auf offenen Nächten gesetzte reguläre Schichten haben durch die 2-Personen-Besetzung stets `is_paired = True`.

### 3.2 Solver (`app/scheduler/solver_cpsat.py`)

1. **Nachtkategorisierung (ersetzt `intern_present_nights` / `regular_nights` / `is_vet_present`):**
   ```python
   open_nights = [s for s in night_shifts if s.is_open_night()]
   closed_nights = [s for s in night_shifts if s.is_closed_night()]
   ```

2. **Schichtabdeckung für Nachtdienste (Constraint #2 in `generate_schedule_cpsat`):**
   - Vorab zugewiesene Feiertagsnächte (`shift_slot in pre_assigned_shift_slots`) behalten ihren Vorrang (`model.Add(sum(all_vars) == target)`).
   - Für reguläre **offene Nächte** (`shift.is_open_night()`):
     ```python
     tfa_vars = [
         x[(s.identifier, shift.shift_date, shift.shift_type)]
         for s in staff_list
         if (s.identifier, shift.shift_date, shift.shift_type) in x
         and s.beruf == Beruf.TFA
     ]
     azubi_vars = [
         x[(s.identifier, shift.shift_date, shift.shift_type)]
         for s in staff_list
         if (s.identifier, shift.shift_date, shift.shift_type) in x
         and s.beruf == Beruf.AZUBI
     ]
     all_vars = [
         x[(s.identifier, shift.shift_date, shift.shift_type)]
         for s in staff_list
         if (s.identifier, shift.shift_date, shift.shift_type) in x
     ]

     # 1. Gesamtkopfzahl immer exakt 2 Personen
     model.Add(sum(all_vars) == 2)

     # 2. Mindestens 1 TFA zwingend erforderlich
     model.Add(sum(tfa_vars) >= 1)

     # 3. Maximal 1 Azubi (verhindert Azubi + Azubi)
     if azubi_vars:
         model.Add(sum(azubi_vars) <= 1)
     ```
   > **Beweis der Vollständigkeit:**
   > - Da $\sum \text{all} = 2$ und $\sum \text{TFA} \ge 1$:
   >   - Wenn $\text{TFA} = 2 \implies \text{Intern} = 0, \text{Azubi} = 0$ (Kombination: TFA + TFA)
   >   - Wenn $\text{TFA} = 1$:
   >     - Entweder $\text{Intern} = 1, \text{Azubi} = 0$ (Kombination: TFA + Intern)
   >     - Oder $\text{Azubi} = 1, \text{Intern} = 0$ (Kombination: TFA + Azubi)
   >     - Oder $\text{TFA} = 1$ (weitere TFA, also TFA = 2)
   >   - Kombinationen wie `Intern + Intern`, `Intern + Azubi` oder `Azubi + Azubi` haben $\sum \text{TFA} = 0$ und sind somit mathematisch unmöglich.

3. **Paarungs-Variable (`is_paired`) & Half-Unit-Berechnung:**
   - Die Verknüpfung von `is_paired[(s.identifier, shift.shift_date)]` über `coverage_sum == 2` wird für **alle** Nachtschichten (offene und geschlossene Nächte) ausgeführt (Entfall der bisherigen `if not is_vet_present:`-Ausnahme bei der `is_paired`-Bindung). Da auf offenen Nächten `coverage_sum == 2` erzwungen wird, gilt dort für jeden eingeteilten Mitarbeiter automatisch `is_paired == 1`.
   - **Arbeitslast/Fairness-Beitrag in `notdienst_half_counts` / `night_half_counts`:**
     - **Azubi (`Beruf.AZUBI`)** (alle Nächte) sowie **Intern (`Beruf.INTERN`) auf offenen Nächten (`shift.is_open_night()`)**: `2 * x[key]` (2 Half-Units = 1,0 effektive Nächte).
     - **TFA (`Beruf.TFA`)** (alle Nächte) sowie **Intern (`Beruf.INTERN`) auf geschlossenen Nächten (`shift.is_closed_night()`)**: `2 * x[key] - paired_assigned` (1 Half-Unit = 0,5 effektive Nächte bei Paarung, 2 Half-Units = 1,0 bei Alleindienst).

4. **`nd_alone`-Einschränkung (Constraint #3 in `generate_schedule_cpsat`):**
   - Die Alleinarbeits-Beschränkung (`var + other_var <= 1`) für Mitarbeiter mit `nd_alone = True` sowie die explizite Paarungs-Implikation für `nd_alone = False` werden **ausschließlich für `shift.is_closed_night()`** aktiviert (auf offenen Nächten arbeiten ohnehin immer 2 Personen im Team).

### 3.3 Validierung (`app/scheduler/validator.py`)
- **Ablösung von `_check_intern_night_capacity` durch `_check_open_night_capacity(schedule, staff_dict)`:**
  - Ersetzt den bisherigen Aufruf `_check_intern_night_capacity` in `validate_schedule()`.
  - Überspringt Schichten, die über `is_pre_assigned=True` extern als Feiertagsdienst fest vorgegeben wurden.
  - Prüft für jede belegte offene Nacht (`shift.is_open_night()`):
    - `len(assignments) != 2` $\implies$ `ConstraintViolation("Open Night Headcount", ...)` (Exakt 2 Personen erforderlich).
    - `sum(1 for p in assigned_staff if p.beruf == Beruf.TFA) < 1` $\implies$ `ConstraintViolation("Open Night Missing TFA", ...)` (Mindestens 1 TFA erforderlich; fängt `Intern + Intern`, `Intern + Azubi` und `Azubi + Azubi` ab).
    - `sum(1 for p in assigned_staff if p.beruf == Beruf.AZUBI) > 1` $\implies$ `ConstraintViolation("Multiple Azubis on Night", ...)`.
- **`_check_nd_alone_improper_pairing` (H6):**
  - Überspringt offene Nächte (`if shift_type in (ShiftType.NIGHT_SUN_MON, ShiftType.NIGHT_MON_TUE): continue` bzw. `assignment.shift.is_open_night()`), sodass `nd_alone = True` auf offenen Nächten keinen Fehler auslöst.
- **`_check_night_pairing_constraint`:**
  - Prüft `nd_alone = False` unverändert; da auf offenen Nächten `len(assignments) == 2` gilt, ist die Bedingung dort automatisch erfüllt.
- **`_check_abteilung_night_constraint` (H17/H18):**
  - Prüft unverändert, dass nicht zwei Mitarbeiter derselben Fachabteilung (`op` oder `station`) auf derselben offenen Nacht oder an aufeinanderfolgenden Nächten liegen.

### 3.4 Kapazitätsprüfung & Machbarkeit (`app/scheduler/feasibility.py`)
- Im 13-Wochen-Quartal gibt es 26 offene Nächte (13 × So–Mo, 13 × Mo–Di) und 65 geschlossene Nächte.
- **Anpassung von Check A (`Non-Azubi Nacht-Kapazität`) in `analyze_capacity()`:**
  - **Bedarf an offenen Nächten:** 26 Nächte × 2 Personen = 52 Schichtplätze (davon mind. 26 zwingend durch TFAs; bis zu 26 Plätze können durch Azubis, Interns oder weitere TFAs abgedeckt werden).
  - **Bedarf an geschlossenen Nächten:** Mindestens 65 Non-Azubi-Schichtplätze (plus Zusatzbedarf für Mitarbeiter mit `nd_alone = False`, soweit keine Azubis als Partner verfügbar sind).
  - Check A prüft separat, ob die geschätzte TFA-Blockkapazität ($\sum_{s \in \text{TFA}} \text{blocks}_s \cdot s.\text{nd\_min\_consecutive}$) mindestens die 26 Pflicht-TFA-Plätze der offenen Nächte abdeckt und ob die kombinierte Non-Azubi- + Azubi-Kapazität die 91 Nächte inklusive der 26 zweiten Plätze auf offenen Nächten (gesamt mind. 117 Schichtplätze) abdeckt.

### 3.5 UI-Texte & Constraint-Labels (`app/streamlit_app.py`)
- **`page_regeln()`:** Aktualisierung des Abschnitts `🌙 Nachtdienste – Besetzung & Rollen` auf die Terminologie **Offene Nächte** (`N_So-Mo`, `N_Mo-Di`: exakt 2 Personen, `1 TFA + 1 TFA/Intern/Azubi`, `nd_alone` aufgehoben, Fairness: TFA 0,5×, Intern 1,0×, Azubi 1,0×) und **Geschlossene Nächte** (`N_Di-Mi` bis `N_Sa-So`).
- **`page_plan_anzeigen()` (`tab_stats` & `tab_validation`):**
  - Aktualisierung der Berechnungslogik-Erklärung im Expander `ℹ️ Berechnungslogik` (Interns auf offenen Nächten = 1,0×).
  - In `known_constraints` (`tab_validation`): Ersatz von `"Intern Night No Non-Azubi"` durch `"Open Night Headcount": "Offene Nacht: Exakt 2 Personen (So-Mo, Mo-Di)"` und `"Open Night Missing TFA": "Offene Nacht: Mind. 1 TFA erforderlich (So-Mo, Mo-Di)"`.

---

## 4. Test- & Verifikationsplan

| Testfall | Beschreibung | Erwartetes Ergebnis |
|---|---|---|
| **T1: Exakte Kopfzahl 2** | Solver erzeugt Quartalsplan | Jede offene Nacht hat **ausnahmslos exakt 2 Personen** (weder 1 noch 3 Personen). |
| **T2: Zwingende TFA-Beteiligung** | Jede offene Nacht prüfen | An jeder offenen Nacht ist mindestens 1 TFA eingeteilt. |
| **T3: Zulässige Kombination TFA + TFA** | 2 TFAs auf offener Nacht | Gültig (sofern H17-Abteilungstrennung gewahrt ist). |
| **T4: Zulässige Kombination TFA + Intern** | 1 TFA und 1 Intern auf offener Nacht | Gültig. |
| **T5: Zulässige Kombination TFA + Azubi** | 1 TFA und 1 Azubi auf offener Nacht | Gültig. Azubi ist durch TFA beaufsichtigt (H3). |
| **T6: Verbot Intern + Intern** | Intern und Intern manuell gepaart | Validator meldet Fehler (keine TFA). |
| **T7: Verbot Intern + Azubi** | Intern und Azubi manuell gepaart | Validator meldet Fehler (keine TFA). |
| **T8: `nd_alone=True` auf offener Nacht** | Mitarbeiter mit `nd_alone=True` auf `N_So-Mo` | Gültig, keine Infeasibility im Solver, kein H6-Fehler im Validator. |
| **T9: `nd_alone=True` auf geschlossener Nacht** | Mitarbeiter mit `nd_alone=True` an Di–Mi | Muss weiterhin zwingend alleine eingeteilt sein. |
| **T10: Abteilungstrennung H17** | Zwei OP-TFAs auf derselben offenen Nacht | Solver verhindert dies; Validator meldet H17-Verletzung. |
| **T11: Fairness-Gewichtung** | Berechnung der effektiven Nächte | TFA erhält 0,5 effektive Nächte (1 Half-Unit); Intern erhält 1,0 effektive Nacht (2 Half-Units); Azubi erhält 1,0 (2 Half-Units). |
