import type {
  StaffMember,
  AbsenceRecord,
  PreAssignedShift,
  QuarterScheduleDocument,
  ShiftAssignmentRecord,
  SolverJobRecord,
  QuarterFairnessOverviewResponse,
} from '../types/api';

const API_BASE = '/api/v1';

export async function fetchStaff(): Promise<StaffMember[]> {
  try {
    const res = await fetch(`${API_BASE}/staff`);
    if (!res.ok) {
      throw new Error(`Failed to fetch staff: ${res.statusText}`);
    }
    const data = await res.json();
    if (Array.isArray(data) && data.length > 0) {
      return data;
    }
    return MOCK_STAFF;
  } catch (err) {
    console.warn('Backend not reachable or empty, using sample clinic staff:', err);
    return MOCK_STAFF;
  }
}

export async function createStaff(staff: Omit<StaffMember, 'id'>): Promise<StaffMember> {
  const res = await fetch(`${API_BASE}/staff`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...staff, id: staff.identifier.toLowerCase() }),
  });
  if (!res.ok) {
    throw new Error(`Error creating staff: ${res.statusText}`);
  }
  return res.json();
}

export async function updateStaff(staffId: string, staff: StaffMember): Promise<StaffMember> {
  const res = await fetch(`${API_BASE}/staff/${staffId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(staff),
  });
  if (!res.ok) {
    throw new Error(`Error updating staff: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchAbsences(): Promise<AbsenceRecord[]> {
  try {
    const res = await fetch(`${API_BASE}/absences`);
    if (!res.ok) throw new Error(res.statusText);
    const data = await res.json();
    if (Array.isArray(data) && data.length > 0) return data;
    return MOCK_ABSENCES;
  } catch (err) {
    console.warn('Backend not reachable or empty, using sample absences:', err);
    return MOCK_ABSENCES;
  }
}

export async function createAbsence(record: AbsenceRecord): Promise<AbsenceRecord> {
  const res = await fetch(`${API_BASE}/absences`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(record),
  });
  if (!res.ok) throw new Error(`Failed to record absence: ${res.statusText}`);
  return res.json();
}

export async function deleteAbsence(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/absences/${id}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`Failed to delete absence: ${res.statusText}`);
}

export async function fetchPreAssigned(): Promise<PreAssignedShift[]> {
  try {
    const res = await fetch(`${API_BASE}/preassigned`);
    if (!res.ok) throw new Error(res.statusText);
    const data = await res.json();
    if (Array.isArray(data) && data.length > 0) return data;
    return MOCK_PREASSIGNED;
  } catch (err) {
    console.warn('Backend preassigned not reachable or empty, using sample:', err);
    return MOCK_PREASSIGNED;
  }
}

export async function createPreAssigned(shift: PreAssignedShift): Promise<PreAssignedShift> {
  const res = await fetch(`${API_BASE}/preassigned`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(shift),
  });
  if (!res.ok) throw new Error(`Failed to save preassigned shift: ${res.statusText}`);
  return res.json();
}

export async function deletePreAssigned(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/preassigned/${id}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(`Failed to delete preassigned shift: ${res.statusText}`);
}

export async function fetchSchedule(quarterKey: string): Promise<QuarterScheduleDocument | null> {
  try {
    const res = await fetch(`${API_BASE}/quarters/${quarterKey}`);
    if (!res.ok) return null;
    const doc = await res.json();
    if (doc && doc.assignments && doc.assignments.length > 0) return doc;
    return null;
  } catch (err) {
    console.warn('Backend schedule fetch failed:', err);
    return null;
  }
}

