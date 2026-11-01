# Product Requirements Document (PRD)
# Feature: Tierarzt-Nachtdienst-Entlastung (Vet Midweek Night Shift Relief)

**Dokument-Version:** 1.2 (Technisch spezifiziert & Codebase-abgeglichen)  
**Status:** Bereit zur Implementierung  
**Ziel-Release:** 1.5.0 (Branch 3 von 3)  
**Ziel-Module:** `app/scheduler/models.py`, `app/scheduler/file_loader.py`, `app/scheduler/solver_cpsat.py`, `app/scheduler/validator.py`, `app/scheduler/feasibility.py`, `app/streamlit_app.py`  
**Verfasser:** Antigravity / Senior Python Engineer & Data Science Architect  

---

## 1. Übersicht & Zielsetzung

### 1.1 Ausgangslage & Problemstellung
Im Notdienst-Dienstplan einer Tierklinik werden Nacht- und Wochenenddienste primär durch Tiermedizinische Fachangestellte (**TFAs**), unterstützt durch Auszubildende (**Azubis**) und **Interns** abgedeckt. Während Sonntags- und Montagsnächte (`N_So-Mo`, `N_Mo-Di`) als offene Nächte mit Praxisbetrieb mit 2 Personen (1 TFA + 1 TFA/Intern/Azubi) und einem externen Tierarzt besetzt sind, stellen die Nächte in der Wochenmitte (**Dienstag bis Donnerstag**) eine erhebliche Belastung für das TFA-Team dar.

### 1.2 Lösungskonzept
Einführung einer neuen Mitarbeiterklasse: **Tierärzte (`Beruf.VET = "Vet"`)**.
- Tierärzte übernehmen gezielt Nachtdienste im Zeitfenster **Dienstag bis Donnerstag**.
- **Block-Länge:** Tierärzte leisten in diesem Zeitfenster **einen 2-Nächte-Block am Stück** (entweder Di→Mi + Mi→Do oder Mi→Do + Do→Fr).
- **Einsatzfrequenz:** **1x pro 2 Monate pro Tierarzt** (strikte Kalendermonatsgrenze, inklusive Quartalsübergang).
- **Alleindienst:** Tierärzte arbeiten in diesen Nächten **vollständig allein** (Kopfzahl = 1). Es wird in diesen Nächten weder eine TFA noch ein Azubi oder Intern eingeteilt.
- **Incentive / Priorisierung:** Der Solver nutzt Tierärzte im Rahmen ihrer Verfügbarkeit und der 2-Monats-Grenze maximal aus, um das TFA-Team bestmöglich zu entlasten.
- **Ausweichlogik (Fallback):** In Wochen ohne verfügbaren Tierarzt greift der Planer nahtlos auf die gewohnte TFA/Intern-Besetzung zurück.

---

## 2. Abgestimmte Business Rules & Spezifikation

| Nr. | Thema | Festlegung / Spezifikation |
|:---|:---|:---|
| **R1** | **Besetzung** | Tierärzte arbeiten in ihren Nächten **allein**. Kopfzahl = genau 1. Keine Begleitung durch TFAs, Azubis oder Interns. |
| **R2** | **Zeitfenster & Block-Länge** | Zeitfenster: Di→Mi, Mi→Do, Do→Fr. Ein Tierarzt leistet **genau einen 2-Nächte-Block am Stück** (entweder Di+Mi oder Mi+Do). Einzeltage sowie 3-Nächte-Blöcke sind ausgeschlossen. |
| **R3** | **Anschluss d. 3. Nacht** | Da der TA-Einsatz genau 2 Nächte umfasst, bleibt eine Nacht des Di–Do-Fensters frei (z. B. Do→Fr). Diese wird nahtlos durch TFAs/Interns mit der Folgenacht (Fr→Sa) verbunden, sodass die TFA-Mindestblocklänge von 2 Nächten (`nd_min_consecutive=2`) gewahrt bleibt. |
| **R4** | **Häufigkeitsgrenze** | **1x pro 2 Monate pro Tierarzt (Kalendermonatsgrenze):** Höchstens 1 Block in zwei aufeinanderfolgenden Kalendermonaten (z. B. Einsatz im April verbietet Mai; frühestens Juni wieder zulässig). Im 13-Wochen-Quartal bedeutet dies maximal 1–2 Blöcke pro TA. |
| **R5** | **Quartalsübergang** | Historische Dienste am Ende des Vorquartals (z. B. Ende März) werden über `PreviousPlanContext` importiert und sperren den Tierarzt im ersten Monat des Folgequartals (April). |
| **R6** | **Datenintegration** | Tierärzte werden in die **bestehende Personaldatei** (`staff.xlsx` / `staff.csv`) aufgenommen. Rolle: `Beruf = "Vet"`. Keine Abteilung, keine Arbeitsstunden, keine Wochentags-Sperren. Urlaube laufen über `vacations.xlsx`. |
| **R7** | **Solver-Incentive & Fairness** | 1. Priorität: Maximale Belegung verfügbarer 2-Nächte-TA-Blöcke.<br>2. Priorität: Gleichmäßige Verteilung der Blöcke unter allen verfügbaren Tierärzten. |
| **R8** | **Ausweichlogik** | Falls in einer Woche kein TA verfügbar ist, greifen automatisch die regulären TFA/Intern-Besetzungsregeln für die gesamte Woche. |

