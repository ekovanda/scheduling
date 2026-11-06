# Product Requirements Document (PRD)
# Cloud Run Deployment & Frontend Modernization Roadmap
## Transforming the Dienstplan Generator into a Unified Single Source of Truth (SSOT)

**Feature Name / Slug**: `gcp-cloud-run-migration-and-modernization`  
**Document Version**: 1.3 (Updated: Cloud Firestore SSOT Persistence & Asynchronous Solver Architecture)  
**Status**: Approved & In Progress (Phase 1 Deployed; Phase 2 Active Development)  
**Target Architecture**: GCP Cloud Run (Containerized Backend) + GCP Cloud Firestore (Serverless Document Database with Local JSON Fallback) + Modern React/Tailwind Frontend (Firebase Hosting)  
**Author**: Antigravity / Senior Cloud & Full-Stack Architect  

---

## 1. Executive Summary & Business Drivers

### 1.1 Motivation & Context
The **Dienstplan Generator** is currently written in Streamlit and deployed on Streamlit Community Cloud. While it successfully solves the complex mathematical optimization problem of fair quarterly emergency and night shifts using OR-Tools CP-SAT, its current operational workflow is that of a **"stateless calculator"**. 

This operational model suffers from two major categories of friction:

#### A. Cloud Infrastructure & Privacy Risks
1. **Repository Privacy & Data Sensitivity**: Streamlit Community Cloud enforces public repositories for free tier hosting. Even with sample data, hosting clinical shift scheduling logic, employee names, initials, and operational constraints in a public repository is unacceptable from an IP and data protection perspective. Migrating to Google Cloud Platform (GCP) allows keeping the source code and clinic data in a private repository and private container registry.
2. **Volatile Execution Environment**: Streamlit relies purely on in-memory `st.session_state`. When a browser tab is refreshed, or when the container sleeps/reboots, all in-session inputs (uploaded staff lists, vacations, trailing quarter contexts, and generated schedules) are lost.
3. **Compute & Solver Constraints**: The CP-SAT constraint programming solver (`ortools`) is CPU- and memory-intensive (runs typically 60–120 seconds). Running this inside a lightweight shared multi-tenant environment risks throttling, memory kills, or WebSocket disconnection.

#### B. Workflow Fragmentation & The "Excel Hell" Problem
Currently, the quarterly scheduling workflow requires extensive manual work **outside** the application:
1. **Disconnected Employee Rosters**: Planners maintain local `staff.csv` or `staff.xlsx` files. Updates to employee hours, new hires (`available_from`), departures, or qualification changes happen in local spreadsheets and must be re-uploaded every session.
2. **Disconnected Vacation Calendars**: Vacations are tracked separately in `vacations.xlsx` and manually fed into the app per quarter.
3. **Local Editing of the "Realized Schedule" (Ist-Plan)**: After the solver creates a plan and it is exported to Excel (`Dienstplan_2026_Q1.xlsx`), clinical reality intervenes during the quarter (sick leave, emergency shift swaps, staff departures). Planners currently edit these changes locally in Excel.
4. **Manual Cross-Quarter Bridging**: When planning the next quarter (e.g. Q2), the planner must remember to upload the manually edited *Arbeitseinsätze* Excel file from Q1 as the "Context File" (`build_previous_context_from_xlsx`). If this file is missing, formatted incorrectly, or outdated, **the 21-day rest constraint across the quarter boundary and the FTE carry-forward fairness deltas are completely lost**.

### 1.2 The Vision: A Single Source of Truth (SSOT)
The objective is to evolve the Dienstplan Generator from a stateless calculation tool into an **all-in-one cloud scheduling platform** for the clinic planning team:
- **Zero local spreadsheet dependencies** for recurring operations (Excel becomes an optional export format, not a storage medium).
- **In-app Master Staff Management** (hire dates, hours adjustments, roles, exceptions).
- **In-app Continuous Vacation & Absence Calendar**.
- **In-app Shift Swap & Sickness Tracking ("Soll vs. Ist")** during the active quarter.
- **Automated 1-Click Quarter Roll-Over**: When starting Q2, the system automatically pulls the locked realized shifts and trailing 21 days from Q1 to enforce boundary constraints and carry-forward fairness without any manual file juggling.

---

## 2. Complete Schedule Lifecycle Architecture

The following diagram illustrates how the target platform replaces external file hand-offs with an end-to-end cloud lifecycle:

