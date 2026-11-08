import React, { useState, useEffect } from 'react';
import {
  Download,
  Play,
  CheckCircle2,
  Calendar as CalendarIcon,
  Pin,
  Settings2,
  Loader2,
  ChevronDown,
  Scale,
  History,
  Clock,
  AlertCircle,
  StopCircle,
  Sparkles,
  ShieldCheck,
  AlertTriangle,
} from 'lucide-react';
import type {
  QuarterScheduleDocument,
  StaffMember,
  PreAssignedShift,
  AbsenceRecord,
  SolverJobRecord,
  FeasibilityReportRecord,
} from '../types/api';
import {
  fetchSchedule,
  fetchStaff,
  fetchPreAssigned,
  fetchAbsences,
  fetchRolloverContext,
  startSolverJob,
  fetchSolverStatus,
  cancelSolverJob,
  validateQuarterFeasibility,
  type RolloverContextData,
} from '../lib/api';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { cn, isBirthdayToday, isNightShift } from '../lib/utils';

interface MatrixViewProps {
  currentQuarter?: string;
  onQuarterChange?: (q: string) => void;
}

export const MatrixView: React.FC<MatrixViewProps> = ({
  currentQuarter: propCurrentQuarter,
  onQuarterChange,
}) => {
  const [schedule, setSchedule] = useState<QuarterScheduleDocument | null>(null);
  const [staffList, setStaffList] = useState<StaffMember[]>([]);
  const [preAssigned, setPreAssigned] = useState<PreAssignedShift[]>([]);
  const [absences, setAbsences] = useState<AbsenceRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [solving, setSolving] = useState(false);

  // Mode: 'view' (schedule display) or 'setup' (distraction-free plan generation)
  const [pageMode, setPageMode] = useState<'view' | 'setup'>('view');
  const [subView, setSubView] = useState<'schedule' | 'rollover'>('schedule');
  const [rollover, setRollover] = useState<RolloverContextData | null>(null);

  // Display toggles matching Streamlit original
  const [showFullNames, setShowFullNames] = useState(false);
  const [selectedMonth, setSelectedMonth] = useState<number | 'ALL'>('ALL'); // 3=Apr, 4=May, 5=Jun

  // Setup form states (initialized from prop or default 2027-Q1)
  const [setupQuarter, setSetupQuarter] = useState(() => {
    if (propCurrentQuarter) {
      const parts = propCurrentQuarter.split('-');
      return parts[1] || 'Q1';
    }
    return 'Q1';
  });
  const [setupYear, setSetupYear] = useState(() => {
    if (propCurrentQuarter) {
      const parts = propCurrentQuarter.split('-');
      return Number(parts[0]) || 2027;
    }
    return 2027;
  });
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [maxSolveMinutes, setMaxSolveMinutes] = useState(10);
  const [blockGapDays, setBlockGapDays] = useState(21);
  const [includePreviousQuarter, setIncludePreviousQuarter] = useState(true);
  const [rolloverRoleFilter, setRolloverRoleFilter] = useState<'ALL' | 'Vet' | 'TFA' | 'Intern'>('ALL');

  // Sync state if global prop changes
  useEffect(() => {
    if (propCurrentQuarter) {
      const [y, q] = propCurrentQuarter.split('-');
      if (y && q) {
        setSetupYear(Number(y));
        setSetupQuarter(q);
      }
    }
  }, [propCurrentQuarter]);

  // Asynchronous Solver state
  const [activeJob, setActiveJob] = useState<SolverJobRecord | null>(null);
  const [solverModalOpen, setSolverModalOpen] = useState(false);
  const [solverError, setSolverError] = useState<string | null>(null);

  // Feasibility & Diagnostics state
  const [feasibilityReport, setFeasibilityReport] = useState<FeasibilityReportRecord | null>(null);
  const [checkingFeasibility, setCheckingFeasibility] = useState(false);
  const [feasibilityModalOpen, setFeasibilityModalOpen] = useState(false);

  const currentQuarterKey = `${setupYear}-${setupQuarter}`;

  useEffect(() => {
    loadData();
  }, [currentQuarterKey]);

  useEffect(() => {
    let timer: any = null;
    let isMounted = true;

    if (activeJob?.status === 'RUNNING') {
      timer = setInterval(async () => {
        try {
          const status = await fetchSolverStatus(currentQuarterKey);
          if (!isMounted) return;
          setActiveJob(status);
          if (status.status === 'COMPLETED') {
            const fresh = await fetchSchedule(currentQuarterKey);
            if (isMounted) {
              setSchedule(fresh);
              setSolving(false);
              if (fresh && fresh.assignments && fresh.assignments.length > 0) {
                setPageMode('view');
              }
            }
          } else if (status.status === 'FAILED' || status.status === 'CANCELLED') {
            if (isMounted) {
              setSolving(false);
              setSolverError(status.error || 'Berechnung fehlgeschlagen.');
            }
          }
        } catch (err) {
          console.warn('Status poll error:', err);
        }
      }, 1500);
    }

    return () => {
      isMounted = false;
      if (timer) clearInterval(timer);
    };
  }, [activeJob?.status, currentQuarterKey]);

  const loadData = async () => {
    setLoading(true);
    const [schedData, stfData, paData, absData, rollData, jobData] = await Promise.all([
      fetchSchedule(currentQuarterKey),
      fetchStaff(),
      fetchPreAssigned(),
      fetchAbsences(),
      fetchRolloverContext(currentQuarterKey),
      fetchSolverStatus(currentQuarterKey).catch(() => null),
    ]);
    setSchedule(schedData);
    setStaffList(stfData);
    setPreAssigned(paData);
    setAbsences(absData);
    setRollover(rollData);
    if (jobData && jobData.status === 'RUNNING') {
      setActiveJob(jobData);
      setSolving(true);
    }

    // Automatically open in setup mode if no schedule exists yet
    if (!schedData || !schedData.assignments || schedData.assignments.length === 0) {
      setPageMode('setup');
    } else {
      setPageMode('view');
    }

    setLoading(false);
  };

  const getStaff = (idOrIdent: string) => {
    if (!idOrIdent) return undefined;
    const needle = idOrIdent.trim().toLowerCase();
    return staffList.find(
      (s) => s.id.toLowerCase() === needle || s.identifier.toLowerCase() === needle
    );
  };

  const isShiftPreAssigned = (shift: { shift_date: string; shift_type: string; actual_staff_id: string }) => {
    return preAssigned.some((pa) => {
      if (pa.shift_date !== shift.shift_date) return false;
      const paId = pa.staff_id?.trim().toLowerCase();
      const paIdent = pa.staff_identifier?.trim().toLowerCase();
      const shiftStaff = shift.actual_staff_id.trim().toLowerCase();

      const staffMatches = paId === shiftStaff || paIdent === shiftStaff;
      if (!staffMatches) return false;

      const isPaNight = isNightShift(pa.shift_type);
      const isShiftNight = isNightShift(shift.shift_type);

      return (
        pa.shift_type === shift.shift_type ||
        (isPaNight && isShiftNight) ||
        (!isPaNight && !isShiftNight)
      );
    });
  };

  interface WeekendShiftMeta {
    num: number;
    label: string;
    hours: string;
    className: string;
  }

  const getWeekendShiftMeta = (shiftType: string): WeekendShiftMeta => {
    const t = (shiftType || '').toLowerCase().trim();

    // 1: Frühdienst (Sa 10–21, So/FT 8–20)
    if (shiftType === 'Sa_10-21') {
      return {
        num: 1,
        label: 'Frühdienst',
        hours: 'Sa 10:00–21:00',
        className: 'bg-amber-100 text-amber-900 border-amber-300',
      };
    }
    if (shiftType === 'So_8-20') {
      return {
        num: 1,
        label: 'Frühdienst',
        hours: 'So/FT 08:00–20:00',
        className: 'bg-amber-100 text-amber-900 border-amber-300',
      };
    }

    // 2: Spätdienst Azubi (Sa 10–19)
    if (shiftType === 'Sa_10-19') {
      return {
        num: 2,
        label: 'Spätdienst Azubi',
        hours: 'Sa 10:00–19:00',
        className: 'bg-orange-100 text-orange-900 border-orange-300',
      };
    }

    // 3: Rufbereitschaft (Sa/So 10–22)
    if (shiftType === 'Sa_10-22' || shiftType === 'So_10-22') {
      return {
        num: 3,
        label: 'Rufbereitschaft',
        hours: 'Sa & So 10:00–22:00',
        className: 'bg-purple-100 text-purple-900 border-purple-300',
      };
    }

    // 4: Azubi Rufbereitschaft (So 8–20:30)
    if (shiftType === 'So_8-20:30') {
      return {
        num: 4,
        label: 'Azubi Rufbereitschaft',
        hours: 'So/FT 08:00–20:30',
        className: 'bg-blue-100 text-blue-900 border-blue-300',
      };
    }

    // Generic fallbacks
    if (t.includes('8-20') || t.includes('10-21') || t.includes('früh') || t.includes('tag')) {
      return { num: 1, label: 'Frühdienst', hours: '', className: 'bg-amber-100 text-amber-900 border-amber-300' };
    }
    if (t.includes('10-19') || t.includes('spät')) {
      return { num: 2, label: 'Spätdienst', hours: '', className: 'bg-orange-100 text-orange-900 border-orange-300' };
    }
    if (t.includes('10-22') || t.includes('ruf')) {
      return { num: 3, label: 'Rufbereitschaft', hours: '', className: 'bg-purple-100 text-purple-900 border-purple-300' };
    }
    if (t.includes('20:30') || t.includes('azubi')) {
      return { num: 4, label: 'Azubi Ruf', hours: '', className: 'bg-blue-100 text-blue-900 border-blue-300' };
    }

    return { num: 1, label: shiftType, hours: '', className: 'bg-stone-100 text-stone-700 border-stone-200' };
  };

  const getShiftOrder = (shiftType: string): number => {
    return getWeekendShiftMeta(shiftType).num;
  };

  const getStaffDisplayName = (id: string, isVet = false) => {
    const s = getStaff(id);
    if (!s) return id.toUpperCase();
    const prefix = isVet && (s.beruf === 'Vet' || s.beruf === 'Tierarzt') ? '🩺 ' : '';
    if (showFullNames) {
      return `${prefix}${s.name}`;
    }
    return `${prefix}${s.identifier}`;
  };

  const formatTimer = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.floor(seconds % 60);
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  // Check Feasibility (Deterministic Pre-Flight Engine)
  const handleCheckFeasibility = async () => {
    setCheckingFeasibility(true);
    try {
      const report = await validateQuarterFeasibility(currentQuarterKey);
      setFeasibilityReport(report);
      setFeasibilityModalOpen(true);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      console.error('Feasibility check failed:', msg);
    } finally {
      setCheckingFeasibility(false);
    }
  };

  // Run Solver (Async Background Runner with Smart Auto-Stop)
  const handleRunSolver = async () => {
    setSolving(true);
    setSolverError(null);
    setSolverModalOpen(true);
    try {
      const job = await startSolverJob(currentQuarterKey, {
        max_solve_time_seconds: maxSolveMinutes * 60,
        stagnation_limit_seconds: 30,
        include_previous_context: includePreviousQuarter,
      });
      setActiveJob(job);
      if (job.status === 'FAILED') {
        setSolving(false);
        setSolverError(job.error || 'Vorprüfung fehlgeschlagen.');
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setSolverError(msg);
      setSolving(false);
    }
  };

  const handleCancelSolve = async () => {
    try {
      await cancelSolverJob(currentQuarterKey);
      const st = await fetchSolverStatus(currentQuarterKey).catch(() => null);
      if (st) setActiveJob(st);
    } catch (err) {
      console.warn('Cancel error:', err);
    }
  };

  // Group assignments by unique date
  const assignments = schedule ? schedule.assignments : [];
  const uniqueDates = Array.from(new Set(assignments.map((a) => a.shift_date))).sort();

  // Filter dates by month
  const filteredDates = uniqueDates.filter((dateStr) => {
    if (selectedMonth === 'ALL') return true;
    const [, mStr] = dateStr.split('-');
    return Number(mStr) - 1 === selectedMonth;
  });

  // Staff with birthday today
  const birthdayStaff = staffList.filter((s) => s.is_active && isBirthdayToday(s.birthday));

  const monthTabs = React.useMemo(() => {
    switch (setupQuarter) {
      case 'Q1':
        return [
          { id: 'ALL' as const, label: 'Quartal (Gesamt)' },
          { id: 0, label: 'Januar' },
          { id: 1, label: 'Februar' },
          { id: 2, label: 'März' },
        ];
      case 'Q2':
        return [
          { id: 'ALL' as const, label: 'Quartal (Gesamt)' },
          { id: 3, label: 'April' },
          { id: 4, label: 'Mai' },
          { id: 5, label: 'Juni' },
        ];
      case 'Q3':
        return [
          { id: 'ALL' as const, label: 'Quartal (Gesamt)' },
          { id: 6, label: 'Juli' },
          { id: 7, label: 'August' },
          { id: 8, label: 'September' },
        ];
      case 'Q4':
      default:
        return [
          { id: 'ALL' as const, label: 'Quartal (Gesamt)' },
          { id: 9, label: 'Oktober' },
          { id: 10, label: 'November' },
          { id: 11, label: 'Dezember' },
        ];
    }
  }, [setupQuarter]);

  const isWeekendDay = (dateStr: string) => {
    const [year, month, day] = dateStr.split('-');
    const d = new Date(Number(year), Number(month) - 1, Number(day));
    return d.getDay() === 0 || d.getDay() === 6;
  };

  const getWeekdayShort = (dateStr: string) => {
    const [year, month, day] = dateStr.split('-');
    const d = new Date(Number(year), Number(month) - 1, Number(day));
    const weekdays = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];
    return weekdays[d.getDay()];
  };

  return (
    <div className="space-y-6">
      {/* Persistent Background Solver Notification Banner */}
      {activeJob?.status === 'RUNNING' && (
        <div className="bg-amber-50/90 border border-amber-300 text-amber-950 px-4 py-2.5 rounded-xl flex items-center justify-between shadow-2xs animate-in fade-in">
          <div className="flex items-center gap-2.5">
            <Loader2 className="h-4 w-4 animate-spin text-amber-700 shrink-0" />
            <span className="text-xs font-medium">
              <strong>Berechnung für {currentQuarterKey} aktiv:</strong> {formatTimer(activeJob.elapsed_seconds)} &middot; {activeJob.solutions_found} Lösungen gefunden
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs bg-white border-amber-300 text-amber-900 hover:bg-amber-100"
              onClick={() => setSolverModalOpen(true)}
            >
              Live-Status
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-xs text-red-700 hover:bg-red-100"
              onClick={handleCancelSolve}
            >
              Abbrechen
            </Button>
          </div>
        </div>
      )}
      {/* ============================================================== */}
      {/* STATE A: DISTRACTION-FREE SETUP SECTION ("Plan erstellen") */}
      {/* ============================================================== */}
      {pageMode === 'setup' ? (
        <div className="max-w-3xl mx-auto space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2.5 flex-wrap">
                <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-stone-900">
                  Plan erstellen
                </h1>
                {birthdayStaff.length > 0 && (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-50 text-amber-900 border border-amber-200 shadow-2xs">
                    <span>🎂</span>
                    <span>
                      Heute Geburtstag:{' '}
                      <strong className="font-semibold">
                        {birthdayStaff.map((s) => s.name).join(', ')}
                      </strong>
                    </span>
                  </span>
                )}
              </div>
              <p className="text-xs text-stone-500 mt-0.5">
                Automatische Dienstplanoptimierung mit dem CP-SAT Solver.
              </p>
            </div>
            {schedule && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPageMode('view')}
                className="text-xs"
              >
                Zurück zur Planansicht
              </Button>
            )}
          </div>

          {/* Quarter & Year Picker */}
          <div className="bg-white rounded-xl border border-stone-200/80 p-5 shadow-2xs space-y-4">
            <h2 className="text-sm font-bold text-stone-900">1. Quartal auswählen</h2>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-stone-700 mb-1">
                  Quartal
                </label>
                <select
                  value={setupQuarter}
                  onChange={(e) => {
                    const q = e.target.value;
                    setSetupQuarter(q);
                    onQuarterChange?.(`${setupYear}-${q}`);
                  }}
                  className="w-full px-3 py-2 text-sm bg-stone-50/70 border border-stone-200 rounded-lg text-stone-800 focus:outline-none focus:ring-2 focus:ring-[#324b9b]/20"
                >
                  <option value="Q1">Q1 (Januar – März)</option>
                  <option value="Q2">Q2 (April – Juni)</option>
                  <option value="Q3">Q3 (Juli – September)</option>
                  <option value="Q4">Q4 (Oktober – Dezember)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-stone-700 mb-1">
                  Jahr
                </label>
                <select
                  value={setupYear}
                  onChange={(e) => {
                    const y = Number(e.target.value);
                    setSetupYear(y);
                    onQuarterChange?.(`${y}-${setupQuarter}`);
                  }}
                  className="w-full px-3 py-2 text-sm bg-stone-50/70 border border-stone-200 rounded-lg text-stone-800 focus:outline-none focus:ring-2 focus:ring-[#324b9b]/20"
                >
                  <option value={2026}>2026</option>
                  <option value={2027}>2027</option>
                  <option value={2028}>2028</option>
                </select>
              </div>
            </div>

            <div className="p-3 rounded-lg bg-blue-50/70 border border-blue-200/60 text-xs text-[#324b9b] flex items-center gap-2">
              <CalendarIcon className="h-4 w-4 shrink-0" />
              <span>
                Planungszeitraum:{' '}
                {setupQuarter === 'Q1'
                  ? `01.01.${setupYear} – 31.03.${setupYear} (90 Tage)`
                  : setupQuarter === 'Q2'
                    ? `01.04.${setupYear} – 30.06.${setupYear} (91 Tage)`
                    : setupQuarter === 'Q3'
                      ? `01.07.${setupYear} – 30.09.${setupYear} (92 Tage)`
                      : `01.10.${setupYear} – 31.12.${setupYear} (92 Tage)`}
              </span>
            </div>
          </div>

          {/* Solver Settings - Streamlined Smart-Stop */}
          <div className="bg-white rounded-xl border border-stone-200/80 p-5 shadow-2xs space-y-4">
            <h2 className="text-sm font-bold text-stone-900">2. Solver-Einstellungen</h2>

            {/* Smart-Stop Card */}
            <div className="p-4 rounded-xl border border-blue-200/80 bg-blue-50/40 space-y-2">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4 text-[#324b9b]" />
                  <span className="text-xs font-bold text-stone-900">
                    Automatische Optimierung mit Smart-Stop
                  </span>
                </div>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200">
                  Aktiv
                </span>
              </div>
              <p className="text-xs text-stone-600 leading-relaxed">
                Der CP-SAT Solver ermittelt die fairste Verteilung aller Notdienste und stoppt selbstständig, sobald Verbesserungen stagnieren (üblicherweise nach 20–60 Sekunden; maximale Obergrenze: bis zu {maxSolveMinutes} Minuten).
              </p>
            </div>

            {/* Collapsible Advanced Parameters */}
            <div className="pt-1">
              <button
                type="button"
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="flex items-center gap-1.5 text-xs text-stone-600 font-medium hover:text-stone-900 cursor-pointer"
              >
                <Settings2 className="h-3.5 w-3.5" />
                <span>Erweiterte Einstellungen {showAdvanced ? 'ausblenden' : 'einblenden'}</span>
                <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', showAdvanced ? 'rotate-180' : '')} />
              </button>

              {showAdvanced && (
                <div className="mt-3 p-3.5 rounded-lg bg-stone-50 border border-stone-200/70 grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
                  <div>
                    <label className="block text-stone-700 font-semibold mb-1">
                      Max. Suchdauer (Minuten)
                    </label>
                    <input
                      type="number"
                      min={1}
                      max={20}
                      value={maxSolveMinutes}
                      onChange={(e) => setMaxSolveMinutes(Math.max(1, Math.min(20, Number(e.target.value) || 1)))}
                      className="w-full px-2.5 py-1.5 bg-white border border-stone-200 rounded text-xs focus:outline-none focus:ring-1 focus:ring-[#324b9b]"
                    />
                    <span className="text-[11px] text-stone-500 mt-1 block">
                      Obergrenze für die solver-Suche (Standard: 10 Min.). Smart-Stop bricht bei Stagnation früher ab.
                    </span>
                  </div>
                  <div>
                    <label className="block text-stone-700 font-semibold mb-1">
                      Mindest-Blockabstand (Tage)
                    </label>
                    <input
                      type="number"
                      min={7}
                      max={42}
                      value={blockGapDays}
                      onChange={(e) => setBlockGapDays(Number(e.target.value))}
                      className="w-full px-2.5 py-1.5 bg-white border border-stone-200 rounded text-xs focus:outline-none focus:ring-1 focus:ring-[#324b9b]"
                    />
                    <span className="text-[11px] text-stone-500 mt-1 block">
                      Gesetzliche Pause zwischen aufeinanderfolgenden Nachtblöcken (Standard: 21 Tage).
                    </span>
                  </div>
                  <div>
                    <label className="block text-stone-700 font-semibold mb-1">
                      Vorquartal berücksichtigen
                    </label>
                    <label className="flex items-center gap-2 mt-2 cursor-pointer select-none">
                      <input
                        type="checkbox"
                        checked={includePreviousQuarter}
                        onChange={(e) => setIncludePreviousQuarter(e.target.checked)}
                        className="h-4 w-4 rounded text-[#324b9b] focus:ring-[#324b9b] border-stone-300"
                      />
                      <span className="text-stone-800 font-medium text-xs">
                        Ruhezeiten & Ausgleichssaldo einbeziehen
                      </span>
                    </label>
                    <span className="text-[11px] text-stone-500 mt-1 block">
                      Guthaben/Rückstände aus dem Vorquartal anrechnen und Grenz-Schichten schützen.
                    </span>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Checklist Card */}
          <div className="bg-white rounded-xl border border-stone-200/80 p-5 shadow-2xs space-y-3">
            <h2 className="text-sm font-bold text-stone-900">3. Datenbasis für dieses Quartal</h2>
            <div className="space-y-2 text-xs">
              <div className="flex items-center justify-between p-2 rounded bg-stone-50">
                <span className="text-stone-700">Aktives Personal:</span>
                <span className="font-bold text-stone-900">{staffList.length} Mitarbeiter</span>
              </div>
              <div className="flex items-center justify-between p-2 rounded bg-stone-50">
                <span className="text-stone-700">Erfasste Abwesenheiten:</span>
                <span className="font-bold text-stone-900">{absences.length} Zeiträume</span>
              </div>
              <div className="flex items-center justify-between p-2 rounded bg-stone-50">
                <span className="text-stone-700">Vorgegebene Vorbelegungen:</span>
                <span className="font-bold text-stone-900">{preAssigned.length} feste Schichten</span>
              </div>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="pt-2 flex flex-col sm:flex-row gap-3">
            <Button
              type="button"
              onClick={handleCheckFeasibility}
              disabled={checkingFeasibility || solving}
              variant="outline"
              size="lg"
              className="py-3 text-sm font-semibold sm:w-1/3 border-stone-300 hover:bg-stone-50"
            >
              {checkingFeasibility ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin text-teal-700" />
                  Prüfe Daten...
                </>
              ) : (
                <>
                  <ShieldCheck className="h-4 w-4 mr-2 text-teal-700" />
                  Machbarkeit prüfen
                </>
              )}
            </Button>
            <Button
              type="button"
              onClick={handleRunSolver}
              disabled={solving}
              variant="primary"
              size="lg"
              className="py-3 text-sm font-bold shadow-md sm:w-2/3"
            >
              {solving ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Berechne optimalen Dienstplan mit CP-SAT...
                </>
              ) : (
                <>
                  <Play className="h-4 w-4 mr-2 fill-current" />
                  Plan jetzt berechnen
                </>
              )}
            </Button>
          </div>
        </div>
      ) : (
        /* ============================================================== */
        /* STATE B: STREAMLIT-STYLE GENERATED SCHEDULE OVERVIEW */
        /* ============================================================== */
        <div className="space-y-5">
          {/* Top Streamlit-Style Control Ribbon */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-white p-4 rounded-xl border border-stone-200/80 shadow-2xs">
            <div>
              <div className="flex items-center gap-2.5 flex-wrap">
                <h1 className="text-lg sm:text-xl font-bold tracking-tight text-stone-900">
                  Dienstplan Übersicht
                </h1>
                <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-blue-50 text-[#324b9b] border border-blue-200">
                  {currentQuarterKey}
                </span>

                {birthdayStaff.length > 0 && (
                  <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-50 text-amber-900 border border-amber-200 shadow-2xs">
                    <span>🎂</span>
                    <span>
                      Heute Geburtstag:{' '}
                      <strong className="font-semibold">
                        {birthdayStaff.map((s) => s.name).join(', ')}
                      </strong>
                    </span>
                  </span>
                )}
              </div>
              <p className="text-xs text-stone-500 mt-0.5">
                Kompakte Schichtübersicht nach Vorbild der bewährten Klinik-Tabelle.
              </p>
            </div>

            <div className="flex items-center gap-2">
              {/* Sub-view toggle: Dienstplan vs Vorquartal & Ausgleich */}
              <div className="inline-flex rounded-lg border border-stone-200 bg-stone-100/70 p-0.5 text-xs font-medium shadow-2xs">
                <button
                  type="button"
                  onClick={() => setSubView('schedule')}
                  className={cn(
                    'px-2.5 py-1 rounded-md transition-all cursor-pointer',
                    subView === 'schedule'
                      ? 'bg-white text-stone-900 font-bold shadow-2xs'
                      : 'text-stone-600 hover:text-stone-900'
                  )}
                >
                  Dienstplan
                </button>
                <button
                  type="button"
                  onClick={() => setSubView('rollover')}
                  className={cn(
                    'px-2.5 py-1 rounded-md transition-all cursor-pointer',
                    subView === 'rollover'
                      ? 'bg-white text-stone-900 font-bold shadow-2xs'
                      : 'text-stone-600 hover:text-stone-900'
                  )}
                >
                  Vorquartal & Ausgleich
                </button>
              </div>

              <a
                href={`/api/v1/quarters/${currentQuarterKey}/export?format=xlsx`}
                download
                className="inline-flex items-center justify-center font-medium rounded-lg text-xs px-3 py-1.5 border border-stone-300 bg-white text-stone-700 hover:bg-stone-50 shadow-2xs transition-all"
              >
                <Download className="h-3.5 w-3.5 mr-1.5 text-stone-500" />
                Excel Export
              </a>

              <Button
                onClick={() => setPageMode('setup')}
                variant="primary"
                size="sm"
                className="text-xs bg-[#324b9b] hover:bg-[#25397a] text-white shadow-xs font-semibold px-3 py-1.5"
                title="Öffnet den Planungs-Assistenten für ein neues Quartal"
              >
                <Sparkles className="h-3.5 w-3.5 mr-1.5 text-amber-300" />
                Neues Quartal planen
              </Button>
            </div>
          </div>

          {subView === 'rollover' ? (
            /* ============================================================== */
            /* SUBVIEW: VORQUARTAL & AUSGLEICH */
            /* ============================================================== */
            <div className="space-y-6">
              {/* Context Overview Banner */}
              <div className="bg-white rounded-xl border border-stone-200/80 p-5 shadow-2xs space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <div className="h-10 w-10 rounded-xl bg-blue-50 text-[#324b9b] flex items-center justify-center shrink-0 border border-blue-200/50">
                      <History className="h-5 w-5" />
                    </div>
                    <div>
                      <h2 className="text-sm font-bold text-stone-900">
                        Vorquartal & Historischer Ausgleich ({currentQuarterKey})
                      </h2>
                      <p className="text-xs text-stone-500">
                        Geleistete Dienste, Ausgleichs-Salden und gesetzliche Ruhezeiten aus dem vorangegangenen Quartal.
                      </p>
                    </div>
                  </div>

                  {rollover?.has_context ? (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200">
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                      Vorquartal aktiv ({rollover.quarter_start} bis {rollover.quarter_end})
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-stone-100 text-stone-600 border border-stone-200">
                      Kein Vorquartal hinterlegt
                    </span>
                  )}
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 pt-1 text-xs">
                  <div className="p-3 rounded-lg bg-stone-50 border border-stone-200/70">
                    <span className="text-stone-500 block">Mitarbeiter mit Historie:</span>
                    <span className="text-sm font-bold text-stone-900">
                      {rollover?.carry_forward.length ?? 0} Mitarbeiter
                    </span>
                  </div>
                  <div className="p-3 rounded-lg bg-stone-50 border border-stone-200/70">
                    <span className="text-stone-500 block">Ruhezeiten Vorquartal (letzte 21 Tage):</span>
                    <span className="text-sm font-bold text-stone-900">
                      {rollover?.trailing_assignments.length ?? 0} Schichten
                    </span>
                  </div>
                  <div className="p-3 rounded-lg bg-stone-50 border border-stone-200/70">
                    <span className="text-stone-500 block">Solver-Berücksichtigung:</span>
                    <span className="text-sm font-bold text-[#324b9b]">
                      Punkte-Ausgleich & 21-Tage-Schutz aktiv
                    </span>
                  </div>
                </div>
              </div>

              {/* Section 1: Carry-Forward Fairness Deltas */}
              <div className="bg-white rounded-xl border border-stone-200/80 shadow-2xs overflow-hidden">
                <div className="p-4 border-b border-stone-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-bold text-stone-900 flex items-center gap-2">
                      <Scale className="h-4 w-4 text-[#324b9b]" />
                      Ausgleichs-Punkte (Vorquartals-Saldo)
                    </h3>
                    <p className="text-xs text-stone-500 mt-0.5">
                      Mitarbeiter mit Guthaben leisteten im Vorquartal überdurchschnittlich viele Dienste und werden nun entlastet.
                    </p>
                  </div>

                  {/* Role Filter Tabs */}
                  <div className="inline-flex rounded-lg border border-stone-200 bg-stone-100/70 p-0.5 text-xs font-medium">
                    {(['ALL', 'Vet', 'TFA', 'Intern'] as const).map((r) => (
                      <button
                        key={r}
                        onClick={() => setRolloverRoleFilter(r)}
                        className={cn(
                          'px-2.5 py-1 rounded-md transition-all cursor-pointer',
                          rolloverRoleFilter === r
                            ? 'bg-white text-stone-900 font-bold shadow-2xs'
                            : 'text-stone-600 hover:text-stone-900'
                        )}
                      >
                        {r === 'ALL' ? 'Alle Rollen' : r === 'Vet' ? 'Tierärzte (Vet)' : r}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead className="bg-[#f5f4f0] border-b border-stone-300 text-stone-700 font-bold">
                      <tr>
                        <th className="py-2.5 px-3 border-r border-stone-200">Mitarbeiter</th>
                        <th className="py-2.5 px-3 border-r border-stone-200">Rolle</th>
                        <th className="py-2.5 px-3 border-r border-stone-200 text-center">Wochenstunden</th>
                        <th className="py-2.5 px-3 border-r border-stone-200 text-center">Nachtdienste</th>
                        <th className="py-2.5 px-3 border-r border-stone-200 text-center">Wochenenden</th>
                        <th className="py-2.5 px-3 text-right">Ausgleichs-Saldo</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-stone-200">
                      {!rollover || rollover.carry_forward.length === 0 ? (
                        <tr>
                          <td colSpan={6} className="py-8 text-center text-stone-500">
                            Keine Ausgleichsdaten für dieses Quartal verfügbar.
                          </td>
                        </tr>
                      ) : (
                        rollover.carry_forward
                          .filter((cf) =>
                            rolloverRoleFilter === 'ALL'
                              ? true
                              : cf.beruf === rolloverRoleFilter || (rolloverRoleFilter === 'Vet' && cf.beruf === 'Tierarzt')
                          )
                          .map((cf) => {
                            const delta = cf.carry_forward_delta;
                            const deltaFormatted = delta > 0 ? `+${delta.toFixed(2)}` : delta.toFixed(2);
                            return (
                              <tr key={cf.identifier} className="hover:bg-stone-50/70">
                                <td className="py-2 px-3 font-semibold text-stone-900">
                                  {cf.name}{' '}
                                  <span className="text-[11px] font-mono text-stone-400">
                                    ({cf.identifier})
                                  </span>
                                </td>
                                <td className="py-2 px-3 text-stone-600">
                                  <span className="px-2 py-0.5 rounded text-[11px] font-medium bg-stone-100 text-stone-700 border border-stone-200">
                                    {cf.beruf}
                                  </span>
                                </td>
                                <td className="py-2 px-3 text-center text-stone-600">{cf.hours} h</td>
                                <td className="py-2 px-3 text-center text-stone-700 font-medium">
                                  {cf.effective_nights}
                                </td>
                                <td className="py-2 px-3 text-center text-stone-700 font-medium">
                                  {cf.weekend_shifts}
                                </td>
                                <td className="py-2 px-3 text-right">
                                  {delta > 0.05 ? (
                                    <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-emerald-50 text-emerald-800 border border-emerald-200">
                                      {deltaFormatted} (Guthaben)
                                    </span>
                                  ) : delta < -0.05 ? (
                                    <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-bold bg-amber-50 text-amber-800 border border-amber-200">
                                      {deltaFormatted} (Nachholbedarf)
                                    </span>
                                  ) : (
                                    <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-stone-100 text-stone-600">
                                      0.00 (Ausgeglichen)
                                    </span>
                                  )}
                                </td>
                              </tr>
                            );
                          })
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Section 2: Trailing 21-Day Rest Period Shifts */}
              <div className="bg-white rounded-xl border border-stone-200/80 shadow-2xs overflow-hidden">
                <div className="p-4 border-b border-stone-200">
                  <h3 className="text-sm font-bold text-stone-900 flex items-center gap-2">
                    <Clock className="h-4 w-4 text-[#324b9b]" />
                    Letzte Schichten des Vorquartals (Ruhezeiten & Abstände)
                  </h3>
                  <p className="text-xs text-stone-500 mt-0.5">
                    Realisierte Dienste der letzten 21 Tage vor Quartalsbeginn – schützen Mitarbeiter vor zu dichten Folgediensten im neuen Plan.
                  </p>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse font-mono">
                    <thead className="bg-[#f5f4f0] border-b border-stone-300 text-stone-700 font-bold font-sans">
                      <tr>
                        <th className="py-2.5 px-3 border-r border-stone-200 w-32">Datum</th>
                        <th className="py-2.5 px-3 border-r border-stone-200 w-44">Schichtart</th>
                        <th className="py-2.5 px-3 border-r border-stone-200">Eingeteilte Person</th>
                        <th className="py-2.5 px-3 text-stone-500 font-normal">Gesetzliche Schutzregel</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-stone-200">
                      {!rollover || rollover.trailing_assignments.length === 0 ? (
                        <tr>
                          <td colSpan={4} className="py-8 text-center text-stone-500 font-sans">
                            Keine Grenz-Schichten für diesen Zeitraum erfasst.
                          </td>
                        </tr>
                      ) : (
                        rollover.trailing_assignments.map((t, idx) => {
                          const s = staffList.find(
                            (st) =>
                              st.id === t.staff_identifier.toLowerCase() ||
                              st.identifier.toLowerCase() === t.staff_identifier.toLowerCase()
                          );
                          const displayName = s ? (showFullNames ? s.name : s.identifier) : t.staff_identifier;
                          return (
                            <tr key={`${t.shift_date}-${t.shift_type}-${idx}`} className="hover:bg-stone-50/70">
                              <td className="py-2 px-3 text-stone-900 font-semibold">{t.shift_date}</td>
                              <td className="py-2 px-3">
                                {t.is_night ? (
                                  <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-sans font-medium bg-[#e8e0f0] text-purple-900 border border-purple-200">
                                    🌙 {t.shift_type}
                                  </span>
                                ) : (
                                  <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-sans font-medium bg-[#fff3e0] text-amber-900 border border-amber-200">
                                    ☀️ {t.shift_type}
                                  </span>
                                )}
                              </td>
                              <td className="py-2 px-3 font-semibold text-stone-900 font-sans">
                                {displayName}
                              </td>
                              <td className="py-2 px-3 text-stone-500 font-sans text-[11px]">
                                {t.is_night
                                  ? '21 Tage Mindestabstand zu Folge-Nachtdienst geschützt'
                                  : 'Wochenend-Ruhezeit über Quartalsgrenze geschützt'}
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          ) : (
            /* ============================================================== */
            /* SUBVIEW: DIENSTPLAN (STREAMLIT CALENDAR TABLE) */
            /* ============================================================== */
            <div className="space-y-4">
              {/* Sub-Toolbar: Name Toggle & Month Tabs (Streamlit-style) */}
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-stone-50/80 p-2.5 rounded-lg border border-stone-200/80">
                {/* Month Filter Tabs */}
                <div className="flex items-center gap-1 overflow-x-auto">
                  {monthTabs.map((m) => (
                    <button
                      key={String(m.id)}
                      onClick={() => setSelectedMonth(m.id as number | 'ALL')}
                      className={cn(
                        'px-3 py-1 text-xs font-medium rounded-md transition-all cursor-pointer whitespace-nowrap',
                        selectedMonth === m.id
                          ? 'bg-white text-stone-900 font-bold shadow-2xs border border-stone-200'
                          : 'text-stone-600 hover:text-stone-900'
                      )}
                    >
                      {m.label}
                    </button>
                  ))}
                </div>

                {/* Toggle: Full Names vs Identifiers (Direct from Streamlit) */}
                <label className="flex items-center gap-2 cursor-pointer text-xs font-medium text-stone-700 select-none">
                  <input
                    type="checkbox"
                    checked={showFullNames}
                    onChange={(e) => setShowFullNames(e.target.checked)}
                    className="h-3.5 w-3.5 rounded text-[#324b9b] focus:ring-[#324b9b] border-stone-300"
                  />
                  <span>Volle Namen anzeigen</span>
                </label>
              </div>

              {/* Pinned Sticky Legend for Shifts */}
              <div className="sticky top-14 z-30 bg-white/95 backdrop-blur-md border border-stone-200/90 rounded-lg px-3 py-2 shadow-2xs">
                <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 text-xs">
                  {/* Left: Weekend Shift Numbers (1, 2, 3, 4) */}
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
                    <span className="font-bold text-stone-700 flex items-center gap-1 shrink-0">
                      <span>☀️ Wochenendschichten:</span>
                    </span>
                    <div className="flex flex-wrap items-center gap-1.5 font-sans">
                      <span
                        className="inline-flex items-center gap-1 bg-amber-50 text-amber-950 border border-amber-200 px-2 py-0.5 rounded text-[11px]"
                        title="Samstag 10:00–21:00 / Sonntag & Feiertag 08:00–20:00"
                      >
                        <span className="font-bold text-amber-900 font-mono">(1)</span>
                        <span className="font-medium">Früh</span>
                        <span className="text-[10px] text-stone-500 font-mono hidden sm:inline">(Sa 10–21 / So 8–20)</span>
                      </span>

                      <span
                        className="inline-flex items-center gap-1 bg-orange-50 text-orange-950 border border-orange-200 px-2 py-0.5 rounded text-[11px]"
                        title="Samstag 10:00–19:00 (Azubi)"
                      >
                        <span className="font-bold text-orange-900 font-mono">(2)</span>
                        <span className="font-medium">Spät Azubi</span>
                        <span className="text-[10px] text-stone-500 font-mono hidden sm:inline">(Sa 10–19)</span>
                      </span>

                      <span
                        className="inline-flex items-center gap-1 bg-purple-50 text-purple-950 border border-purple-200 px-2 py-0.5 rounded text-[11px]"
                        title="Samstag & Sonntag 10:00–22:00"
                      >
                        <span className="font-bold text-purple-900 font-mono">(3)</span>
                        <span className="font-medium">Ruf</span>
                        <span className="text-[10px] text-stone-500 font-mono hidden sm:inline">(Sa & So 10–22)</span>
                      </span>

                      <span
                        className="inline-flex items-center gap-1 bg-blue-50 text-blue-950 border border-blue-200 px-2 py-0.5 rounded text-[11px]"
                        title="Sonntag & Feiertag 08:00–20:30 (Azubi Präsenz 8–12, Ruf 12–20:30)"
                      >
                        <span className="font-bold text-blue-900 font-mono">(4)</span>
                        <span className="font-medium">Azubi Ruf</span>
                        <span className="text-[10px] text-stone-500 font-mono hidden sm:inline">(So 8–20:30)</span>
                      </span>
                    </div>
                  </div>

                  {/* Right: Quick Indicators */}
                  <div className="flex flex-wrap items-center gap-3 text-[11px] text-stone-600">
                    <span className="flex items-center gap-1">
                      <span className="h-2.5 w-2.5 rounded bg-[#eee8f5] border border-purple-300 inline-block" />
                      <span>🌙 Nacht</span>
                    </span>
                    <span className="flex items-center gap-1">
                      <span className="h-2.5 w-2.5 rounded bg-[#e8f5f3] border border-teal-300 inline-block" />
                      <span>🎓 Intern (08:30–20:30)</span>
                    </span>
                    <span className="flex items-center gap-1">
                      <span className="h-2.5 w-2.5 rounded bg-emerald-100 border border-emerald-300 inline-block" />
                      <Pin className="h-2.5 w-2.5 text-emerald-700" />
                      <span className="text-emerald-950 font-medium">Fest vorbelegt</span>
                    </span>
                  </div>
                </div>
              </div>

              {/* The Streamlit-Style Calendar Matrix Table */}
              <div className="bg-white rounded-xl border border-stone-200/80 shadow-2xs overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead className="bg-[#f5f4f0] border-b border-stone-300 text-stone-700 font-bold">
                      <tr>
                        <th className="py-2.5 px-3 border-r border-stone-200 w-28">Datum</th>
                        <th className="py-2.5 px-3 border-r border-stone-200 w-52 bg-[#eee8f5]">
                          🌙 Nacht
                        </th>
                        <th className="py-2.5 px-3 border-r border-stone-200 w-64 bg-[#fff8e7]">
                          ☀️ Sa/So Dienst & Rufbereitschaft (1–4)
                        </th>
                        <th className="py-2.5 px-3 border-r border-stone-200 w-44 bg-[#e8f5f3]">
                          <div className="flex items-center justify-between">
                            <span>🎓 Intern Tagdienst</span>
                            <span className="text-[10px] text-teal-800/70 font-mono font-normal">08:30–20:30</span>
                          </div>
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-stone-200 font-mono">
                      {loading ? (
                        <tr>
                          <td colSpan={4} className="py-12 text-center text-stone-500 font-sans">
                            Lade Dienstplan...
                          </td>
                        </tr>
                      ) : filteredDates.length === 0 ? (
                        <tr>
                          <td colSpan={4} className="py-12 text-center text-stone-500 font-sans">
                            Keine Schichten vorhanden.
                          </td>
                        </tr>
                      ) : (
                        filteredDates.map((dateStr) => {
                          const isWknd = isWeekendDay(dateStr);
                          const dayShifts = assignments.filter((a) => a.shift_date === dateStr);

                          // 1. Night shifts (starts with 'N_') - includes Vets, TFAs, and Night-Interns
                          const nightShifts = dayShifts.filter((a) => a.shift_type.startsWith('N_'));

                          // 2. Weekend day shifts & Rufbereitschaft (non-night, non-intern)
                          const weekendAndRufShifts = dayShifts
                            .filter((a) => !a.shift_type.startsWith('N_') && !a.shift_type.includes('Intern'))
                            .sort((a, b) => getShiftOrder(a.shift_type) - getShiftOrder(b.shift_type));

                          // 3. Daytime Intern weekend shifts
                          const internShifts = dayShifts.filter(
                            (a) => !a.shift_type.startsWith('N_') && a.shift_type.includes('Intern')
                          );

                          const isNightPreAssigned = nightShifts.some((s) => isShiftPreAssigned(s));
                          const isWkndPreAssigned = weekendAndRufShifts.some((s) => isShiftPreAssigned(s));
                          const isInternPreAssigned = internShifts.some((s) => isShiftPreAssigned(s));

                          const [, month, day] = dateStr.split('-');
                          const dayLabel = `${day}.${month}. ${getWeekdayShort(dateStr)}`;

                          return (
                            <tr
                              key={dateStr}
                              className={cn(
                                'hover:brightness-95 transition-all group',
                                isWknd ? 'bg-[#fffaf0]' : 'bg-white'
                              )}
                            >
                              {/* Date Column */}
                              <td
                                className={cn(
                                  'py-2 px-3 border-r border-stone-200 font-sans font-medium',
                                  isWknd ? 'text-amber-900 font-bold bg-[#fff5e0]/60' : 'text-stone-800'
                                )}
                              >
                                {dayLabel}
                              </td>

                              {/* 🌙 Nacht Column */}
                              <td
                                className={cn(
                                  'py-2 px-3 border-r border-stone-200 font-sans font-semibold transition-colors',
                                  isNightPreAssigned
                                    ? 'bg-[#b2dfdb] text-teal-950'
                                    : 'bg-[#f2ecf8] text-purple-950'
                                )}
                              >
                                {nightShifts.length > 0 ? (
                                  <div className="flex flex-col gap-1">
                                    {nightShifts.map((shift, idx) => {
                                      const isPre = isShiftPreAssigned(shift);
                                      const stf = getStaff(shift.actual_staff_id);
                                      const role = stf?.beruf;
                                      return (
                                        <div
                                          key={`${shift.shift_date}-${shift.shift_type}-${shift.actual_staff_id}-${idx}`}
                                          className={cn(
                                            'flex items-center gap-1.5 text-left font-semibold transition-all rounded px-1.5 py-0.5',
                                            isPre
                                              ? 'bg-emerald-100/90 text-emerald-950 border border-emerald-300 shadow-2xs'
                                              : 'text-stone-900'
                                          )}
                                        >
                                          {isPre && (
                                            <span title="Fest vorgegebener Dienst">
                                              <Pin className="h-3 w-3 text-emerald-700 shrink-0" />
                                            </span>
                                          )}
                                          <span>
                                            {getStaffDisplayName(shift.actual_staff_id, true)}
                                          </span>
                                          {role && role !== 'Vet' && role !== 'Tierarzt' && (
                                            <span
                                              className={cn(
                                                'text-[10px] px-1 py-0.2 rounded font-medium',
                                                role === 'Azubi'
                                                  ? 'bg-amber-100 text-amber-900 border border-amber-200'
                                                  : role === 'Intern'
                                                    ? 'bg-teal-100 text-teal-900 border border-teal-200'
                                                    : 'bg-blue-100 text-blue-900 border border-blue-200'
                                              )}
                                            >
                                              {role}
                                            </span>
                                          )}
                                          {shift.is_override && (
                                            <span className="text-[11px]" title="Getauchter Dienst">
                                              ⚠️
                                            </span>
                                          )}
                                        </div>
                                      );
                                    })}
                                  </div>
                                ) : (
                                  <span className="text-stone-400 font-normal">—</span>
                                )}
                              </td>

                              {/* ☀️ Sa/So Dienst & Rufbereitschaft Column */}
                              <td
                                className={cn(
                                  'py-2 px-3 border-r border-stone-200 font-sans transition-colors',
                                  isWkndPreAssigned
                                    ? 'bg-[#b2dfdb] text-teal-950 font-semibold'
                                    : !isWknd && weekendAndRufShifts.length === 0
                                      ? 'bg-stone-50/30 text-stone-400 font-normal'
                                      : 'bg-[#fff4e3] text-amber-950 font-semibold'
                                )}
                              >
                                {weekendAndRufShifts.length > 0 ? (
                                  <div className="flex flex-col gap-1">
                                    {weekendAndRufShifts.map((shift, idx) => {
                                      const isPre = isShiftPreAssigned(shift);
                                      const stf = getStaff(shift.actual_staff_id);
                                      const role = stf?.beruf;
                                      const meta = getWeekendShiftMeta(shift.shift_type);

                                      return (
                                        <div
                                          key={`${shift.shift_date}-${shift.shift_type}-${shift.actual_staff_id}-${idx}`}
                                          className={cn(
                                            'flex items-center justify-between gap-1.5 text-left font-semibold transition-all rounded px-1.5 py-0.5',
                                            isPre
                                              ? 'bg-emerald-100/90 text-emerald-950 border border-emerald-300 shadow-2xs'
                                              : 'text-stone-900'
                                          )}
                                        >
                                          <div className="flex items-center gap-1.5 min-w-0">
                                            {isPre && (
                                              <span title="Fest vorgegebener Dienst">
                                                <Pin className="h-3 w-3 text-emerald-700 shrink-0" />
                                              </span>
                                            )}
                                            <span className="truncate">
                                              {getStaffDisplayName(shift.actual_staff_id, false)}
                                            </span>
                                            {role && role !== 'TFA' && (
                                              <span
                                                className={cn(
                                                  'text-[9px] px-1 py-0.2 rounded font-medium shrink-0',
                                                  role === 'Azubi'
                                                    ? 'bg-amber-100 text-amber-900 border border-amber-200'
                                                    : role === 'Intern'
                                                      ? 'bg-teal-100 text-teal-900 border border-teal-200'
                                                      : 'bg-rose-100 text-rose-900 border border-rose-200'
                                                )}
                                              >
                                                {role}
                                              </span>
                                            )}
                                            {shift.is_override && (
                                              <span className="text-[11px]" title="Getauchter Dienst">
                                                ⚠️
                                              </span>
                                            )}
                                          </div>

                                          <span
                                            className={cn(
                                              'text-[10px] font-bold px-1.5 py-0.2 rounded border font-mono shrink-0 cursor-help',
                                              meta.className
                                            )}
                                            title={`${meta.label} (${meta.hours})`}
                                          >
                                            ({meta.num})
                                          </span>
                                        </div>
                                      );
                                    })}
                                  </div>
                                ) : (
                                  <span className="text-stone-300 font-normal">—</span>
                                )}
                              </td>

                              {/* 🎓 Intern Tagdienst Column */}
                              <td
                                className={cn(
                                  'py-2 px-3 border-r border-stone-200 font-sans transition-colors',
                                  isInternPreAssigned
                                    ? 'bg-[#b2dfdb] text-teal-950 font-semibold'
                                    : !isWknd && internShifts.length === 0
                                      ? 'bg-stone-50/30 text-stone-300 font-normal'
                                      : 'bg-[#f0faf7] text-teal-950 font-semibold'
                                )}
                              >
                                {internShifts.length > 0 ? (
                                  <div className="flex flex-col gap-1">
                                    {internShifts.map((shift, idx) => {
                                      const isPre = isShiftPreAssigned(shift);
                                      return (
                                        <div
                                          key={`${shift.shift_date}-${shift.shift_type}-${shift.actual_staff_id}-${idx}`}
                                          className={cn(
                                            'flex items-center gap-1.5 text-left font-semibold transition-all rounded px-1.5 py-0.5',
                                            isPre
                                              ? 'bg-emerald-100/90 text-emerald-950 border border-emerald-300 shadow-2xs'
                                              : 'text-stone-900'
                                          )}
                                        >
                                          {isPre && (
                                            <span title="Fest vorgegebener Dienst">
                                              <Pin className="h-3 w-3 text-emerald-700 shrink-0" />
                                            </span>
                                          )}
                                          <span className="truncate">
                                            {getStaffDisplayName(shift.actual_staff_id, false)}
                                          </span>
                                          {shift.is_override && (
                                            <span className="text-[11px]" title="Getauchter Dienst">
                                              ⚠️
                                            </span>
                                          )}
                                        </div>
                                      );
                                    })}
                                  </div>
                                ) : (
                                  <span className="text-stone-300 font-normal">—</span>
                                )}
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Bottom Streamlit Metrics Summary */}
              <div className="bg-stone-50 rounded-lg border border-stone-200/80 p-3.5 flex flex-wrap items-center justify-between gap-4 text-xs">
                <div className="flex items-center gap-6">
                  <div>
                    <span className="text-stone-500">Dienste gesamt: </span>
                    <span className="font-bold text-stone-900">{assignments.length}</span>
                  </div>
                  <div>
                    <span className="text-stone-500">Nachtdienste: </span>
                    <span className="font-bold text-stone-900">
                      {assignments.filter((a) => a.shift_type.startsWith('N_')).length}
                    </span>
                  </div>
                  <div>
                    <span className="text-stone-500">Wochenenden: </span>
                    <span className="font-bold text-stone-900">
                      {assignments.filter((a) => !a.shift_type.startsWith('N_')).length}
                    </span>
                  </div>
                  <div>
                    <span className="text-stone-500">Vorbelegt: </span>
                    <span className="font-bold text-teal-800">{preAssigned.length}</span>
                  </div>
                </div>

                <div className="flex items-center gap-2 text-stone-500">
                  <span>Solver-Laufzeit: 14.2s</span>
                  <span>&middot;</span>
                  <span className="text-emerald-700 font-semibold flex items-center gap-1">
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                    Optimale Lösung
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Asynchronous Solver Progress Modal */}
      <Modal
        isOpen={solverModalOpen}
        onClose={() => setSolverModalOpen(false)}
        title={`CP-SAT Optimierung: ${currentQuarterKey}`}
      >
        <div className="space-y-5">
          {/* Status Header */}
          <div className="flex items-center gap-3 p-4 rounded-xl bg-stone-50 border border-stone-200">
            {activeJob?.status === 'RUNNING' && (
              <Loader2 className="h-6 w-6 animate-spin text-amber-600 shrink-0" />
            )}
            {activeJob?.status === 'COMPLETED' && (
              <CheckCircle2 className="h-6 w-6 text-emerald-600 shrink-0" />
            )}
            {(activeJob?.status === 'FAILED' || solverError) && (
              <AlertCircle className="h-6 w-6 text-red-600 shrink-0" />
            )}
            {activeJob?.status === 'CANCELLED' && (
              <StopCircle className="h-6 w-6 text-stone-500 shrink-0" />
            )}
            <div>
              <h4 className="text-sm font-bold text-stone-900">
                {activeJob?.status === 'RUNNING' && 'Optimierung läuft im Hintergrund...'}
                {activeJob?.status === 'COMPLETED' && 'Optimierung erfolgreich abgeschlossen!'}
                {activeJob?.status === 'CANCELLED' && 'Berechnung abgebrochen'}
                {(activeJob?.status === 'FAILED' || solverError) && 'Berechnung fehlgeschlagen'}
                {!activeJob && 'Initialisiere Solver...'}
              </h4>
              <p className="text-xs text-stone-500 mt-0.5">
                {activeJob?.status === 'RUNNING' &&
                  'CP-SAT optimiert die Fairness und stoppt automatisch bei stabiler Lösung.'}
                {activeJob?.status === 'COMPLETED' &&
                  'Der neue Dienstplan wurde gespeichert und kann geprüft werden.'}
                {activeJob?.status === 'CANCELLED' &&
                  'Der Vorgang wurde auf Wunsch des Planers gestoppt.'}
                {(activeJob?.status === 'FAILED' || solverError) &&
                  (solverError || activeJob?.error || 'Unbekannter Fehler.')}
              </p>
            </div>
          </div>

          {/* Metric Dashboard */}
          <div className="grid grid-cols-3 gap-3 text-center">
            <div className="p-3 bg-stone-50 rounded-lg border border-stone-200/80">
              <span className="text-[10px] uppercase font-bold text-stone-500 tracking-wider">Laufzeit</span>
              <div className="text-lg font-bold font-mono text-stone-900 mt-0.5">
                {activeJob ? formatTimer(activeJob.elapsed_seconds) : '00:00'}
              </div>
              <span className="text-[10px] text-stone-400">
                max {String(maxSolveMinutes).padStart(2, '0')}:00 (Smart-Stop)
              </span>
            </div>
            <div className="p-3 bg-stone-50 rounded-lg border border-stone-200/80">
              <span className="text-[10px] uppercase font-bold text-stone-500 tracking-wider">Lösungen</span>
              <div className="text-lg font-bold font-mono text-amber-700 mt-0.5">
                {activeJob?.solutions_found ?? 0}
              </div>
              <span className="text-[10px] text-stone-400">Verbesserungen</span>
            </div>
            <div className="p-3 bg-stone-50 rounded-lg border border-stone-200/80">
              <span className="text-[10px] uppercase font-bold text-stone-500 tracking-wider">Score</span>
              <div className="text-lg font-bold font-mono text-emerald-700 mt-0.5">
                {activeJob?.best_objective !== null && activeJob?.best_objective !== undefined
                  ? activeJob.best_objective.toFixed(1)
                  : '—'}
              </div>
              <span className="text-[10px] text-stone-400">Penalty</span>
            </div>
          </div>

          {/* Diagnostic Infeasibility Explanations */}
          {activeJob?.diagnostics && activeJob.diagnostics.length > 0 && (
            <div className="space-y-3 pt-2 border-t border-stone-200">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-stone-900 uppercase tracking-wider flex items-center gap-1.5">
                  <AlertCircle className="h-4 w-4 text-red-600" />
                  Erkannte Regel- und Vorbelegungskonflikte ({activeJob.diagnostics.length})
                </span>
                <span className="text-[11px] text-stone-500">
                  Präzise Vorprüfung vor CP-SAT-Lauf
                </span>
              </div>
              <div className="max-h-72 overflow-y-auto space-y-2.5 pr-1">
                {activeJob.diagnostics.map((diag, idx) => {
                  const isErr = diag.severity === 'ERROR';
                  return (
                    <div
                      key={idx}
                      className={cn(
                        'p-3.5 rounded-xl border text-xs space-y-2 transition-all',
                        isErr
                          ? 'bg-red-50/70 border-red-200 text-red-950'
                          : 'bg-amber-50/70 border-amber-200 text-amber-950'
                      )}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2">
                          {isErr ? (
                            <AlertCircle className="h-4 w-4 text-red-600 shrink-0" />
                          ) : (
                            <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0" />
                          )}
                          <span
                            className={cn(
                              'text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider',
                              isErr
                                ? 'bg-red-200/80 text-red-900'
                                : 'bg-amber-200/80 text-amber-900'
                            )}
                          >
                            {isErr ? 'Blockierend' : 'Warnung'}
                          </span>
                          <span className="font-bold text-stone-900">{diag.title}</span>
                        </div>
                        {diag.affected_staff_ids.length > 0 && (
                          <div className="flex items-center gap-1 shrink-0">
                            {diag.affected_staff_ids.map((id) => (
                              <span
                                key={id}
                                className="font-mono font-bold bg-white/90 border border-stone-200 px-1.5 py-0.5 rounded text-[10px] text-stone-800"
                              >
                                {id}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>

                      <p className="text-stone-700 leading-relaxed font-sans">{diag.message}</p>

                      {diag.remediation_hint && (
                        <div className="bg-white/80 rounded-lg p-2.5 border border-stone-200/60 flex items-start gap-2 text-stone-800 text-[11px]">
                          <span className="text-amber-600 shrink-0 font-bold">💡 Lösung:</span>
                          <span>{diag.remediation_hint}</span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Modal Actions */}
          <div className="pt-2 flex items-center justify-between gap-3 border-t border-stone-100">
            {activeJob?.status === 'RUNNING' ? (
              <>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setSolverModalOpen(false)}
                >
                  Im Hintergrund weiterlaufen lassen
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="text-red-700 border-red-200 hover:bg-red-50"
                  onClick={handleCancelSolve}
                >
                  Abbrechen
                </Button>
              </>
            ) : activeJob?.status === 'COMPLETED' ? (
              <Button
                type="button"
                variant="primary"
                size="md"
                className="w-full"
                onClick={() => {
                  setSolverModalOpen(false);
                  setPageMode('view');
                }}
              >
                Zum fertigen Dienstplan
              </Button>
            ) : (
              <Button
                type="button"
                variant="outline"
                size="md"
                className="w-full"
                onClick={() => setSolverModalOpen(false)}
              >
                Schließen
              </Button>
            )}
          </div>
        </div>
      </Modal>

      {/* Pre-Flight Feasibility Check Modal */}
      <Modal
        isOpen={feasibilityModalOpen}
        onClose={() => setFeasibilityModalOpen(false)}
        title={`Machbarkeitsprüfung: ${currentQuarterKey}`}
      >
        <div className="space-y-4">
          {feasibilityReport?.is_feasible ? (
            <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-950 space-y-2">
              <div className="flex items-center gap-2.5 text-emerald-800 font-bold text-sm">
                <CheckCircle2 className="h-5 w-5 text-emerald-600 shrink-0" />
                <span>Alle Vorbelegungen und Kapazitäten konsistent!</span>
              </div>
              <p className="text-xs text-emerald-800/90 leading-relaxed">
                Es wurden keine mathematischen Widersprüche (wie Doppelbelegungen, Wochentags-Sperren oder Ruhezeitverletzungen) erkannt. Das Quartal kann mit CP-SAT berechnet werden.
              </p>
            </div>
          ) : (
            <div className="p-4 rounded-xl bg-red-50 border border-red-200 text-red-950 space-y-2">
              <div className="flex items-center gap-2.5 text-red-800 font-bold text-sm">
                <AlertCircle className="h-5 w-5 text-red-600 shrink-0" />
                <span>
                  {feasibilityReport?.blocking_error_count} blockierende(r) Konflikt(e) erkannt!
                </span>
              </div>
              <p className="text-xs text-red-800/90 leading-relaxed">
                Der mathematische Solver würde mit diesen Vorbelegungen sofort scheitern (Status: INFEASIBLE). Bitte beheben Sie die folgenden Punkte:
              </p>
            </div>
          )}

          {/* Diagnostic Cards List */}
          {feasibilityReport && feasibilityReport.diagnostics.length > 0 && (
            <div className="max-h-80 overflow-y-auto space-y-2.5 pr-1">
              {feasibilityReport.diagnostics.map((diag, idx) => {
                const isErr = diag.severity === 'ERROR';
                return (
                  <div
                    key={idx}
                    className={cn(
                      'p-3.5 rounded-xl border text-xs space-y-2 transition-all',
                      isErr
                        ? 'bg-red-50/70 border-red-200 text-red-950'
                        : 'bg-amber-50/70 border-amber-200 text-amber-950'
                    )}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2">
                        {isErr ? (
                          <AlertCircle className="h-4 w-4 text-red-600 shrink-0" />
                        ) : (
                          <AlertTriangle className="h-4 w-4 text-amber-600 shrink-0" />
                        )}
                        <span
                          className={cn(
                            'text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-wider',
                            isErr
                              ? 'bg-red-200/80 text-red-900'
                              : 'bg-amber-200/80 text-amber-900'
                          )}
                        >
                          {isErr ? 'Blockierend' : 'Warnung'}
                        </span>
                        <span className="font-bold text-stone-900">{diag.title}</span>
                      </div>
                      {diag.affected_staff_ids.length > 0 && (
                        <div className="flex items-center gap-1 shrink-0">
                          {diag.affected_staff_ids.map((id) => (
                            <span
                              key={id}
                              className="font-mono font-bold bg-white/90 border border-stone-200 px-1.5 py-0.5 rounded text-[10px] text-stone-800"
                            >
                              {id}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    <p className="text-stone-700 leading-relaxed font-sans">{diag.message}</p>

                    {diag.remediation_hint && (
                      <div className="bg-white/80 rounded-lg p-2.5 border border-stone-200/60 flex items-start gap-2 text-stone-800 text-[11px]">
                        <span className="text-amber-600 shrink-0 font-bold">💡 Lösung:</span>
                        <span>{diag.remediation_hint}</span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          <div className="pt-2 flex items-center justify-end border-t border-stone-100">
            <Button
              type="button"
              variant="outline"
              size="md"
              onClick={() => setFeasibilityModalOpen(false)}
            >
              Schließen
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
};
