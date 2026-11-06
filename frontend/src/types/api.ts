export type Beruf = 'Tierarzt' | 'TFA' | 'Azubi' | 'Intern';
export type Abteilung = 'Station' | 'OP' | 'Sprechstunde' | 'Sonstiges';

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
  error?: string | null;
}


