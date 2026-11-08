import type {
  StaffMember,
  AbsenceRecord,
  PreAssignedShift,
  QuarterScheduleDocument,
  SolverJobRecord,
  QuarterFairnessOverviewResponse,
  FeasibilityReportRecord,
} from '../types/api';

const API_BASE = '/api/v1';

export function getAuthToken(): string | null {
  return localStorage.getItem('clinic_auth_token');
}

export function setAuthToken(token: string | null): void {
  if (token) {
    localStorage.setItem('clinic_auth_token', token);
  } else {
    localStorage.removeItem('clinic_auth_token');
  }
}

async function authFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const token = getAuthToken();
  const headers = new Headers(init?.headers);
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', `Bearer ${token}`);
  }
  const response = await fetch(input, { ...init, headers });
  if (response.status === 401) {
    window.dispatchEvent(new CustomEvent('clinic:unauthorized'));
  }
  return response;
}

export async function checkAuthStatus(): Promise<{ required: boolean }> {
  try {
    const res = await fetch(`${API_BASE}/auth/status`);
    if (res.ok) {
      return res.json();
    }
  } catch {
    // fallback for offline or tests
  }
  return { required: false };
}

export async function loginClinic(password: string): Promise<{ authenticated: boolean; token?: string }> {
  const res = await fetch(`${API_BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Falsches Passwort.');
  }
  const data = await res.json();
  if (data.token) {
    setAuthToken(data.token);
  }
  return data;
}

export function logoutClinic(): void {
  setAuthToken(null);
  window.dispatchEvent(new CustomEvent('clinic:unauthorized'));
}

async function extractApiError(res: Response, fallback: string): Promise<string> {
  const errData = await res.json().catch(() => null);
  if (errData && typeof errData.detail === 'string') {
    return errData.detail;
  }
  if (errData && Array.isArray(errData.detail) && errData.detail.length > 0) {
    return errData.detail.map((e: { msg?: string }) => e.msg || JSON.stringify(e)).join('; ');
  }
  return `${fallback} (${res.statusText || res.status})`;
}

export async function fetchStaff(activeOnly = true): Promise<StaffMember[]> {
  try {
    const res = await authFetch(`${API_BASE}/staff?active_only=${activeOnly}`);
    if (!res.ok) {
      throw new Error(`Failed to fetch staff: ${res.statusText}`);
    }
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch (err) {
    console.error('Failed to fetch staff from backend:', err);
    return [];
  }
}

export async function createStaff(staff: Omit<StaffMember, 'id'>): Promise<StaffMember> {
  const res = await authFetch(`${API_BASE}/staff`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...staff, id: staff.identifier.toLowerCase() }),
  });
  if (!res.ok) {
    throw new Error(await extractApiError(res, 'Fehler beim Anlegen des Mitarbeiters'));
  }
  return res.json();
}

export async function updateStaff(staffId: string, staff: StaffMember): Promise<StaffMember> {
  const res = await authFetch(`${API_BASE}/staff/${staffId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(staff),
  });
  if (!res.ok) {
    throw new Error(await extractApiError(res, 'Fehler beim Aktualisieren des Mitarbeiters'));
  }
  return res.json();
}

export async function deleteStaff(staffId: string, hardDelete = false): Promise<void> {
  const res = await authFetch(`${API_BASE}/staff/${staffId}?hard_delete=${hardDelete}`, {
    method: 'DELETE',
  });
  if (!res.ok) {
    throw new Error(await extractApiError(res, 'Fehler beim Deaktivieren/Löschen des Mitarbeiters'));
  }
}