```mermaid
flowchart TD
    subgraph MasterData["1. Master Data Management (In-App)"]
        StaffDir["Master Staff Directory\n(Hours, Roles, Exceptions, Available_From)"]
        AbsenceLedger["Continuous Absence Calendar\n(Vacations, Sick Leave, Training)"]
    end

    subgraph PlanningPhase["2. Quarterly Planning & Optimization"]
        QuarterInit["Initialize Quarter (e.g. 2026-Q2)"]
        AutoContext["Automated Roll-Over Engine\n(Pulls Trailing 21 Days + Carry-Forward Deltas)"]
        SolverEngine["OR-Tools CP-SAT Solver Job\n(app/scheduler/solver_cpsat.py)"]
        DraftView["Interactive Schedule Matrix\n(Draft Mode + Live Rule Validator)"]
    end

    subgraph OperationalPhase["3. Live Quarter Operations (Soll vs. Ist)"]
        PublishPlan["Publish Official Schedule (Soll-Plan)"]
        LiveTracking["In-App Shift Swaps & Sick Replacements\n(Realized / Ist-Plan Tracking)"]
        AuditLog["Audit Trail & Shift History"]
    end

    subgraph RollOver["4. Continuous Quarter Transition"]
        LockQuarter["Lock Quarter (Final Realized State)"]
    end

    StaffDir & AbsenceLedger --> QuarterInit
    QuarterInit --> AutoContext
    AutoContext --> SolverEngine
    SolverEngine --> DraftView
    DraftView -->|Approve| PublishPlan
    PublishPlan --> LiveTracking
    LiveTracking --> AuditLog
    LiveTracking --> LockQuarter
    LockQuarter -->|Auto-Feeds Next Quarter Context| AutoContext
```

### 2.1 Workflow Comparison: Today vs. Target SSOT Platform

| Step | Current Workflow (External Files) | Target SSOT Platform (In-App) |
|:---|:---|:---|
| **Staff Management** | Edit local `staff.csv`, upload per session | In-app Employee Management UI; changes persist automatically |
| **Vacation Tracking** | Edit local `vacations.xlsx`, upload per session | In-app Vacation Calendar; recurring & future leaves pre-stored |
| **Schedule Generation** | Streamlit button, browser blocks during solve | Asynchronous Background Solver Job (`POST /quarters/{key}/generate` returns `202 Accepted` with `job_id`; frontend polls status or receives updates; background thread with `--no-cpu-throttling` withstanding 10-minute solves) |
| **Manual Adjustments** | Export to Excel or use clumsy Streamlit widgets | Interactive React grid with drag-and-drop & live constraint feedback |
| **Quarter Operations** | Planners edit exported Excel file on desktop when shifts swap or sick leave occurs | Planners log swaps and sick replacements directly in the live schedule matrix |
| **Quarter Roll-Over** | Manually upload Q1 *Arbeitseinsätze* Excel into Q2 Streamlit session | 1-Click Roll-Over: system automatically reads Q1 realized shifts, builds `PreviousPlanContext`, and initializes Q2 |
| **Excel Role** | Primary storage & communication medium | Read-only export for noticeboard printouts and external archiving |

---

## 3. Phased Implementation Strategy

To protect ongoing clinical operations and avoid disruption, the transition remains structured in three safe phases:

```mermaid
flowchart LR
    subgraph Phase1["Phase 1: Lift & Shift (Complete / In Production)"]
        direction TB
        A1["Dockerize Streamlit App"] --> A2["Deploy to Private GCP Cloud Run"]
        A2 --> A3["Secure via Private Repo & Secrets Manager"]
        A3 --> A4["Verified identical parity with Streamlit Cloud"]
    end

    subgraph Phase2["Phase 2: Decoupled API & Cloud Firestore SSOT Backend (Active)"]
        direction TB
        B1["Expose FastAPI REST Service on Cloud Run"] --> B2["Pure Python app/scheduler intact"]
        B2 --> B3["Asynchronous Solver API (POST 202 + /solver-status)"]
        B3 --> B4["Persist in Cloud Firestore (Local JSON Fallback)"]
        B4 --> B5["Automated Roll-Over Engine (build_previous_context)"]
    end

    subgraph Phase3["Phase 3: React SSOT Frontend"]
        direction TB
        C1["React 19 + Vite + Tailwind CSS"] --> C2["Deploy to Firebase Hosting / Cloud CDN"]
        C2 --> C3["Staff Directory & Vacation Calendar Views"]
        C3 --> C4["Interactive Schedule Matrix (Draft + Live Ist-Plan)"]
        C4 --> C5["Shift Swap & Replacement Modal with Live Validation"]
    end

    Phase1 --> Phase2 --> Phase3
```

- **Phase 1** has been successfully executed, deploying the existing Streamlit app to private Cloud Run with zero disruption to active scheduling.
- **Phase 2** builds the headless FastAPI layer, persistence store, automated roll-over logic, and an asynchronous in-process solver runner. While maintaining "Flat & Simple" architecture (avoiding heavy external Redis/Celery brokers), Phase 2 addresses the operational reality that clinical optimization requires up to 600s (10-minute) "Gründlich" solves. Because Firebase Hosting enforces a hard 60s CDN connection timeout and Cloud Run defaults to 300s, Phase 2 implements a lightweight in-process background task with non-blocking status polling (`POST /generate` returns `202 Accepted` + `job_id`, `GET /solver-status`), backed by Cloud Run's `--no-cpu-throttling` flag.
- **Phase 3** replaces Streamlit with the full single-source-of-truth React UI.
- **Parallel Deployment Model**: All Phase 2 and Phase 3 deployments target a separate Cloud Run service (`dienstplan-dev`) configured with `min-instances=0` ($0 idle cost), ensuring production (`dienstplan-app`) remains completely insulated from downtime or breaking changes.