export async function startSolverJob(
  quarterKey: string,
  options?: {
    max_solve_time_seconds?: number;
    random_seed?: number;
    include_previous_context?: boolean;
    stagnation_limit_seconds?: number;
  }
): Promise<SolverJobRecord> {
  const res = await fetch(`${API_BASE}/quarters/${quarterKey}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      max_solve_time_seconds: options?.max_solve_time_seconds ?? 600,
      random_seed: options?.random_seed,
      include_previous_context: options?.include_previous_context ?? true,
      stagnation_limit_seconds: options?.stagnation_limit_seconds ?? 30,
    }),
  });
  if (!res.ok && res.status !== 202) {
    const errData = await res.json().catch(() => null);
    throw new Error(errData?.detail || `Solver failed: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchSolverStatus(quarterKey: string): Promise<SolverJobRecord> {
  const res = await fetch(`${API_BASE}/quarters/${quarterKey}/solver-status`);
  if (!res.ok) {
    throw new Error(`Failed to fetch solver status: ${res.statusText}`);
  }
  return res.json();
}

export async function cancelSolverJob(quarterKey: string): Promise<{ message: string }> {
  const res = await fetch(`${API_BASE}/quarters/${quarterKey}/cancel`, {
    method: 'POST',
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => null);
    throw new Error(errData?.detail || `Failed to cancel solver: ${res.statusText}`);
  }
  return res.json();
}

export async function generateSchedule(quarterKey: string): Promise<QuarterScheduleDocument | null> {
  const res = await fetch(`${API_BASE}/quarters/${quarterKey}/generate?sync=true`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ max_solve_time_seconds: 90, stagnation_limit_seconds: 15 }),
  });
  if (!res.ok) {
    throw new Error(`Solver failed: ${res.statusText}`);
  }
  return fetchSchedule(quarterKey);
}

export async function swapShift(
  quarterKey: string,
  params: {
    shift_date: string;
    shift_type: string;
    old_staff_id: string;
    new_staff_id: string;
    reason: string;
    force?: boolean;
  }
): Promise<QuarterScheduleDocument> {
  const res = await fetch(`${API_BASE}/quarters/${quarterKey}/shifts/swap`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    throw new Error(`Shift swap rejected: ${res.statusText}`);
  }
  return res.json();
}

export async function publishSchedule(quarterKey: string): Promise<QuarterScheduleDocument> {
  const res = await fetch(`${API_BASE}/quarters/${quarterKey}/publish`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`Failed to publish: ${res.statusText}`);
  return res.json();
}

export const MOCK_STAFF: StaffMember[] = [
  {
    id: 'mueller',
    identifier: 'MUE',
    name: 'Dr. Julia Müller',
    beruf: 'Vet',
    abteilung: 'Station',
    hours: 0,
    adult: true,
    reception: false,
    nd_possible: true,
    nd_alone: true,
    nd_min_consecutive: 2,
    nd_max_consecutive: 4,
    is_active: true,
  },
  {
    id: 'schmidt',
    identifier: 'SCH',
    name: 'Dr. Thomas Schmidt',
    beruf: 'Vet',
    abteilung: 'OP',
    hours: 0,
    adult: true,
    reception: false,
    nd_possible: true,
    nd_alone: true,
    nd_min_consecutive: 2,
    nd_max_consecutive: 4,
    is_active: true,
  },
  {
    id: 'weber',
    identifier: 'WEB',
    name: 'Katharina Weber',
    beruf: 'TFA',
    abteilung: 'Station',
    hours: 40,
    adult: true,
    reception: false,
    nd_possible: true,
    nd_alone: true,
    nd_min_consecutive: 2,
    nd_max_consecutive: 5,
    is_active: true,
  },
  {
    id: 'koch',
    identifier: 'KOC',
    name: 'Lena Koch',
    beruf: 'TFA',
    abteilung: 'Sprechstunde',
    hours: 30,
    adult: true,
    reception: true,
    nd_possible: true,
    nd_alone: false,
    nd_min_consecutive: 2,
    nd_max_consecutive: 4,
    is_active: true,
  },
  {
    id: 'bauer',
    identifier: 'BAU',
    name: 'Felix Bauer',
    beruf: 'Azubi',
    abteilung: 'Station',
    hours: 38,
    adult: false,
    reception: false,
    nd_possible: false,
    nd_alone: false,
    nd_min_consecutive: 2,
    nd_max_consecutive: 3,
    is_active: true,
  },
  {
    id: 'wagner',
    identifier: 'WAG',
    name: 'Dr. Sarah Wagner',
    beruf: 'Intern',
    abteilung: 'OP',
    hours: 40,
    adult: true,
    reception: false,
    nd_possible: true,
    nd_alone: false,
    nd_min_consecutive: 2,
    nd_max_consecutive: 3,
    is_active: true,
  },
];