export async function fetchAbsences(): Promise<AbsenceRecord[]> {
  try {
    const res = await authFetch(`${API_BASE}/absences`);
    if (!res.ok) throw new Error(res.statusText);
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch (err) {
    console.error('Failed to fetch absences from backend:', err);
    return [];
  }
}

export async function createAbsence(record: AbsenceRecord): Promise<AbsenceRecord> {
  const res = await authFetch(`${API_BASE}/absences`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(record),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Fehler beim Speichern der Abwesenheit'));
  return res.json();
}

export async function updateAbsence(id: string, record: AbsenceRecord): Promise<AbsenceRecord> {
  const res = await authFetch(`${API_BASE}/absences/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(record),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Fehler beim Aktualisieren der Abwesenheit'));
  return res.json();
}

export async function deleteAbsence(id: string): Promise<void> {
  const res = await authFetch(`${API_BASE}/absences/${id}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Fehler beim Löschen der Abwesenheit'));
}

export async function fetchPreAssigned(): Promise<PreAssignedShift[]> {
  try {
    const res = await authFetch(`${API_BASE}/preassigned`);
    if (!res.ok) throw new Error(res.statusText);
    const data = await res.json();
    return Array.isArray(data) ? data : [];
  } catch (err) {
    console.error('Failed to fetch preassigned shifts from backend:', err);
    return [];
  }
}

export async function createPreAssigned(shift: PreAssignedShift): Promise<PreAssignedShift> {
  const res = await authFetch(`${API_BASE}/preassigned`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(shift),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Fehler beim Speichern der Vorbelegung'));
  return res.json();
}

export async function updatePreAssigned(id: string, shift: PreAssignedShift): Promise<PreAssignedShift> {
  const res = await authFetch(`${API_BASE}/preassigned/${id}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(shift),
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Fehler beim Aktualisieren der Vorbelegung'));
  return res.json();
}

export async function deletePreAssigned(id: string): Promise<void> {
  const res = await authFetch(`${API_BASE}/preassigned/${id}`, {
    method: 'DELETE',
  });
  if (!res.ok) throw new Error(await extractApiError(res, 'Fehler beim Löschen der Vorbelegung'));
}

export async function fetchSchedule(quarterKey: string): Promise<QuarterScheduleDocument | null> {
  try {
    const res = await authFetch(`${API_BASE}/quarters/${quarterKey}`);
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
    block_gap_days?: number;
  }
): Promise<SolverJobRecord> {
  const res = await authFetch(`${API_BASE}/quarters/${quarterKey}/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      max_solve_time_seconds: options?.max_solve_time_seconds ?? 600,
      random_seed: options?.random_seed,
      include_previous_context: options?.include_previous_context ?? true,
      stagnation_limit_seconds: options?.stagnation_limit_seconds ?? 30,
      block_gap_days: options?.block_gap_days ?? 21,
    }),
  });
  if (!res.ok && res.status !== 202) {
    const errData = await res.json().catch(() => null);
    throw new Error(errData?.detail || `Solver failed: ${res.statusText}`);
  }
  return res.json();
}

export async function fetchSolverStatus(quarterKey: string): Promise<SolverJobRecord> {
  const res = await authFetch(`${API_BASE}/quarters/${quarterKey}/solver-status`);
  if (!res.ok) {
    throw new Error(`Failed to fetch solver status: ${res.statusText}`);
  }
  return res.json();
}

export async function cancelSolverJob(quarterKey: string): Promise<{ message: string }> {
  const res = await authFetch(`${API_BASE}/quarters/${quarterKey}/cancel`, {
    method: 'POST',
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => null);
    throw new Error(errData?.detail || `Failed to cancel solver: ${res.statusText}`);
  }
  return res.json();
}

export async function validateQuarterFeasibility(
  quarterKey: string
): Promise<FeasibilityReportRecord> {
  const res = await authFetch(`${API_BASE}/quarters/${quarterKey}/validate-feasibility`, {
    method: 'POST',
  });
  if (!res.ok) {
    const errData = await res.json().catch(() => null);
    throw new Error(errData?.detail || `Fehler bei der Machbarkeitsprüfung: ${res.statusText}`);
  }
  return res.json();
}

export async function generateSchedule(quarterKey: string): Promise<QuarterScheduleDocument | null> {
  const res = await authFetch(`${API_BASE}/quarters/${quarterKey}/generate?sync=true`, {
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
  const res = await authFetch(`${API_BASE}/quarters/${quarterKey}/shifts/swap`, {
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
  const res = await authFetch(`${API_BASE}/quarters/${quarterKey}/publish`, {
    method: 'POST',
  });
  if (!res.ok) throw new Error(`Failed to publish: ${res.statusText}`);
  return res.json();
}

export async function exportQuarterSchedule(
  quarterKey: string,
  format: 'xlsx' | 'csv' = 'xlsx'
): Promise<void> {
  const res = await authFetch(`${API_BASE}/quarters/${quarterKey}/export?format=${format}`);
  if (!res.ok) {
    const errData = await res.json().catch(() => null);
    throw new Error(errData?.detail || `Export fehlgeschlagen: ${res.statusText}`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `Dienstplan_${quarterKey}.${format}`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
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
    const res = await authFetch(`${API_BASE}/quarters/${quarterKey}/rollover`);
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
    const res = await authFetch(`${API_BASE}/quarters/${quarterKey}/fairness`);
    if (!res.ok) throw new Error(res.statusText);
    return res.json();
  } catch (err) {
    console.warn('Fairness overview fetch failed:', err);
    return null;
  }
}