---

## 4. Phase 1: Containerized Streamlit on GCP Cloud Run

### 4.1 Objectives
- Deploy the existing Streamlit app inside a secure, private GCP project.
- Host source code in a private GitHub repository; store containers in GCP Artifact Registry.
- Guarantee 100% feature parity with zero user disruption.

### 4.2 Cloud Run Service Specification
| Parameter | Specification | Rational / Justification |
|:---|:---|:---|
| **Service Name** | `dienstplan-app` | Primary scheduling service |
| **Region** | `europe-west3` (Frankfurt) or `europe-west1` (Belgium) | Low latency, strict EU GDPR compliance |
| **CPU Allocation & Throttling** | 2 vCPU, Always Allocated (`--no-cpu-throttling`) | Dedicated CPU cores for OR-Tools CP-SAT; `--no-cpu-throttling` is mandatory so background solver threads continue running after HTTP 202 is returned |
| **Memory** | 4 GiB | Headroom for deep CP-SAT branch-and-bound search trees, preventing OOM kills (exit 137) during 10-minute solves |
| **Execution Environment** | Second Generation (`gen2`) | Full Linux syscall and memory bandwidth compatibility |
| **Request Timeout** | 900 seconds (15 min) | Generous container lifetime accommodating long solves up to 10 minutes |
| **Concurrency** | 2 | Limits concurrent compute jobs per container, preventing CPU starvation and heartbeat drops |
| **Session Affinity** | Enabled (`--session-affinity`) | Critical for Streamlit WebSockets across client reconnects |
| **Min Instances** | 0 (cost-effective) or 1 (instant) | Min 0 scales to zero when idle; Min 1 eliminates cold-start latency |
| **Max Instances** | 3 | Prevents accidental cost runaway |

### 4.3 Container Hardening (`Dockerfile` Updates)
The updated `Dockerfile` for Phase 1 must support:
- Dynamic `$PORT` binding provided by Cloud Run with fallback to `8080`.
- Streamlit production flags (`--server.enableCORS=false`, `--server.headless=true`).
- Installing all required dependencies (`matplotlib`, `ortools`, `xlsxwriter`, `pandas`, `openpyxl`, `pydantic`).

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Prevent Python from writing .pyc and buffer output for Cloud Logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# Install dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir \
    streamlit>=1.30.0 \
    pandas>=2.1.0 \
    openpyxl>=3.1.0 \
    pydantic>=2.5.0 \
    python-dateutil>=2.8.0 \
    xlsxwriter>=3.0.0 \
    matplotlib>=3.8.0 \
    ortools>=9.15.6755

# Copy application source
COPY app/ ./app/

# Create data directory if not present
RUN mkdir -p /app/data

EXPOSE 8080

# Run Streamlit bound to Cloud Run dynamic $PORT
CMD ["sh", "-c", "streamlit run app/streamlit_app.py --server.port=${PORT} --server.address=0.0.0.0 --server.enableCORS=false --server.headless=true"]
```

### 4.4 Dual-Environment Cloud Run Strategy (Zero-Risk Parallel Deployments)
To enable active development and validation without risking production downtime or breaking changes to active scheduling sessions, the infrastructure uses two distinct Cloud Run services:
1. **Production Service (`dienstplan-app`)**:
   - Deployed from `main` branch.
   - Hosts the stable, user-facing scheduling application.
   - Min instances: 0 (or 1 during high-volume planning quarters).
2. **Preview / Development Service (`dienstplan-dev`)**:
   - Deployed from feature/modernization branches (`feat/gcp-modernization-redesign`).
   - Hosts experimental API routes, persistence layers, and preview frontends.
   - Min instances: 0 ($0 cost when idle).
   - Completely independent Cloud Run URL and configuration (`SERVICE_NAME="dienstplan-dev"`).

---

## 5. Phase 2: Decoupled API, Persistent Data Models & SSOT Engine

### 5.1 Objectives
- Expose a clean FastAPI REST backend wrapping [`app/scheduler/`](file:///home/e/Desktop/antigravity-projects/scheduling/app/scheduler/).
- **Asynchronous In-Process Solver Execution**: Runs OR-Tools CP-SAT via lightweight background thread returning `202 Accepted` to bypass Firebase Hosting 60s CDN timeout and withstand 10-minute long-solves.
- **Multi-Planner Cloud Persistence**: Google Cloud Firestore as the single source of truth for multi-user, multi-week collaboration without file collisions, backed by local JSON file fallback for offline test suites.
- Eliminate all manual file upload/download steps for inter-quarter scheduling.
- Implement an **Automated Roll-Over Engine** that auto-computes `PreviousPlanContext` directly from database records.

### 5.2 Core Data Models for Persistence

#### A. Master Staff Entity
```python
class StaffMember(BaseModel):
    id: str                        # Unique UUID or acronym (e.g. "STAFF_01")
    identifier: str                # 2-4 letter clinic acronym (e.g. "MUE")
    name: str                      # Full display name
    beruf: Beruf                   # TFA, AZUBI, INTERN, VET
    abteilung: Abteilung           # STATION, OP, OTHER
    hours: float                   # Weekly contracted hours (e.g. 40.0, 20.0)
    adult: bool = True
    reception: bool = False
    nd_possible: bool = True
    nd_alone: bool = True
    nd_min_consecutive: int = 2
    nd_max_consecutive: int | None = None
    nd_exceptions: list[int] = []  # Weekday blocks [0..6]
    birthday: str | None = None    # "MM-DD"
    available_from: date | None = None
    is_active: bool = True         # False if employee has left clinic
    created_at: datetime
    updated_at: datetime