export const MOCK_ABSENCES: AbsenceRecord[] = [
  // Dr. Julia Müller (MUE)
  { id: 'abs-1', staff_id: 'mueller', absence_type: 'Vacation', start_date: '2026-04-10', end_date: '2026-04-17' },
  { id: 'abs-2', staff_id: 'mueller', absence_type: 'Vacation', start_date: '2026-05-22', end_date: '2026-05-25' },
  { id: 'abs-3', staff_id: 'mueller', absence_type: 'Vacation', start_date: '2026-06-15', end_date: '2026-06-21' },

  // Dr. Thomas Schmidt (SCH)
  { id: 'abs-4', staff_id: 'schmidt', absence_type: 'Vacation', start_date: '2026-04-03', end_date: '2026-04-06' },
  { id: 'abs-5', staff_id: 'schmidt', absence_type: 'Vacation', start_date: '2026-05-04', end_date: '2026-05-10' },
  { id: 'abs-6', staff_id: 'schmidt', absence_type: 'Vacation', start_date: '2026-06-01', end_date: '2026-06-03' },

  // Katharina Weber (WEB)
  { id: 'abs-7', staff_id: 'weber', absence_type: 'Vacation', start_date: '2026-04-14', end_date: '2026-04-20' },
  { id: 'abs-8', staff_id: 'weber', absence_type: 'Vacation', start_date: '2026-05-15', end_date: '2026-05-24' },

  // Lena Koch (KOC)
  { id: 'abs-9', staff_id: 'koch', absence_type: 'Vacation', start_date: '2026-04-27', end_date: '2026-05-03' },
  { id: 'abs-10', staff_id: 'koch', absence_type: 'Vacation', start_date: '2026-06-08', end_date: '2026-06-14' },

  // Felix Bauer (BAU)
  { id: 'abs-11', staff_id: 'bauer', absence_type: 'Vacation', start_date: '2026-04-01', end_date: '2026-04-05' },
  { id: 'abs-12', staff_id: 'bauer', absence_type: 'Vacation', start_date: '2026-05-18', end_date: '2026-05-22' },
  { id: 'abs-13', staff_id: 'bauer', absence_type: 'Vacation', start_date: '2026-06-22', end_date: '2026-06-26' },

  // Dr. Sarah Wagner (WAG)
  { id: 'abs-14', staff_id: 'wagner', absence_type: 'Vacation', start_date: '2026-04-18', end_date: '2026-04-24' },
  { id: 'abs-15', staff_id: 'wagner', absence_type: 'Vacation', start_date: '2026-05-29', end_date: '2026-06-02' },
];

export const MOCK_PREASSIGNED: PreAssignedShift[] = [
  {
    id: 'pa-1',
    staff_id: 'schmidt',
    staff_identifier: 'SCH',
    shift_date: '2026-04-12',
    shift_type: 'Nachtdienst',
    is_holiday: true,
    note: 'Ostersonntag (Fest zugesagt)',
  },
  {
    id: 'pa-2',
    staff_id: 'weber',
    staff_identifier: 'WEB',
    shift_date: '2026-04-13',
    shift_type: 'Wochenenddienst',
    is_holiday: true,
    note: 'Ostermontag Tagdienst',
  },
  {
    id: 'pa-3',
    staff_id: 'wagner',
    staff_identifier: 'WAG',
    shift_date: '2026-05-01',
    shift_type: 'Nachtdienst',
    is_holiday: true,
    note: 'Tag der Arbeit',
  },
  {
    id: 'pa-4',
    staff_id: 'mueller',
    staff_identifier: 'MUE',
    shift_date: '2026-05-14',
    shift_type: 'Nachtdienst',
    is_holiday: true,
    note: 'Christi Himmelfahrt',
  },
];


