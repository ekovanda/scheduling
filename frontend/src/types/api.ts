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