```

#### B. Continuous Absence & Vacation Entity
```python
class AbsenceType(str, Enum):
    VACATION = "Vacation"
    SICK_LEAVE = "SickLeave"
    SPECIAL_LEAVE = "SpecialLeave"
    TRAINING = "Training"

class AbsenceRecord(BaseModel):
    id: str
    staff_id: str
    absence_type: AbsenceType
    start_date: date
    end_date: date
    note: str | None = None
```

#### C. Quarter Schedule & Realized Shift Lifecycle
```python
class ScheduleState(str, Enum):
    DRAFT = "DRAFT"               # Candidate plan being adjusted by planner
    PUBLISHED = "PUBLISHED"       # Official plan released to staff (Soll-Plan)
    ACTIVE = "ACTIVE"             # Currently ongoing quarter (accepting realized swaps)
    CLOSED = "CLOSED"             # Quarter concluded; locked for historical continuity

class ShiftAssignment(BaseModel):
    shift_date: date
    shift_type: ShiftType
    planned_staff_id: str         # Staff member originally assigned by solver/planner
    actual_staff_id: str          # Staff member who actually worked the shift
    is_paired: bool
    is_override: bool = False     # True if manually swapped/reassigned
    override_reason: str | None = None  # e.g. "Krankheitsvertretung", "Diensttausch"
    override_timestamp: datetime | None = None

class QuarterScheduleDocument(BaseModel):
    quarter_key: str              # e.g. "2026-Q2"
    year: int
    quarter: int
    state: ScheduleState
    config: SchedulerConfig
    assignments: list[ShiftAssignment]
    solver_metrics: dict          # Objective value, fairness deviation, solve time
    carry_forward_applied: list[CarryForwardEntry]
    trailing_applied: list[TrailingAssignment]
    created_at: datetime
    updated_at: datetime
```

### 5.3 Automated Roll-Over Engine Specification
In the current Streamlit app, cross-quarter bridging is handled by `build_previous_context_from_xlsx`. In the SSOT platform, this becomes an automated background method:

```python
def get_previous_quarter_context(target_year: int, target_quarter: int) -> PreviousPlanContext | None:
    """Auto-computes PreviousPlanContext from the preceding quarter document in database."""
    prev_year, prev_quarter = compute_preceding_quarter(target_year, target_quarter)
    prev_doc = datastore.get_schedule(f"{prev_year}-Q{prev_quarter}")
    
    if not prev_doc or prev_doc.state not in [ScheduleState.ACTIVE, ScheduleState.CLOSED, ScheduleState.PUBLISHED]:
        return None  # First quarter setup without historical context

    # Construct Schedule object using actual_staff_id (the REALIZED shift schedule)
    realized_schedule = Schedule(
        quarter_start=date(prev_year, (prev_quarter - 1) * 3 + 1, 1),
        assignments=[
            Assignment(
                shift=Shift(shift_type=a.shift_type, shift_date=a.shift_date),
                staff_identifier=a.actual_staff_id,
                is_paired=a.is_paired
            ) for a in prev_doc.assignments
        ]
    )
    
    active_staff = datastore.list_active_staff()
    # Call battle-tested core scheduling function directly:
    return build_previous_context(schedule=realized_schedule, staff_list=active_staff, trailing_days=21)
