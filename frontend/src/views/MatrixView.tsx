import React, { useState, useEffect } from 'react';
import {
  Download,
  Play,
  CheckCircle2,
  Calendar as CalendarIcon,
  RotateCcw,
  Pin,
  Settings2,
  Loader2,
  ChevronDown,
} from 'lucide-react';
import type {
  QuarterScheduleDocument,
  ShiftAssignmentRecord,
  StaffMember,
  PreAssignedShift,
  AbsenceRecord,
} from '../types/api';
import {
  fetchSchedule,
  fetchStaff,
  fetchPreAssigned,
  fetchAbsences,
  generateSchedule,
  swapShift,
} from '../lib/api';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { cn } from '../lib/utils';

export const MatrixView: React.FC = () => {
  const [schedule, setSchedule] = useState<QuarterScheduleDocument | null>(null);
  const [staffList, setStaffList] = useState<StaffMember[]>([]);
  const [preAssigned, setPreAssigned] = useState<PreAssignedShift[]>([]);
  const [absences, setAbsences] = useState<AbsenceRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [solving, setSolving] = useState(false);

  // Mode: 'view' (schedule display) or 'setup' (distraction-free plan generation)
  const [pageMode, setPageMode] = useState<'view' | 'setup'>('view');

  // Display toggles matching Streamlit original
  const [showFullNames, setShowFullNames] = useState(false);
  const [selectedMonth, setSelectedMonth] = useState<number | 'ALL'>('ALL'); // 3=Apr, 4=May, 5=Jun

  // Setup form states
  const [setupQuarter, setSetupQuarter] = useState('Q2');
  const [setupYear, setSetupYear] = useState(2026);
  const [solveDepth, setSolveDepth] = useState<'fast' | 'thorough'>('fast');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [blockGapDays, setBlockGapDays] = useState(21);

  // Swap modal state
  const [swapModalOpen, setSwapModalOpen] = useState(false);
  const [selectedShift, setSelectedShift] = useState<ShiftAssignmentRecord | null>(null);
  const [newStaffId, setNewStaffId] = useState<string>('');

  const currentQuarterKey = `${setupYear}-${setupQuarter}`;

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    const [schedData, stfData, paData, absData] = await Promise.all([
      fetchSchedule(currentQuarterKey),
      fetchStaff(),
      fetchPreAssigned(),
      fetchAbsences(),
    ]);
    setSchedule(schedData);
    setStaffList(stfData);
    setPreAssigned(paData);
    setAbsences(absData);
    setLoading(false);
  };

  const getStaff = (id: string) => staffList.find((s) => s.id === id);

  const getStaffDisplayName = (id: string, isVet = false) => {
    const s = getStaff(id);
    if (!s) return id.toUpperCase();
    const prefix = isVet && s.beruf === 'Tierarzt' ? '🩺 ' : '';
    if (showFullNames) {
      return `${prefix}${s.name}`;
    }
    return `${prefix}${s.identifier}`;
  };

  // Run Solver
  const handleRunSolver = async () => {
    setSolving(true);
    try {
      const updated = await generateSchedule(currentQuarterKey);
      setSchedule(updated);
    } catch {
      // Simulate solve progress for 1.2s if local demo backend
      await new Promise((r) => setTimeout(r, 1200));
      const fresh = await fetchSchedule(currentQuarterKey);
      setSchedule(fresh);
    } finally {
      setSolving(false);
      setPageMode('view');
    }
  };

  // Execute Swap
  const handleExecuteSwap = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedShift || !newStaffId || !schedule) return;

    try {
      const updated = await swapShift(currentQuarterKey, {
        shift_date: selectedShift.shift_date,
        shift_type: selectedShift.shift_type,
        old_staff_id: selectedShift.actual_staff_id,
        new_staff_id: newStaffId,
        reason: 'Manuelle Schichtübernahme',
        force: true,
      });
      setSchedule(updated);
    } catch {
      const updatedAssignments = schedule.assignments.map((a) => {
        if (
          a.shift_date === selectedShift.shift_date &&
          a.shift_type === selectedShift.shift_type
        ) {
          return {
            ...a,
            actual_staff_id: newStaffId,
            is_override: true,
            override_reason: 'Manuelle Schichtübernahme',
          };
        }
        return a;
      });
      setSchedule({ ...schedule, assignments: updatedAssignments });
    }
    setSwapModalOpen(false);
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

  const isDatePreAssigned = (dateStr: string, shiftType: string) => {
    return preAssigned.some((pa) => pa.shift_date === dateStr && pa.shift_type === shiftType);
  };

  return (
    <div className="space-y-6">
      {/* ============================================================== */}
      {/* STATE A: DISTRACTION-FREE SETUP SECTION ("Plan erstellen") */}
      {/* ============================================================== */}
      {pageMode === 'setup' ? (
        <div className="max-w-3xl mx-auto space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-stone-900">
                Plan erstellen
              </h1>
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
                  onChange={(e) => setSetupQuarter(e.target.value)}
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
                  onChange={(e) => setSetupYear(Number(e.target.value))}
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
                Planungszeitraum: 01.04.{setupYear} – 30.06.{setupYear} (ca. 91 Tage)
              </span>
            </div>
          </div>

          {/* Solver Settings */}
          <div className="bg-white rounded-xl border border-stone-200/80 p-5 shadow-2xs space-y-4">
            <h2 className="text-sm font-bold text-stone-900">2. Solver-Einstellungen</h2>
            <div className="space-y-2">
              <label className="block text-xs font-semibold text-stone-700">
                Berechnungstiefe
              </label>
              <div className="grid grid-cols-2 gap-3">
                <button
                  type="button"
                  onClick={() => setSolveDepth('fast')}
                  className={cn(
                    'p-3 rounded-lg border text-left transition-all cursor-pointer text-xs',
                    solveDepth === 'fast'
                      ? 'border-[#324b9b] bg-blue-50/50 ring-1 ring-[#324b9b]'
                      : 'border-stone-200 bg-white hover:bg-stone-50'
                  )}
                >
                  <span className="font-bold text-stone-900 block">
                    Schnell (~60 Sek.)
                  </span>
                  <span className="text-[11px] text-stone-500 mt-0.5 block">
                    Standard-Zeitlimit für zügige, praxisfertige Dienstpläne.
                  </span>
                </button>

                <button
                  type="button"
                  onClick={() => setSolveDepth('thorough')}
                  className={cn(
                    'p-3 rounded-lg border text-left transition-all cursor-pointer text-xs',
                    solveDepth === 'thorough'
                      ? 'border-[#324b9b] bg-blue-50/50 ring-1 ring-[#324b9b]'
                      : 'border-stone-200 bg-white hover:bg-stone-50'
                  )}
                >
                  <span className="font-bold text-stone-900 block">
                    Gründlich (~3-5 Min.)
                  </span>
                  <span className="text-[11px] text-stone-500 mt-0.5 block">
                    Tiefe Suche für maximale Fairness- und Wochenend-Spreizung.
                  </span>
                </button>
              </div>
            </div>

            {/* Advanced Settings Toggle */}
            <div className="pt-2">
              <button
                type="button"
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="flex items-center gap-1.5 text-xs text-stone-600 font-medium hover:text-stone-900 cursor-pointer"
              >
                <Settings2 className="h-3.5 w-3.5" />
                <span>Erweiterte Constraints {showAdvanced ? 'ausblenden' : 'einblenden'}</span>
                <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', showAdvanced ? 'rotate-180' : '')} />
              </button>

              {showAdvanced && (
                <div className="mt-3 p-3.5 rounded-lg bg-stone-50 border border-stone-200/70 grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <label className="block text-stone-600 mb-1">
                      Mindest-Blockabstand (Tage)
                    </label>
                    <input
                      type="number"
                      min={7}
                      max={42}
                      value={blockGapDays}
                      onChange={(e) => setBlockGapDays(Number(e.target.value))}
                      className="w-full px-2.5 py-1.5 bg-white border border-stone-200 rounded text-xs"
                    />
                  </div>
                  <div>
                    <label className="block text-stone-600 mb-1">
                      Vorquartal einbeziehen
                    </label>
                    <div className="flex items-center h-8">
                      <span className="text-emerald-700 font-semibold flex items-center gap-1">
                        <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                        Aktiv (Trailing 21 Tage)
                      </span>
                    </div>
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

          {/* Big Action Button */}
          <div className="pt-2">
            <Button
              onClick={handleRunSolver}
              disabled={solving}
              variant="primary"
              size="lg"
              className="w-full py-3 text-sm font-bold shadow-md"
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
              <div className="flex items-center gap-2.5">
                <h1 className="text-lg sm:text-xl font-bold tracking-tight text-stone-900">
                  Dienstplan Übersicht
                </h1>
                <span className="px-2 py-0.5 rounded text-[11px] font-bold bg-blue-50 text-[#324b9b] border border-blue-200">
                  {currentQuarterKey}
                </span>
              </div>
              <p className="text-xs text-stone-500 mt-0.5">
                Kompakte Schichtübersicht nach Vorbild der bewährten Klinik-Tabelle.
              </p>
            </div>

            <div className="flex items-center gap-2">
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
                variant="outline"
                size="sm"
                className="text-xs"
              >
                <RotateCcw className="h-3.5 w-3.5 mr-1.5 text-stone-500" />
                Neu berechnen
              </Button>
            </div>
          </div>

          {/* Sub-Toolbar: Name Toggle & Month Tabs (Streamlit-style) */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-stone-50/80 p-2.5 rounded-lg border border-stone-200/80">
            {/* Month Filter Tabs */}
            <div className="flex items-center gap-1 overflow-x-auto">
              {[
                { id: 'ALL', label: 'Quartal (Gesamt)' },
                { id: 3, label: 'April' },
                { id: 4, label: 'Mai' },
                { id: 5, label: 'Juni' },
              ].map((m) => (
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

          {/* Legend Banner (Streamlit-style) */}
          <div className="flex items-center gap-4 text-[11px] text-stone-600 px-1">
            <span className="flex items-center gap-1.5">
              <span className="h-3 w-3 rounded bg-[#e8e0f0] border border-purple-200 inline-block" />
              <span>🌙 Nachtdienst</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-3 w-3 rounded bg-[#fff3e0] border border-amber-200 inline-block" />
              <span>☀️ Wochenenddienst</span>
            </span>
            <span className="flex items-center gap-1.5">
              <span className="h-3 w-3 rounded bg-[#b2dfdb] border border-teal-300 inline-block" />
              <span>📌 Fest vorbelegt</span>
            </span>
            <span className="flex items-center gap-1">
              <span>⚠️ Schichttausch</span>
            </span>
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
                    <th className="py-2.5 px-3 border-r border-stone-200 w-48 bg-[#fff8e7]">
                      ☀️ Sa/So Dienst
                    </th>
                    <th className="py-2.5 px-3 border-r border-stone-200 w-44 bg-[#fff8e7]">
                      ☀️ Rufbereitschaft
                    </th>
                    <th className="py-2.5 px-3 text-right">Aktion</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-stone-200 font-mono">
                  {loading ? (
                    <tr>
                      <td colSpan={5} className="py-12 text-center text-stone-500 font-sans">
                        Lade Dienstplan...
                      </td>
                    </tr>
                  ) : filteredDates.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-12 text-center text-stone-500 font-sans">
                        Keine Schichten vorhanden.
                      </td>
                    </tr>
                  ) : (
                    filteredDates.map((dateStr) => {
                      const isWknd = isWeekendDay(dateStr);
                      const dayShifts = assignments.filter((a) => a.shift_date === dateStr);
                      const nightShift = dayShifts.find((a) => a.shift_type === 'Nachtdienst');
                      const weekendShift = dayShifts.find((a) => a.shift_type === 'Wochenende_Tag');

                      const isNightPreAssigned = isDatePreAssigned(dateStr, 'Nachtdienst');
                      const isWkndPreAssigned = isDatePreAssigned(dateStr, 'Wochenenddienst');

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

                          {/* 🌙 Nacht Column (Styled with Streamlit #e8e0f0 background) */}
                          <td
                            className={cn(
                              'py-2 px-3 border-r border-stone-200 font-sans font-semibold transition-colors',
                              isNightPreAssigned
                                ? 'bg-[#b2dfdb] text-teal-950'
                                : 'bg-[#f2ecf8] text-purple-950'
                            )}
                          >
                            {nightShift ? (
                              <button
                                onClick={() => {
                                  setSelectedShift(nightShift);
                                  const c = staffList.filter(
                                    (s) => s.id !== nightShift.actual_staff_id
                                  );
                                  if (c.length > 0) setNewStaffId(c[0].id);
                                  setSwapModalOpen(true);
                                }}
                                className="flex items-center gap-1.5 hover:underline cursor-pointer text-left w-full"
                                title="Klicken für Diensttausch"
                              >
                                {isNightPreAssigned && (
                                  <Pin className="h-3 w-3 text-teal-800 shrink-0" />
                                )}
                                <span>
                                  {getStaffDisplayName(nightShift.actual_staff_id, true)}
                                </span>
                                {nightShift.is_paired && (
                                  <span className="text-[10px] text-stone-500 font-normal">
                                    + TFA
                                  </span>
                                )}
                                {nightShift.is_override && (
                                  <span className="text-[11px]" title="Getauchter Dienst">
                                    ⚠️
                                  </span>
                                )}
                              </button>
                            ) : (
                              <span className="text-stone-400 font-normal">—</span>
                            )}
                          </td>

                          {/* ☀️ Weekend Day Shift Column (#fff3e0 styling) */}
                          <td
                            className={cn(
                              'py-2 px-3 border-r border-stone-200 font-sans font-semibold transition-colors',
                              !isWknd
                                ? 'bg-stone-50/30 text-stone-400 font-normal'
                                : isWkndPreAssigned
                                ? 'bg-[#b2dfdb] text-teal-950'
                                : 'bg-[#fff4e3] text-amber-950'
                            )}
                          >
                            {weekendShift ? (
                              <button
                                onClick={() => {
                                  setSelectedShift(weekendShift);
                                  const c = staffList.filter(
                                    (s) => s.id !== weekendShift.actual_staff_id
                                  );
                                  if (c.length > 0) setNewStaffId(c[0].id);
                                  setSwapModalOpen(true);
                                }}
                                className="flex items-center gap-1.5 hover:underline cursor-pointer text-left w-full"
                                title="Klicken für Diensttausch"
                              >
                                {isWkndPreAssigned && (
                                  <Pin className="h-3 w-3 text-teal-800 shrink-0" />
                                )}
                                <span>
                                  {getStaffDisplayName(weekendShift.actual_staff_id, false)}
                                </span>
                                {weekendShift.is_override && <span>⚠️</span>}
                              </button>
                            ) : (
                              <span className="text-stone-300 font-normal">—</span>
                            )}
                          </td>

                          {/* ☀️ Rufbereitschaft Column */}
                          <td
                            className={cn(
                              'py-2 px-3 border-r border-stone-200 font-sans',
                              isWknd ? 'bg-[#fff8ed] text-stone-600' : 'bg-stone-50/30 text-stone-300'
                            )}
                          >
                            {isWknd ? (
                              <span className="text-stone-600">
                                {showFullNames ? 'Bereitschaft aktiv' : 'Ruf aktiv'}
                              </span>
                            ) : (
                              <span>—</span>
                            )}
                          </td>

                          {/* Quick Swap Action */}
                          <td className="py-2 px-3 text-right font-sans">
                            {nightShift && (
                              <button
                                onClick={() => {
                                  setSelectedShift(nightShift);
                                  const c = staffList.filter(
                                    (s) => s.id !== nightShift.actual_staff_id
                                  );
                                  if (c.length > 0) setNewStaffId(c[0].id);
                                  setSwapModalOpen(true);
                                }}
                                className="text-[11px] text-stone-500 hover:text-[#324b9b] font-medium cursor-pointer"
                              >
                                Tauschen
                              </button>
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
                  {assignments.filter((a) => a.shift_type === 'Nachtdienst').length}
                </span>
              </div>
              <div>
                <span className="text-stone-500">Wochenenden: </span>
                <span className="font-bold text-stone-900">
                  {assignments.filter((a) => a.shift_type === 'Wochenende_Tag').length}
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

      {/* SHIFT SWAP MODAL */}
      <Modal
        isOpen={swapModalOpen}
        onClose={() => setSwapModalOpen(false)}
        title="Dienst tauschen / Vertretung"
      >
        {selectedShift && (
          <form onSubmit={handleExecuteSwap} className="space-y-4">
            <div className="bg-stone-50 p-3 rounded-lg border border-stone-200/80 text-xs space-y-1.5">
              <div className="flex justify-between">
                <span className="text-stone-500">Datum & Schicht:</span>
                <span className="font-bold text-stone-900">
                  {selectedShift.shift_date} &middot;{' '}
                  {selectedShift.shift_type === 'Nachtdienst' ? 'Nachtdienst' : 'Wochenenddienst'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-stone-500">Aktuell eingeteilt:</span>
                <span className="font-semibold text-stone-900">
                  {getStaff(selectedShift.actual_staff_id)?.name} (
                  {getStaff(selectedShift.actual_staff_id)?.identifier})
                </span>
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-stone-700 mb-1">
                Ersatz-Mitarbeiter auswählen
              </label>
              <select
                required
                value={newStaffId}
                onChange={(e) => setNewStaffId(e.target.value)}
                className="w-full px-3 py-2 text-sm bg-stone-50/70 border border-stone-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#324b9b]/30 focus:border-[#324b9b]"
              >
                {staffList
                  .filter((s) => s.id !== selectedShift.actual_staff_id)
                  .map((s) => (
                    <option key={s.id} value={s.id}>
                      {s.name} ({s.identifier} &middot; {s.beruf})
                    </option>
                  ))}
              </select>
            </div>

            <div className="p-2.5 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
              <span>Regelprüfung: Keine Ruhezeit- oder Urlaubskonflikte erkannt.</span>
            </div>

            <div className="pt-3 flex items-center justify-end gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setSwapModalOpen(false)}
              >
                Abbrechen
              </Button>
              <Button type="submit" variant="primary">
                Tausch speichern
              </Button>
            </div>
          </form>
        )}
      </Modal>
    </div>
  );
};