export function getMockSchedule(quarterKey: string): QuarterScheduleDocument {
  const assignments: ShiftAssignmentRecord[] = [];
  const vets = ['mueller', 'schmidt', 'wagner'];
  const tfas = ['weber', 'koch', 'bauer'];

  // Generate 91 days for Q2 (Apr 1 to Jun 30, 2026)
  const startDate = new Date(2026, 3, 1); // 2026-04-01
  for (let i = 0; i < 91; i++) {
    const cur = new Date(startDate);
    cur.setDate(startDate.getDate() + i);
    const yyyy = cur.getFullYear();
    const mm = String(cur.getMonth() + 1).padStart(2, '0');
    const dd = String(cur.getDate()).padStart(2, '0');
    const dateStr = `${yyyy}-${mm}-${dd}`;
    const dayOfWeek = cur.getDay(); // 0 = Sun, 6 = Sat

    // Night shift (assigned to vets in blocks of 2-3)
    const vetIdx = Math.floor(i / 3) % vets.length;
    const vetId = vets[vetIdx];

    // Example shift swap on April 15
    const isSwapDay = dateStr === '2026-04-15';

    assignments.push({
      shift_date: dateStr,
      shift_type: 'Nachtdienst',
      planned_staff_id: vetId,
      actual_staff_id: isSwapDay ? 'wagner' : vetId,
      is_paired: i % 4 === 0, // Some nights have paired TFA
      is_override: isSwapDay,
      override_reason: isSwapDay ? 'Tausch wegen Fortbildung' : undefined,
    });

    // Weekend day shift (Sat & Sun)
    if (dayOfWeek === 0 || dayOfWeek === 6) {
      const tfaIdx = i % tfas.length;
      assignments.push({
        shift_date: dateStr,
        shift_type: 'Wochenende_Tag',
        planned_staff_id: tfas[tfaIdx],
        actual_staff_id: tfas[tfaIdx],
        is_paired: false,
        is_override: false,
      });
    }
  }

  return {
    quarter_key: quarterKey,
    year: 2026,
    quarter: 2,
    state: 'DRAFT',
    assignments,
    solver_metrics: {
      solve_time_seconds: 14.2,
      num_shifts: assignments.length,
      fairness_score: 96.5,
      violations: 0,
    },
  };
}


export interface RolloverContextData {
  has_context: boolean;
  message?: string;
  quarter_start?: string;
  quarter_end?: string;
  carry_forward: Array<{
    identifier: string;
    name: string;
    beruf: string;
    hours: number;
    effective_nights: number;
    weekend_shifts: number;
    total_notdienst?: number;
    normalized_40h?: number;
    group_mean_40h?: number;
    carry_forward_delta: number;
  }>;
  trailing_assignments: Array<{
    staff_identifier: string;
    shift_date: string;
    shift_type: string;
    is_night: boolean;
    is_paired?: boolean;
  }>;
}

export async function fetchRolloverContext(quarterKey: string): Promise<RolloverContextData> {
  try {
    const res = await fetch(`${API_BASE}/quarters/${quarterKey}/rollover`);
    if (!res.ok) throw new Error(res.statusText);
    return res.json();
  } catch (err) {
    console.warn('Rollover context fetch failed, returning empty:', err);
    return {
      has_context: false,
      message: 'Kein Vorplan gefunden.',
      carry_forward: [],
      trailing_assignments: [],
    };
  }
}

export async function fetchFairnessOverview(quarterKey: string): Promise<QuarterFairnessOverviewResponse | null> {
  try {
    const res = await fetch(`${API_BASE}/quarters/${quarterKey}/fairness`);
    if (!res.ok) throw new Error(res.statusText);
    return res.json();
  } catch (err) {
    console.warn('Fairness overview fetch failed:', err);
    return null;
  }
}