```

> [!IMPORTANT]
> The automated roll-over uses `actual_staff_id` (the realized shifts worked), ensuring that sick leaves or manual swaps that occurred in late March are automatically respected as rest-period constraints in early April!

### 5.4 REST API Endpoints Specification
| Method | Path | Description |
|:---|:---|:---|
| `GET` / `POST` | `/api/v1/staff` | List active staff or create a new employee |
| `GET` / `PUT` / `DELETE` | `/api/v1/staff/{staff_id}` | Retrieve, update or deactivate staff member |
| `POST` | `/api/v1/staff/bulk-import` | Optional one-time onboarding from `staff.xlsx` / `.csv` |
| `GET` / `POST` | `/api/v1/absences` | Query or record vacations and sick leaves across any date range |
| `GET` | `/api/v1/quarters/{quarter_key}` | Retrieve quarter schedule document, status, and metrics |
| `POST` | `/api/v1/quarters/{quarter_key}/init` | 1-Click Init: auto-detects preceding quarter, computes roll-over context |
| `POST` | `/api/v1/quarters/{quarter_key}/generate` | Launch async background CP-SAT solve; returns `202 Accepted` with `{job_id, status: "RUNNING", started_at, max_solve_time_seconds}` |
| `GET` | `/api/v1/quarters/{quarter_key}/solver-status` | Poll live solver progress (`IDLE`, `RUNNING`, `COMPLETED`, `FAILED`), elapsed seconds, latest objective score, and soft penalty |
| `POST` | `/api/v1/quarters/{quarter_key}/cancel` | Gracefully interrupt / cancel an active CP-SAT search |
| `POST` | `/api/v1/quarters/{quarter_key}/shifts/swap` | Swap or reassign a shift with instant live constraint validation |
| `POST` | `/api/v1/quarters/{quarter_key}/publish` | Move state from `DRAFT` to `PUBLISHED` |
| `POST` | `/api/v1/quarters/{quarter_key}/lock` | Lock quarter into `CLOSED` state for permanent record |
| `GET` | `/api/v1/quarters/{quarter_key}/export` | 1-Click download of styled Excel (.xlsx) or CSV for noticeboard/staff |

### 5.5 Asynchronous Solver Job Architecture & Long-Solve Resiliency

Stakeholder testing on Cloud Run revealed that synchronous HTTP solver execution breaks under real-world clinical optimization workloads. This section specifies the resilient, asynchronous solver pattern engineered specifically to overcome reverse proxy and serverless compute boundaries.

#### 5.5.1 Root Cause Analysis: The Synchronous Solver Failure Modes
1. **Firebase Hosting CDN Reverse Proxy 60s Timeout**:
   - When requests route through Firebase Hosting rewrites (`firebase.json` $\rightarrow$ Cloud Run), Google's edge CDN imposes a hard **60-second connection timeout**.
   - Any synchronous HTTP call taking longer than 60s triggers an immediate `504 Gateway Timeout` at the edge, even if the backend Cloud Run container is still running.
2. **Cloud Run 300s Default Request Timeout**:
   - The "Gründlich" deep optimization requires **600 seconds (10 minutes)** to prove optimality across complex constraint interactions (open/closed nights, intern weekend coupling, vet midweek blocks, cross-quarter boundaries).
   - Cloud Run's default `--timeout=300s` forcefully terminates any active HTTP connection at the 5-minute mark, dropping the connection and rebooting or resetting the request.
3. **Cloud Run Default CPU Throttling (`--cpu-throttling`)**:
   - By default, Cloud Run drastically throttles container CPU down to near zero outside active HTTP request processing windows.
   - If an async background task is spawned without `--no-cpu-throttling`, the background solver thread freezes as soon as the HTTP `202 Accepted` response completes.
4. **ASGI Web Worker Starvation**:
   - OR-Tools CP-SAT is a CPU-intensive C++ multi-threaded engine. Executing it synchronously on the web worker thread pool starves Uvicorn/FastAPI from serving container health check probes (`/_stcore/health` or `/healthz`), causing Cloud Run to declare the container unhealthy and kill it.

#### 5.5.2 "Flat & Simple" In-Process Job Architecture
Rather than introducing heavy, expensive distributed message brokers (such as Celery, RabbitMQ, or Redis), Phase 2 implements a lightweight in-process asynchronous runner:

```mermaid
sequenceDiagram
    autonumber
    actor Planner as Clinic Planner (React UI)
    participant CDN as Firebase Hosting CDN
    participant API as FastAPI Backend (Cloud Run)
    participant Worker as Background Solver Thread
    participant CPSAT as OR-Tools CP-SAT
    participant DB as JSON / Firestore Store

    Planner->>CDN: POST /api/v1/quarters/2026-Q2/generate (max=600s)
    CDN->>API: Forward HTTP POST
    API->>Worker: Spawn Solver Thread (job_id, quarter_key)
    Worker->>CPSAT: Launch cp_model.CpSolver.Solve()
    API-->>CDN: 202 Accepted {job_id, status: "RUNNING"} (<50ms)
    CDN-->>Planner: Immediate Response (bypasses 60s CDN timeout)

    loop Every 2 Seconds
        Planner->>API: GET /api/v1/quarters/2026-Q2/solver-status
        API-->>Planner: 200 OK {status: "RUNNING", elapsed: 42s, solutions: 5}
    end

    CPSAT-->>Worker: Solve Finished (status: OPTIMAL / FEASIBLE)
    Worker->>DB: Persist Candidate Schedule Draft & Solver Metrics
    Worker-->>Worker: Update Job Registry (status: "COMPLETED")

    Planner->>API: GET /api/v1/quarters/2026-Q2/solver-status
    API-->>Planner: 200 OK {status: "COMPLETED", best_schedule_id}
    Planner->>API: GET /api/v1/quarters/2026-Q2
    API-->>Planner: Load Generated Matrix Draft
