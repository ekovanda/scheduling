export type Beruf = 'Vet' | 'Tierarzt' | 'TFA' | 'Azubi' | 'Intern';
export type Abteilung = 'Station' | 'OP' | 'other' | 'Sprechstunde' | 'Sonstiges';

export interface StaffMember {
  id: string;
  identifier: string;
  name: string;
  beruf: Beruf;
  abteilung: Abteilung;
  hours: number;
  adult: boolean;
  reception: boolean;
  nd_possible: boolean;
  nd_alone: boolean;
  nd_min_consecutive: number;
  nd_max_consecutive: number | null;
  nd_exceptions?: number[];
  birthday?: string | null;
  available_from?: string | null;
  is_active: boolean;
  created_at?: string;
  updated_at?: string;
}

export type AbsenceType = 'Vacation' | 'SickLeave' | 'SpecialLeave' | 'Training';

export interface AbsenceRecord {
  id: string;
  staff_id: string;
  absence_type: AbsenceType;
  start_date: string;
  end_date: string;
  note?: string | null;
}

export type PreAssignedShiftType = 'Nachtdienst' | 'Wochenenddienst' | 'Tagdienst';

export interface PreAssignedShift {
  id: string;
  staff_id: string;
  staff_identifier: string;
  shift_date: string;
  shift_type: PreAssignedShiftType;
  is_holiday?: boolean;
  note?: string;
}

export type ScheduleState = 'DRAFT' | 'PUBLISHED' | 'ACTIVE' | 'CLOSED';

export interface ShiftAssignmentRecord {
  shift_date: string;
  shift_type: string;
  planned_staff_id: string;
  actual_staff_id: string;
  is_paired: boolean;
  is_override: boolean;
  override_reason?: string | null;
  override_timestamp?: string | null;
}

export interface QuarterScheduleDocument {
  quarter_key: string;
  year: number;
  quarter: number;
  state: ScheduleState;
  config?: Record<string, unknown>;
  assignments: ShiftAssignmentRecord[];
  solver_metrics: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
}

export type InfeasibilityCategory =
  | 'PREASSIGNED_SAME_DAY'
  | 'PREASSIGNED_CONSECUTIVE_CAP'
  | 'PREASSIGNED_WEEKEND_ISOLATION'
  | 'PREASSIGNED_BLOCKED_WEEKDAY'
  | 'PREASSIGNED_ABSENCE_COLLISION'
  | 'PREASSIGNED_QUALIFICATION_MISMATCH'
  | 'PREASSIGNED_SOLO_UNQUALIFIED'
  | 'PREASSIGNED_PAIRING_UNQUALIFIED'
  | 'CAPACITY_TFA_OPEN_NIGHTS'
  | 'CAPACITY_TOTAL_NIGHTS'
  | 'CAPACITY_WEEKEND_ROLES'
  | 'CAPACITY_VET_MIDWEEK'
  | 'CAPACITY_NO_VIABLE_BLOCKS'
  | 'SOLVER_UNSATISFIABLE';

export type DiagnosticSeverity = 'ERROR' | 'WARNING';

export interface InfeasibilityDiagnosticRecord {
  category: InfeasibilityCategory;
  severity: DiagnosticSeverity;
  title: string;
  message: string;
  affected_staff_ids: string[];
  affected_dates: string[];
  remediation_hint: string;
}

export interface FeasibilityReportRecord {
  is_feasible: boolean;
  quarter_key: string;
  diagnostics: InfeasibilityDiagnosticRecord[];
  blocking_error_count: number;
  warning_count: number;
}

export type SolverJobStatus = 'IDLE' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';

export interface SolverJobRecord {
  job_id: string;
  quarter_key: string;
  status: SolverJobStatus;
  started_at: string;
  completed_at?: string | null;
  max_solve_time_seconds: number;
  elapsed_seconds: number;
  solutions_found: number;
  best_objective?: number | null;
  soft_penalty?: number | null;
  status_name?: string | null;
  best_objective_bound?: number | null;
  stopped_due_to_stagnation?: boolean;
  num_workers?: number | null;
  error?: string | null;
  diagnostics?: InfeasibilityDiagnosticRecord[];
}

export type FairnessStatus = 'balanced' | 'slight_deviation' | 'warning';

export interface StaffFairnessRecord {
  identifier: string;
  name: string;
  beruf: string;
  hours: number;
  vacation_days: number;
  presence_factor: number;
  effective_nights: number;
  weekend_shifts: number;
  total_notdienst: number;
  normalized_40h: number;
  group_mean_40h: number;
  plan_delta: number;
  cf_delta: number;
  net_delta: number;
  status: FairnessStatus;
  explanation: string;
}

export interface GroupFairnessSummary {
  beruf: string;
  total_staff: number;
  active_with_shifts: number;
  group_mean_40h: number;
  min_norm: number;
  max_norm: number;
  plan_spread: number;
  min_net: number;
  max_net: number;
  net_spread: number;
  balanced_pct: number;
}

export interface QuarterFairnessOverviewResponse {
  quarter_key: string;
  has_schedule: boolean;
  total_shifts: number;
  groups: Record<string, GroupFairnessSummary>;
  records: StaffFairnessRecord[];
}