---

## 3. Datenmodell & Dateiformat

### 3.1 Anpassung des Rollen-Enums
In [`app/scheduler/models.py`](file:///home/e/Desktop/antigravity-projects/scheduling/app/scheduler/models.py#L19):
```python
class Beruf(str, Enum):
    TFA = "TFA"
    AZUBI = "Azubi"
    INTERN = "Intern"
    VET = "Vet"  # Tierärzte für Nachtdienst-Entlastung
```

### 3.2 Tierarzt-Attribute im `Staff`-Modell & CSV/XLSX-Lader
Tierärzte nutzen dieselbe `Staff`-Klasse mit festen Invarianten. Da in `staff.xlsx` / `staff.csv` für Tierärzte Felder wie Stunden, Abteilung oder Mindest-/Maximalnächte leer gelassen werden können (R6), erzwingt ein `@model_validator(mode="after")` auf `Staff` in `app/scheduler/models.py` automatisch diese Invarianten, sobald `self.beruf == Beruf.VET`:
- `identifier`: 2–4 stelliges Kürzel (z. B. `TA_MUE`, `DRM`)
- `name`: Vollständiger Name mit Titel (z. B. `Dr. Martin Müller`)
- `adult`: `True`
- `hours`: `0` (Tierärzte fließen nicht in die Stunden-/FTE-Fairness-Berechnung von TFAs ein)
- `beruf`: `Beruf.VET`
- `abteilung`: `Abteilung.OTHER` (keine Sperren ggü. Station/OP)
- `reception`: `False` (keine Wochenend-Anmeldung)
- `nd_possible`: `True`
- `nd_alone`: `True` (Arbeiten stets solo)
- `nd_min_consecutive`: `2` (strikte Vorgabe: genau 2 Nächte am Stück)
- `nd_max_consecutive`: `2` (strikte Vorgabe: genau 2 Nächte am Stück)
- `nd_exceptions`: `[]` (Einschränkung auf Di–Do erfolgt primär über Schicht-Zulässigkeit, sofern nicht explizit gesetzt)

In `app/scheduler/file_loader.py` (`load_staff_from_file`) akzeptiert die Rollen-Spalte zusätzlich Synonyme wie `"Vet"`, `"Tierarzt"`, `"TA_Entlastung"` und normalisiert diese auf `"Vet"`.

### 3.3 Shift-Eligibility (`can_work_shift`)
In [`Staff.can_work_shift(shift_type, shift_date)`](file:///home/e/Desktop/antigravity-projects/scheduling/app/scheduler/models.py#L136):
- Tierärzte dürfen **ausschließlich** folgende geschlossene Nächte arbeiten:
  - `ShiftType.NIGHT_TUE_WED` (`N_Di-Mi`)
  - `ShiftType.NIGHT_WED_THU` (`N_Mi-Do`)
  - `ShiftType.NIGHT_THU_FRI` (`N_Do-Fr`)
- Tierärzte sind für Wochenendschichten (`Sa_*`, `So_*`) und alle anderen Nächte (`N_So-Mo`, `N_Mo-Di`, `N_Fr-Sa`, `N_Sa-So`) **vollständig gesperrt**:
  ```python
  if self.beruf == Beruf.VET:
      if not self.nd_possible:
          return False
      if shift_date.isoweekday() in self.nd_exceptions:
          return False
      return shift_type in (
          ShiftType.NIGHT_TUE_WED,
          ShiftType.NIGHT_WED_THU,
          ShiftType.NIGHT_THU_FRI,
      )
  ```

### 3.4 Quartalsübergang in `PreviousPlanContext` (`app/scheduler/models.py`)
- Aktuell speichert `build_previous_context()` nur `trailing_days: int = 21`. Da ein Kalendermonat 30–31 Tage hat, würde ein Tierarzt-Einsatz am Anfang des letzten Vorquartals-Monats (z. B. 03.–04. März vor Quartalsende 31. März) bei einem 21-Tage-Fenster verloren gehen.
- **Technische Anpassung:**
  - `PreviousPlanContext` erhält ein zusätzliches Feld `vet_active_last_month_ids: list[str] = Field(default_factory=list)` (oder `trailing_days` für `TrailingAssignment` wird auf 31 Tage erweitert, wobei `_add_block_constraints` und `_add_nd_max_consecutive_constraints` für TFAs/Azubis weiterhin nur ihr jeweiliges `staff_gap_days`-Fenster prüfen).
  - In `build_previous_context()` werden alle `staff_identifier` erfasst, die im letzten Kalendermonat des Vorquartals (`a.shift.shift_date.month == schedule.quarter_end.month`) mindestens eine Nachtschicht (`N_Di-Mi`, `N_Mi-Do`, `N_Do-Fr`) geleistet haben.

---

## 4. Mathematische Formulierung im CP-SAT-Solver (`app/scheduler/solver_cpsat.py`)

### 4.1 Variablen & Umgang mit Quartalsgrenzen
1. **Zuweisung:** $x[v, d, t] \in \{0, 1\}$ für Tierarzt $v$, Datum $d \in \{\text{Di, Mi, Do}\}$, Schicht $t$.
2. **Wochen-Block-Indikatoren (2 Nächte am Stück):**  
   In einem 91-Tage-Quartal liegen bis zu 13 vollständige Di–Do-Fenster. **Wichtiger Randfall (Quartalsgrenze):** Beginnt ein Quartal an einem Mittwoch (wie Q2 2026 am `01.04.2026`) oder endet an einem Dienstag (wie Q2 2026 am `30.06.2026`), existieren am Quartalsrand unvollständige Di–Do-Fenster:
   - Für jede Woche $w$ im Quartal und jeden Tierarzt $v$ wird:
     - $b_{\text{DiMi}}[v, w] \in \{0, 1\}$ **nur erzeugt**, wenn sowohl $(v, d_{\text{Di}}, \text{N\_Di-Mi}) \in x$ als auch $(v, d_{\text{Mi}}, \text{N\_Mi-Do}) \in x$ im Quartal (und ohne Urlaub) existieren.
     - $b_{\text{MiDo}}[v, w] \in \{0, 1\}$ **nur erzeugt**, wenn sowohl $(v, d_{\text{Mi}}, \text{N\_Mi-Do}) \in x$ als auch $(v, d_{\text{Do}}, \text{N\_Do-Fr}) \in x$ im Quartal (und ohne Urlaub) existieren.
     - $b[v, w] = b_{\text{DiMi}}[v, w] + b_{\text{MiDo}}[v, w] \le 1$ (höchstens ein 2-Nächte-Block pro Woche).
     - Hat eine isolierte Randnacht (z. B. Dienstag `30.06.2026` am Quartalsende ohne Mittwoch im selben Quartal) keinen gültigen 2-Nächte-Block in $w$, erzwingt H-TA-1 automatisch $x[v, d, t] = 0$.

### 4.2 Hard Constraints

#### H-TA-1: Atomare 2-Nächte-Blockbindung
Für jeden Tierarzt $v$ und jede zulässige Schicht $(v, d, t) \in x$ ist die Schichtvariable exakt gleich der Summe der aktiven Block-Indikatoren, die diesen Tag abdecken:
- Für Dienstag ($d_{\text{Di}}$): $x[v, d_{\text{Di}}, \text{N\_Di-Mi}] == b_{\text{DiMi}}[v, w]$ (bzw. $0$, falls $b_{\text{DiMi}}[v, w]$ wegen Urlaub/Quartalsrand nicht existiert).
- Für Mittwoch ($d_{\text{Mi}}$): $x[v, d_{\text{Mi}}, \text{N\_Mi-Do}] == b_{\text{DiMi}}[v, w] + b_{\text{MiDo}}[v, w]$.
- Für Donnerstag ($d_{\text{Do}}$): $x[v, d_{\text{Do}}, \text{N\_Do-Fr}] == b_{\text{MiDo}}[v, w]$ (bzw. $0$, falls $b_{\text{MiDo}}[v, w]$ nicht existiert).
Damit sind Einzeltage sowie 3-Nächte-Blöcke ($b_{\text{DiMi}} + b_{\text{MiDo}} \le 1$) mathematisch ausgeschlossen.

#### H-TA-2: Alleindienst & Verdrängung (Headcount = 1)
Für jede geschlossene Nacht $d \in \{\text{Di, Mi, Do}\}$:
1. Maximal 1 Tierarzt pro Nacht (und damit maximal 1 Tierarzt-Block pro Woche $w$ über alle Tierärzte hinweg):
   $$\sum_{v \in \mathcal{V}} x[v, d, t] \le 1$$
2. **Integration in bestehende Coverage- & `nd_alone`-Logik in `solver_cpsat.py`:**
   - Da Tierärzte `beruf != Beruf.AZUBI` und `nd_alone = True` besitzen, greift für sie auf geschlossenen Nächten automatisch die bestehende Alleinarbeits-Bedingung (`var + other_var <= 1` gegen alle anderen Mitarbeiter inkl. TFA, Intern, Azubi und andere Tierärzte) sowie die reguläre Schichtabdeckung (`1 <= sum(all_vars) <= 2`).
   - Wenn ein Tierarzt eingeteilt ist ($x[v, d, t] = 1$), erzwingt `var + other_var <= 1` automatisch, dass an dieser Nacht `0` TFAs, `0` Interns und `0` Azubis eingeteilt sind ($\text{Headcount} = 1$).
   - Wenn kein Tierarzt eingeteilt ist ($\sum_{v \in \mathcal{V}} x[v, d, t] = 0$), greifen unverändert die regulären TFA/Intern/Azubi-Besetzungsregeln.

#### H-TA-3: Frequenzgrenze: 1x pro 2 Monate (Kalendermonatsgrenze)
Sei $M(b)$ der Kalendermonat der **ersten Nacht** des jeweiligen 2-Nächte-Blocks ($d_{\text{Di}}.\text{month}$ für $b_{\text{DiMi}}$ bzw. $d_{\text{Mi}}.\text{month}$ für $b_{\text{MiDo}}$).
Für jedes Paar aufeinanderfolgender Kalendermonate $(m_1, m_2)$ im Quartal und jeden Tierarzt $v$:
$$\sum_{b \text{ mit } M(b) \in \{m_1, m_2\}} b[v] \le 1$$

#### H-TA-4: Quartalsübergang (`PreviousPlanContext`)
War Tierarzt $v$ im letzten Kalendermonat des Vorquartals aktiv (`v.identifier in previous_context.vet_active_last_month_ids` bzw. Nachtdienst im Monat `previous_context.quarter_end.month`), wird der erste Kalendermonat des aktuellen Quartals (`m_1 = quarter_start.month`) für diesen Tierarzt gesperrt:
$$\sum_{b \text{ mit } M(b) = m_1} b[v] == 0$$

#### H-TA-5: Ausschluss aus TFA/Azubi-Mindestteilnahme & Stunden-Fairness
- In `_add_min_participation_constraints` (`solver_cpsat.py`): Tierärzte (`staff.beruf == Beruf.VET`) werden übersprungen (`if staff.nd_possible and staff.beruf != Beruf.VET:`), da ein Tierarzt durch Urlaub oder H-TA-4 legitim 0 Blöcke im Quartal haben kann.
- In `_add_group_fairness_objective_with_presence` (`solver_cpsat.py`) und `compute_carry_forward` (`models.py`): Tierärzte haben `hours = 0` und dürfen **nicht** durch `staff.hours` dividiert werden (verhindert `ZeroDivisionError`).
- In `_calculate_soft_penalty` (`validator.py`): Tierärzte (`staff.beruf == Beruf.VET`) werden bei der stundenproportionalen Abweichung (`staff.hours / total_hours`) ausgeschlossen.

### 4.3 Objective Terms (Zielfunktion)
1. **Maximierung der Tierarzt-Entlastung (stark gewichtet):**
   Für jeden möglichen Wochen-Block $b[v, w]$ (bzw. als Strafterm für ungenutzte mögliche Tierarzt-Kapazität):
   $$\text{Minimize} \quad - W_{\text{vet}} \cdot \sum_{w} \sum_{v \in \mathcal{V}} b[v, w]$$
   mit $W_{\text{vet}} = 100\,000$ (deutlich höher als die regulären Fairness-Spannen `~200–500`, aber unterhalb der Cross-Quarter-Block-Gap-Strafe `10_000_000`).
2. **Gleichmäßige Verteilung unter den Tierärzten (Sekundärziel):**
   Für $|\mathcal{V}| \ge 2$ sei $\text{blocks}_v = \sum_{w} b[v, w] \in \{0, 1, 2\}$. Minimiere:
   $$W_{\text{vet\_fairness}} \cdot (\max_{v \in \mathcal{V}} \text{blocks}_v - \min_{v \in \mathcal{V}} \text{blocks}_v)$$
   mit $W_{\text{vet\_fairness}} = 500$.

---

## 5. Kapazitätsanalyse & finale Kennzahlen

Basierend auf der getroffenen Entscheidung (**2-Nächte-Block, 1x alle 2 Monate**) ergeben sich im 13-Wochen-Quartal (91 Nächte) folgende Kennzahlen:

| Pool-Größe | Frequenz | TA-Blöcke (Wochen) | TA-Nächte gesamt | Di–Do Quote | Rest-Nächte TFA & Intern | H22 / Intern-Status |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **4 Tierärzte** | **1x / 2 Monate** | **6 / 13 Wochen** | **12 Nächte** | **30.8%** | **79 Nächte** (Interns: 24–36, TFAs: 43–55) | ✅ Perfekt machbar |
| **5 Tierärzte** | **1x / 2 Monate** | **8 / 13 Wochen** | **16 Nächte** | **41.0%** | **75 Nächte** (Interns: 24–36, TFAs: 39–51) | ✅ **Empfohlener Standard** |

> [!IMPORTANT]
> **Vorteile dieser Festlegung:**
> 1. **Stabile Lösbarkeit:** Bei 16 entlasteten Nächten (bei 5 TÄ) bleiben genau 75 Nächte im Dienstpool. Die Intern-Pflichtquote (24–36 Nächte) und die TFA-Mindestteilnahme nach H22 (alle ~20 nachtfähigen TFAs) kommen sich mathematisch nicht in die Quere.
> 2. **Akzeptanz bei Tierärzten:** 2 Nächte am Stück sind im klinischen Alltag deutlich verträglicher als 3 aufeinanderfolgende Nächte.
> 3. **Lückenlose Wochenmitte:** Die verbleibende 3. Nacht (Donnerstag) schließt für TFAs/Interns direkt an Freitag an (`N_Do-Fr + N_Fr-Sa`), womit die Mindestblocklänge von 2 Nächten gewahrt bleibt.

---

## 6. UI-, Validierungs-, Machbarkeits- & Export-Anpassungen

### 6.1 Kapazitätsanalyse (`app/scheduler/feasibility.py`)
- In `analyze_capacity()`:
  - `non_azubi_nd` wird auf `[s for s in staff_list if s.nd_possible and s.beruf in (Beruf.TFA, Beruf.INTERN)]` eingeschränkt, damit Tierärzte nicht fälschlicherweise mit dem 21-Tage-Rhythmus in Check A und Check B gezählt werden.
  - Neuer **Check F (`Tierarzt-Nachtdienst-Entlastung`)**: Sofern Tierärzte (`Beruf.VET`) in `staff_list` vorhanden sind, wird deren Anzahl und die unter der 2-Monats-Regel maximal möglichen 2-Nächte-Blöcke (bis zu 2 Blöcke = 4 Nächte pro TA im Quartal, abzgl. Urlaub/Vorquartals-Sperre) ausgewiesen und vom geschlossenen Nachtbedarf in Check A abgezogen.

### 6.2 UI (`app/streamlit_app.py`)
1. **Personalansicht (`page_personal`):**
   - `Beruf.VET` ist automatisch im Rollen-Filter (`[b.value for b in Beruf]`) enthalten.
   - Erweiterung der Statistik-Leiste um eine Metrik-Spalte für `Vet` (Tierärzte).
2. **Planerstellung (`page_plan_erstellen`):**
   - Die **Kapazitätsanalyse** (`analyze_capacity`) zeigt vor Solve-Start automatisch Check F (Anzahl verfügbarer Tierärzte und resultierende Entlastungs-Blöcke) an.
3. **Plananzeige (`page_plan_anzeigen`):**
   - **Tab Kalender (`tab_calendar`):** In der Spalte `🌙 Nacht` erhalten Tierarzt-Zuweisungen das Präfix `🩺 [TA] ` vor dem Kürzel/Namen.
   - **Tab Fairness & Statistik (`tab_stats`):**
     - Eigene Sektion `##### 🩺 Tierärzte (Entlastung Di–Do)` mit Anzeige von Name, Kürzel, Urlaub, Anzahl 2-Nächte-Blöcke und Gesamtnächten (ohne Division durch `Std. = 0`).
     - Ausschluss von `Beruf.VET` aus der stundenbasierten `Proportionale Abweichung`-Tabelle im Score-Breakdown.
   - **Tab Validierung (`tab_validation`):** Aufnahme von `"Vet Shift Constraint": "Tierarzt-Regeln (nur Di-Do, 2er-Block, Alleindienst, 1x/2 Monate)"` in `known_constraints`.
4. **Excel-Export (`page_export`):**
   - Tierarzt-Einsätze sind reguläre `Assignment`-Einträge auf `N_Di-Mi`, `N_Mi-Do`, `N_Do-Fr` mit `is_paired = False` (`Paarweise = "Nein"`) und werden automatisch in das Blatt `Nachtdienste` exportiert und beim Re-Import (`parse_previous_plan_xlsx`) für den Quartalsübergang (H-TA-4) erkannt.

### 6.3 Validierung (`app/scheduler/validator.py`)
Erweiterung von `validate_schedule` um `_check_vet_shift_constraints(schedule, staff_dict)`:
- Prüft für alle Zuweisungen von Mitarbeitern mit `staff.beruf == Beruf.VET`:
  - **Schichttyp:** Nur `N_Di-Mi`, `N_Mi-Do`, `N_Do-Fr` zulässig (wird zusätzlich durch `_check_shift_eligibility` abgedeckt).
  - **Exakter 2-Nächte-Block:** Jeder zusammenhängende Nachtblock eines Tierarztes muss die Länge `len(block) == 2` haben (weder 1 Nacht noch $\ge 3$ Nächte).
  - **Alleindienst:** An einer Nacht mit Tierarzt-Beteiligung muss `len(shift_assignments) == 1` gelten (keine Begleitperson).
  - **2-Monats-Regel (Kalendermonat):** Kein Tierarzt darf in zwei aufeinanderfolgenden Kalendermonaten $(m, m+1)$ mehr als 1 Block beginnen.

---

## 7. Nicht-funktionale Anforderungen & Qualitätssicherung

1. **Typsicherheit & Linting:** Strikte Typisierung mit `mypy`, Formatierung nach PEP 8 via `ruff`.
2. **Tests (`tests/test_vet_scheduling.py`):**
   - Testet 2-Nächte-Blockbildung (weder 1 Nacht noch 3 Nächte zulässig).
   - Testet Alleindienst-Erzwingung (Kopfzahl = 1).
   - Testet Kalendermonats-Sperre (1x alle 2 Monate) und Vorquartals-Übergang.
   - Testet automatische Ausweichlogik auf TFAs in Wochen ohne TA.
3. **Performance:** Schnelle CP-SAT-Konvergenz durch enge Blockkopplung.