```

#### 5.5.3 Cloud Run Production Configuration Directives
To guarantee 10-minute long-solves run without interruption:
* **`--no-cpu-throttling` (MANDATORY)**: Guarantees 100% CPU allocation to the container even when no HTTP request is actively in flight, allowing the background solver thread to run at full speed.
* **`--timeout=900s`**: Sets the Cloud Run service timeout to 15 minutes, accommodating 600s solves plus model generation, validation, and persistence overhead.
* **`--memory=4Gi`**: Allocates 4 GiB memory to prevent Linux OOM kills (exit code 137) during deep branch-and-bound exploration.
* **`--concurrency=2`**: Constrains concurrent requests per solver-bearing container to prevent CPU thrashing.

#### 5.5.4 API Contract & Cancellation
* **`POST /api/v1/quarters/{quarter_key}/generate`**:
  - Request: `{"max_solve_time_seconds": 600, "random_seed": 42, "include_previous_context": true}`
  - Response (`202 Accepted`):
    ```json
    {
      "job_id": "job_2026_q2_solve_a8f9",
      "quarter_key": "2026-Q2",
      "status": "RUNNING",
      "started_at": "2026-11-06T12:00:00Z",
      "max_solve_time_seconds": 600
    }
    ```
* **`GET /api/v1/quarters/{quarter_key}/solver-status`**:
  - Response (`200 OK`):
    ```json
    {
      "job_id": "job_2026_q2_solve_a8f9",
      "quarter_key": "2026-Q2",
      "status": "RUNNING",
      "elapsed_seconds": 124.5,
      "solutions_found": 12,
      "best_objective": 8420.0,
      "soft_penalty": 150.0,
      "error": null
    }
    ```
* **`POST /api/v1/quarters/{quarter_key}/cancel`**:
  - Sets atomic cancellation flag on solver progress callback (`stop_search()`), aborting computation gracefully within milliseconds.

#### 5.5.5 Frontend User Experience (Phase 3 Integration)
* **Non-Blocking Execution**: Launching a solve opens a modal with a live timer, solution quality trajectory, and cancel button.
* **Navigation Freedom**: Planners can close the modal and browse "Mitarbeiter" or "Abwesenheiten" while the solve proceeds in the background. A navbar indicator (`⏳ Berechnung läuft: 03:15`) maintains live context.
* **Toast & Matrix Auto-Refresh**: When the polling hook detects `"COMPLETED"`, a toast notification alerts the planner and the Dienstplan matrix seamlessly re-renders with the newly created candidate draft.

### 5.6 Multi-Planner Persistence: Cloud Firestore Architecture & Dual-Driver Pattern

To ensure the application serves as the durable Single Source of Truth (SSOT) for multiple clinic planners collaborating over multiple weeks, the persistence architecture implements **Google Cloud Firestore** with a local file fallback.

#### 5.6.1 Motivation & Multi-User Requirements
1. **Survivability Across Ephemeral Container Lifecycles**: Cloud Run container instances are stateless and scale to zero during idle periods. Storing records solely on the container filesystem means state is wiped upon instance cycling or restarts.
2. **Multi-Planner Concurrency & Conflict Prevention**: Multiple planners (clinic leadership, head veterinarians, lead TFAs) frequently adjust staff hours, vacation requests, and shift assignments concurrently. Document-level datastore operations prevent silent overwrite collisions (where the last file write overwrites concurrent edits).
3. **Sub-10ms Indexed Range Queries**: Querying absences across a quarterly boundary (e.g. all leaves overlapping Q2) performs an indexed query on Firestore rather than scanning and parsing dozens of individual JSON files on disk.

#### 5.6.2 Firestore Data Collections Specification

```mermaid
erDiagram
    STAFF ||--o{ ABSENCES : "has"
    SCHEDULES ||--o{ SHIFTS : "contains"
    SCHEDULES ||--o| SOLVER_JOBS : "tracks"

    STAFF {
        string id PK "Unique ID / Acronym (e.g. MUE)"
        string identifier "Clinic Acronym"
        string name "Display Name"
        string beruf "VET, TFA, AZUBI, INTERN"
        string abteilung "STATION, OP, OTHER"
        float hours "Weekly contract hours"
        boolean is_active "Active flag"
        timestamp updated_at "Last modified"
    }

    ABSENCES {
        string id PK "UUID / abs-seed-xx"
        string staff_id FK "Staff Member Reference"
        string absence_type "Vacation, SickLeave, Training"
        date start_date "Start of absence"
        date end_date "End of absence"
        string note "Optional remark"
    }

    SCHEDULES {
        string quarter_key PK "e.g. 2026-Q2"
        int year "2026"
        int quarter "2"
        string state "DRAFT, PUBLISHED, ACTIVE, CLOSED"
        array assignments "Shift assignment objects"
        map solver_metrics "Penalty, solve time, candidates"
        timestamp updated_at "Last modified"
    }

    SOLVER_JOBS {
        string quarter_key PK "e.g. 2026-Q2"
        string job_id "Unique solve job ID"
        string status "IDLE, RUNNING, COMPLETED, FAILED"
        timestamp started_at "Solve start timestamp"
        float elapsed_seconds "Live timer"
        float best_objective "Best score found"
        float soft_penalty "Constraint penalty"
        string error "Error message if failed"
    }
```

* **`staff` Collection**: Keyed by `id` (e.g., `MUE`). Stores current master employee contracts, role definitions, and weekend/night preferences.
* **`absences` Collection**: Keyed by `id`. Stores continuous vacation, sickness, and training intervals with indexed `[start_date, end_date]` fields.
* **`schedules` Collection**: Keyed by `quarter_key` (e.g., `2026-Q2`). Stores full quarterly documents, shift assignments, and roll-over metadata.
* **`solver_jobs` Collection**: Keyed by `quarter_key`. Tracks background solver execution status, supporting durable progress polling across multiple user browser tabs and container instances.

#### 5.6.3 The Dual-Driver Architecture (Local Dev + Cloud Production)
To preserve ultra-fast local testing without requiring cloud credentials or incurring network latency during offline development, the backend follows the **Dual-Driver Repository Pattern**:

```mermaid
flowchart TD
    API["FastAPI Endpoints (app/api/v1/)"] --> Protocol["Repository Protocols\n(Staff, Absence, Schedule, Job)"]
    Protocol --> Router{"STORAGE_BACKEND"}
    Router -->|file (Default for Local/Tests)| FileRepo["FileJsonRepository\n(Atomic writes to data/db/*.json)"]
    Router -->|firestore (Cloud Run Production)| FirestoreRepo["FirestoreRepository\n(Google Cloud Firestore europe-west3)"]
```

* **Configuration**: Controlled by environment variable `STORAGE_BACKEND=firestore` (in Cloud Run) and `STORAGE_BACKEND=file` (local default).
* **Test Isolation**: All 150+ pytest test suites run against `FileJsonRepository` with isolated temporary directories in ~4 seconds, maintaining zero external dependencies for routine CI/CD.
* **Zero Cost**: Google Cloud Free Tier provides 50,000 document reads and 20,000 writes per day. With clinic usage typically under 500 operations per day, production database cost is **$0.00 / month**.
* **GDPR & Regional Compliance**: Hosted in `europe-west3` (Frankfurt) within the same VPC/region as Cloud Run for sub-5ms internal latency and strict German medical data protection compliance.

---

## 6. Phase 3: Modern React Single Source of Truth Frontend

### 6.1 Objectives
- Provide a responsive, high-performance web UI eliminating all desktop spreadsheet manipulation.
- Integrate interactive schedule editing with instant constraint feedback.
- Deliver an intuitive 5-view architecture designed for clinical workflows.
- Prioritize visual clarity over statistical complexity for clinic stakeholders.

### 6.2 Key User Interface Views

```
┌────────────────────────────────────────────────────────────────────────┐
│  🏥 TIERKLINIK DIENSTPLAN   [2026-Q2 ▼]                                 │
│  [Mitarbeiter] [Abwesenheiten] [Dienstplan Matrix] [Fairness] [Über]   │
├────────────────────────────────────────────────────────────────────────┤
│  Status: 🟢 AKTIV (IST-STAND)       [Dienst tauschen]  [Excel Export]  │
│                                                                        │
│  APRIL 2026                                                            │
│  ┌────────────┬────────────────────────────┬─────────────────────────┐ │
│  │ Datum      │ Notdienst (Nacht)          │ Wochenende (Tag)        │ │
│  ├────────────┼────────────────────────────┼─────────────────────────┤ │
│  │ Mi 01.04   │ 👤 Vet: Dr. Müller         │ —                       │ │
│  │ Do 02.04   │ 👤 Vet: Dr. Müller         │ —                       │ │
│  │ Fr 03.04   │ 👤 TFA: Schmidt, K.        │ —                       │ │
│  │            │ 👤 Azubi: Bauer, L.        │                         │ │
│  │ Sa 04.04   │ 👤 TFA: Schmidt, K.        │ 👤 TFA: Weber, M.       │ │
│  │            │ 👤 Azubi: Bauer, L.        │ 👤 Intern: Dr. Koch     │ │
│  │            │ ⚠️ [Tausch: Bauer ➔ Klein] │                         │ │
│  └────────────┴────────────────────────────┴─────────────────────────┘ │
└────────────────────────────────────────────────────────────────────────┘
```

1. **Staff Directory Hub (Pilot Design Anchor)**:
   - Filterable table of clinic employees with clear role badges (`Tierarzt`, `TFA`, `Azubi`, `Intern`).
   - Summary metric cards (Active Staff, Total Weekly Contract Hours, On-Call Eligibility).
   - Modal to add/edit contract hours, roles, department locks, and night availability.
   - Deactivate departing staff or set availability dates.
2. **Interactive Absence & Vacation Planner**:
   - Visual team calendar and ledger showing who is away when (Urlaub, Fortbildung, Krank).
   - Quick-entry date range form with live validation.
   - Immediate warning if an absence creates an impossible weekend or night coverage shortage.
3. **Interactive Schedule Matrix & Operations (Hero View)**:
   - Header with quarter status banner (`DRAFT` / `PUBLISHED` / `LOCKED`), 1-click solve trigger with asynchronous live progress modal / background status polling, and Excel export.
   - Matrix grid with colored badges for shift types (Night, Weekend, Day, On-Call).
   - **Click-to-Swap Drawer**: Click any shift to view eligible replacements with instant live constraint check (rest gaps, max consecutive days) via `POST /quarters/{key}/shifts/swap`.
   - Supports both Pre-Quarter Planning (Soll-Plan) and Live Realized Tracking (Ist-Plan) with full audit log.
4. **Simplified Fairness & Health Scorecard**:
   - Redesigned for stakeholder clarity: replaces confusing variance and Gini indices with 3 actionable signals:
     1. *Target Adherence Score*: Visual progress bar per staff member (assigned nights vs. target).
     2. *Weekend Burden Equity*: Distribution bar chart scaled to contract percentage.
     3. *Rest & Safety Traffic Light*: Green checks for 11h rest gap compliance and max consecutive streak limits.
5. **About & Release Highlights**:
   - Displays `CURRENT_VERSION` directly from `release_info.py`.
   - Changelog highlights showing recently deployed features and improvements.
   - Clinic planner documentation and support contacts.

### 6.3 Development & UI Implementation Strategy
- **Tech Stack**: React 19, TypeScript, Vite, Tailwind CSS.
- **Component Architecture (Option B - Shadcn / Radix Primitives)**:
  - Accessible, unstyled primitives for dialogs, popovers, drawers, and tabs wrapped in Tailwind classes.
  - Zero heavy black-box UI dependencies; all component code lives in `frontend/src/components/ui/`.
- **Iteration Workflow ("Vertical Slice" on Localhost)**:
  - Build the **Staff Directory Hub** first on `localhost` as the design anchor to dial in colors, typography, and density with instant Vite HMR (<50ms feedback).
  - Review and refine aesthetic collaboratively before extending the design system to the remaining 4 views.
  - Connect to local FastAPI dev server (`http://localhost:8000/api/v1`) or Cloud Run dev endpoint (`https://dienstplan-dev-owwijghxkq-ey.a.run.app/api/v1`).
  - Deploy production build to Firebase Hosting / Cloud CDN once verified.

---

## 7. Migration & Rollout Plan

```mermaid
gantt
    title Phased Modernization & SSOT Roadmap
    dateFormat  YYYY-MM-DD
    section Phase 1: Lift & Shift (Complete)
    Dockerfile Hardening & Cloud Run Config       :p1_1, 2026-11-02, 2d
    Deploy Existing Streamlit to Private Cloud Run:p1_2, after p1_1, 2d
    Verify Zero Disruption with Current Users     :p1_3, after p1_2, 3d

    section Phase 2: Decoupled API & SSOT Backend (Active)
    FastAPI Core wrapping app/scheduler           :p2_1, after p1_3, 3d
    Asynchronous Background Solver & Polling API  :p2_2, after p2_1, 3d
    Data Persistence (Firestore & Local Repo)     :p2_3, after p2_2, 4d
    Automated Roll-Over Engine Implementation     :p2_4, after p2_3, 3d
    Parallel Dev Service Deployment (dienstplan-dev):p2_5, after p2_4, 2d
    Comprehensive API Tests (Lifecycle & Solver)  :p2_6, after p2_5, 3d

    section Phase 3: React SSOT Frontend
    Vite + React + Tailwind Scaffold              :p3_1, after p2_6, 3d
    Staff Management & Vacation Calendar Views    :p3_2, after p3_1, 5d
    Interactive Matrix with Live Rule Validation  :p3_3, after p3_2, 6d
    Live Quarter Shift Swap & Ist-Tracking Mode   :p3_4, after p3_3, 5d
    Firebase Hosting Deployment & Decommissioning :p3_5, after p3_4, 3d
```

---

## 8. Summary of Added Requirements for SSOT

To achieve the single source of truth vision, the following items are now formally part of the PRD:
1. **Persistent Staff Master**: Replaces per-session `staff.csv` uploads with persistent CRUD entities.
2. **Continuous Absence Ledger**: Replaces quarterly `vacations.xlsx` uploads with an ongoing database ledger.
3. **Soll- vs. Ist-Tracking**: Adds shift swap and replacement logging directly into active schedules.
4. **Automated Roll-Over Engine**: Replaces manual `Arbeitseinsaetze.xlsx` context uploads with automated database queries feeding `build_previous_context(...)`.
5. **Excel Role Shift**: Excel is relegated from an operational storage format to a 1-click presentation/export format.
6. **Resilient Asynchronous Solver Execution**: Replaces fragile synchronous HTTP calls with an in-process background worker (`POST /generate` $\rightarrow$ `202 Accepted`, `GET /solver-status`) and Cloud Run `--no-cpu-throttling`, withstanding 10-minute "Gründlich" solves and bypassing CDN reverse-proxy timeouts.
7. **Zero-Risk Parallel Cloud Run Deployments**: Development and preview iterations deploy to `dienstplan-dev` with `min-instances=0` ($0 idle cost), guaranteeing zero disruption to the production service (`dienstplan-app`).
8. **Cloud Firestore Multi-Planner Persistence (Dual-Driver Pattern)**: Replaces ephemeral container storage with Google Cloud Firestore (`europe-west3`) for concurrent, collision-free multi-user planning over weeks, preserving the local `FileJsonRepository` for fast, offline testing.
