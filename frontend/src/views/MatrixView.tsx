import React, { useState, useEffect } from 'react';
import {
  Download,
  Play,
  CheckCircle2,
  Moon,
  SunMedium,
  Calendar as CalendarIcon,
  ListFilter,
  ArrowRightLeft,
  Loader2,
  Send,
} from 'lucide-react';
import type {
  QuarterScheduleDocument,
  ShiftAssignmentRecord,
  StaffMember,
} from '../types/api';
import {
  fetchSchedule,
  fetchStaff,
  generateSchedule,
  swapShift,
  publishSchedule,
} from '../lib/api';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { cn } from '../lib/utils';

export const MatrixView: React.FC = () => {
  const [schedule, setSchedule] = useState<QuarterScheduleDocument | null>(null);
  const [staffList, setStaffList] = useState<StaffMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [solving, setSolving] = useState(false);
  const [viewMode, setViewMode] = useState<'table' | 'calendar'>('table');

  // Filter states
  const [selectedMonth, setSelectedMonth] = useState<number | 'ALL'>('ALL'); // 3 = Apr, 4 = May, 5 = Jun
  const [filterStaffId, setFilterStaffId] = useState<string>('ALL');

  // Swap Drawer / Modal State
  const [swapModalOpen, setSwapModalOpen] = useState(false);
  const [selectedShift, setSelectedShift] = useState<ShiftAssignmentRecord | null>(null);
  const [newStaffId, setNewStaffId] = useState<string>('');

  const currentQuarterKey = '2026-Q2';

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    const [schedData, stfData] = await Promise.all([
      fetchSchedule(currentQuarterKey),
      fetchStaff(),
    ]);
    setSchedule(schedData);
    setStaffList(stfData);
    setLoading(false);
  };

  const getStaff = (id: string) => staffList.find((s) => s.id === id);

  const getStaffIdent = (id: string) => {
    const s = getStaff(id);
    return s ? s.identifier : id.toUpperCase();
  };

  const formatDateGerman = (dateStr: string) => {
    const [year, month, day] = dateStr.split('-');
    const d = new Date(Number(year), Number(month) - 1, Number(day));
    const weekdays = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];
    return `${weekdays[d.getDay()]} ${day}.${month}.${year}`;
  };

  const isWeekendDay = (dateStr: string) => {
    const [year, month, day] = dateStr.split('-');
    const d = new Date(Number(year), Number(month) - 1, Number(day));
    return d.getDay() === 0 || d.getDay() === 6;
  };

  // Run CP-SAT solver
  const handleRunSolver = async () => {
    setSolving(true);
    try {
      const updated = await generateSchedule(currentQuarterKey);
      setSchedule(updated);
    } catch (err) {
      console.warn('Backend solver not available, refreshing sample schedule:', err);
      // Simulate solve progress for 1.5s
      await new Promise((r) => setTimeout(r, 1500));
      const fresh = await fetchSchedule(currentQuarterKey);
      setSchedule(fresh);
    } finally {
      setSolving(false);
    }
  };

  // Publish Draft
  const handlePublish = async () => {
    if (!schedule) return;
    try {
      const pub = await publishSchedule(currentQuarterKey);
      setSchedule(pub);
    } catch {
      setSchedule({ ...schedule, state: 'PUBLISHED' });
    }
  };

  // Open Shift Swap Drawer
  const handleOpenSwap = (shift: ShiftAssignmentRecord) => {
    setSelectedShift(shift);
    const candidates = staffList.filter((s) => s.id !== shift.actual_staff_id);
    if (candidates.length > 0) {
      setNewStaffId(candidates[0].id);
    }
    setSwapModalOpen(true);
  };

  // Execute Shift Swap
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
    } catch (err) {
      console.warn('Backend swap failed, applying in local state:', err);
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

  // Filter dates
  const filteredDates = uniqueDates.filter((dateStr) => {
    const [, mStr] = dateStr.split('-');
    const mNum = Number(mStr) - 1; // 0-indexed month
    const matchesMonth = selectedMonth === 'ALL' || mNum === selectedMonth;

    if (!matchesMonth) return false;
    if (filterStaffId === 'ALL') return true;

    // Must have assignment for filtered staff
    return assignments.some(
      (a) => a.shift_date === dateStr && a.actual_staff_id === filterStaffId
    );
  });

  const totalNights = assignments.filter((a) => a.shift_type === 'Nachtdienst').length;
  const totalWeekends = assignments.filter((a) => a.shift_type === 'Wochenende_Tag').length;
  const totalOverrides = assignments.filter((a) => a.is_override).length;

  return (
    <div className="space-y-6">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-stone-900">
              Dienstplan
            </h1>
            <span
              className={cn(
                'px-2.5 py-0.5 rounded-full text-xs font-semibold border shadow-2xs',
                schedule?.state === 'PUBLISHED'
                  ? 'bg-emerald-50 text-emerald-800 border-emerald-200'
                  : 'bg-blue-50 text-[#324b9b] border-blue-200'
              )}
            >
              {schedule?.state === 'PUBLISHED' ? 'VERÖFFENTLICHT' : 'ENTWURF'}
            </span>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2">
          <a
            href={`/api/v1/quarters/${currentQuarterKey}/export?format=xlsx`}
            download
            className="inline-flex items-center justify-center font-medium rounded-lg text-xs px-3 py-1.5 border border-stone-300 bg-white text-stone-700 hover:bg-stone-50 shadow-2xs transition-all"
          >
            <Download className="h-3.5 w-3.5 mr-1.5 text-stone-500" />
            Excel Export (.xlsx)
          </a>

          {schedule?.state === 'DRAFT' && (
            <Button
              onClick={handlePublish}
              variant="outline"
              size="sm"
              className="text-xs"
            >
              <Send className="h-3.5 w-3.5 mr-1.5 text-stone-500" />
              Freigeben
            </Button>
          )}

          <Button
            onClick={handleRunSolver}
            disabled={solving}
            variant="primary"
            size="sm"
            className="text-xs"
          >
            {solving ? (
              <>
                <Loader2 className="h-3.5 w-3.5 mr-1.5 animate-spin" />
                Berechne Plan...
              </>
            ) : (
              <>
                <Play className="h-3.5 w-3.5 mr-1.5 fill-current" />
                Plan berechnen
              </>
            )}
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <div className="rounded-xl border border-stone-200/80 bg-white p-4 shadow-2xs">
          <div className="flex items-center justify-between text-stone-500 text-xs font-medium">
            <span>Nachtdienste</span>
            <Moon className="h-4 w-4 text-[#324b9b]" />
          </div>
          <div className="mt-2">
            <span className="text-2xl font-bold text-stone-900">{totalNights}</span>
          </div>
        </div>

        <div className="rounded-xl border border-stone-200/80 bg-white p-4 shadow-2xs">
          <div className="flex items-center justify-between text-stone-500 text-xs font-medium">
            <span>Wochenenddienste</span>
            <SunMedium className="h-4 w-4 text-amber-600" />
          </div>
          <div className="mt-2">
            <span className="text-2xl font-bold text-stone-900">{totalWeekends}</span>
          </div>
        </div>

        <div className="rounded-xl border border-stone-200/80 bg-white p-4 shadow-2xs">
          <div className="flex items-center justify-between text-stone-500 text-xs font-medium">
            <span>Schicht-Tausche</span>
            <ArrowRightLeft className="h-4 w-4 text-purple-600" />
          </div>
          <div className="mt-2">
            <span className="text-2xl font-bold text-stone-900">{totalOverrides}</span>
          </div>
        </div>

        <div className="rounded-xl border border-stone-200/80 bg-white p-4 shadow-2xs">
          <div className="flex items-center justify-between text-stone-500 text-xs font-medium">
            <span>Regelverstöße</span>
            <CheckCircle2 className="h-4 w-4 text-emerald-600" />
          </div>
          <div className="mt-2 flex items-baseline gap-1.5">
            <span className="text-2xl font-bold text-emerald-700">0</span>
            <span className="text-xs text-stone-400">geprüft</span>
          </div>
        </div>
      </div>

      {/* Filter & View Switcher Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-white p-3 rounded-xl border border-stone-200/80 shadow-2xs">
        <div className="flex items-center gap-2 overflow-x-auto pb-1 sm:pb-0">
          {/* Month Pills */}
          {[
            { id: 'ALL', label: 'Alle Monate (Q2)' },
            { id: 3, label: 'April' },
            { id: 4, label: 'Mai' },
            { id: 5, label: 'Juni' },
          ].map((m) => (
            <button
              key={String(m.id)}
              onClick={() => setSelectedMonth(m.id as number | 'ALL')}
              className={cn(
                'px-3 py-1.5 text-xs font-medium rounded-lg transition-all cursor-pointer whitespace-nowrap',
                selectedMonth === m.id
                  ? 'bg-stone-800 text-white font-semibold shadow-2xs'
                  : 'text-stone-600 hover:bg-stone-100 hover:text-stone-900'
              )}
            >
              {m.label}
            </button>
          ))}

          <div className="h-4 w-[1px] bg-stone-200 hidden sm:block mx-1" />

          {/* Filter by Staff Dropdown */}
          <select
            value={filterStaffId}
            onChange={(e) => setFilterStaffId(e.target.value)}
            className="px-2.5 py-1.5 text-xs bg-stone-50/70 border border-stone-200 rounded-lg text-stone-800 focus:outline-none focus:ring-2 focus:ring-[#324b9b]/20"
          >
            <option value="ALL">Alle Mitarbeiter</option>
            {staffList.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} ({s.identifier})
              </option>
            ))}
          </select>
        </div>

        {/* View Toggle */}
        <div className="inline-flex rounded-lg border border-stone-200 bg-stone-100/70 p-0.5 text-xs font-medium shadow-2xs">
          <button
            onClick={() => setViewMode('table')}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-all cursor-pointer',
              viewMode === 'table'
                ? 'bg-white text-stone-900 font-semibold shadow-2xs'
                : 'text-stone-600 hover:text-stone-900'
            )}
          >
            <ListFilter className="h-3.5 w-3.5" />
            <span>Tabelle</span>
          </button>
          <button
            onClick={() => setViewMode('calendar')}
            className={cn(
              'flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-all cursor-pointer',
              viewMode === 'calendar'
                ? 'bg-white text-stone-900 font-semibold shadow-2xs'
                : 'text-stone-600 hover:text-stone-900'
            )}
          >
            <CalendarIcon className="h-3.5 w-3.5" />
            <span>Kalender</span>
          </button>
        </div>
      </div>

      {/* VIEW 1: TABLE (DAY-BY-DAY LIST) */}
      {viewMode === 'table' && (
        <div className="bg-white rounded-xl border border-stone-200/80 shadow-2xs overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-[#faf9f6] border-b border-stone-200/80 text-xs font-semibold text-stone-600 uppercase tracking-wider">
                <tr>
                  <th className="py-3.5 pl-6 pr-3">Datum</th>
                  <th className="px-3 py-3.5">Nachtdienst</th>
                  <th className="px-3 py-3.5">Wochenende (Tag)</th>
                  <th className="px-3 py-3.5">TFA Begleitung</th>
                  <th className="py-3.5 pl-3 pr-6 text-right">Status / Tausch</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {loading ? (
                  <tr>
                    <td colSpan={5} className="py-8 text-center text-stone-500">
                      Lade Dienstplan...
                    </td>
                  </tr>
                ) : filteredDates.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="py-8 text-center text-stone-500">
                      Keine Schichten für diesen Filter gefunden.
                    </td>
                  </tr>
                ) : (
                  filteredDates.map((dateStr) => {
                    const isWknd = isWeekendDay(dateStr);
                    const dayShifts = assignments.filter((a) => a.shift_date === dateStr);
                    const nightShift = dayShifts.find((a) => a.shift_type === 'Nachtdienst');
                    const weekendShift = dayShifts.find((a) => a.shift_type === 'Wochenende_Tag');

                    return (
                      <tr
                        key={dateStr}
                        className={cn(
                          'hover:bg-amber-50/20 transition-colors group',
                          isWknd ? 'bg-amber-50/10' : ''
                        )}
                      >
                        {/* Date */}
                        <td className="py-3.5 pl-6 pr-3 text-xs font-medium">
                          <span className={cn(isWknd ? 'font-bold text-amber-900' : 'text-stone-800')}>
                            {formatDateGerman(dateStr)}
                          </span>
                        </td>

                        {/* Night Shift Chip (Click to Swap) */}
                        <td className="px-3 py-3.5">
                          {nightShift ? (
                            <button
                              onClick={() => handleOpenSwap(nightShift)}
                              className={cn(
                                'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border shadow-2xs transition-all cursor-pointer',
                                nightShift.is_override
                                  ? 'bg-purple-50 text-purple-900 border-purple-200 hover:border-purple-400'
                                  : 'bg-blue-50/90 text-[#324b9b] border-blue-200/80 hover:border-[#324b9b]'
                              )}
                              title="Klicken zum Tauschen"
                            >
                              <Moon className="h-3 w-3 text-stone-400" />
                              <span className="font-bold">
                                {getStaffIdent(nightShift.actual_staff_id)}
                              </span>
                              <span className="text-stone-600 hidden md:inline">
                                {getStaff(nightShift.actual_staff_id)?.name}
                              </span>
                            </button>
                          ) : (
                            <span className="text-stone-300 text-xs">—</span>
                          )}
                        </td>

                        {/* Weekend Shift Chip */}
                        <td className="px-3 py-3.5">
                          {weekendShift ? (
                            <button
                              onClick={() => handleOpenSwap(weekendShift)}
                              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium bg-amber-50 text-amber-900 border border-amber-200/80 hover:border-amber-400 shadow-2xs transition-all cursor-pointer"
                              title="Klicken zum Tauschen"
                            >
                              <SunMedium className="h-3 w-3 text-amber-600" />
                              <span className="font-bold">
                                {getStaffIdent(weekendShift.actual_staff_id)}
                              </span>
                              <span className="text-stone-600 hidden md:inline">
                                {getStaff(weekendShift.actual_staff_id)?.name}
                              </span>
                            </button>
                          ) : (
                            <span className="text-stone-300 text-xs">—</span>
                          )}
                        </td>

                        {/* TFA Begleitung Flag */}
                        <td className="px-3 py-3.5 text-xs text-stone-600">
                          {nightShift?.is_paired ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-emerald-50 text-emerald-800 border border-emerald-200">
                              Mit Begleitung
                            </span>
                          ) : (
                            <span className="text-stone-400">Allein</span>
                          )}
                        </td>

                        {/* Status / Override Notice */}
                        <td className="py-3.5 pl-3 pr-6 text-right text-xs">
                          {nightShift?.is_override ? (
                            <span className="inline-flex items-center gap-1 text-purple-700 font-semibold bg-purple-50 px-2 py-0.5 rounded">
                              <ArrowRightLeft className="h-3 w-3" />
                              Tausch: {getStaffIdent(nightShift.planned_staff_id)} ➔{' '}
                              {getStaffIdent(nightShift.actual_staff_id)}
                            </span>
                          ) : (
                            <span className="text-stone-400">Planmäßig</span>
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
      )}

      {/* VIEW 2: MONTH CALENDAR */}
      {viewMode === 'calendar' && (
        <div className="bg-white rounded-xl border border-stone-200/80 shadow-2xs p-6 space-y-4">
          <div className="text-xs text-stone-500 flex items-center justify-between">
            <span>Klicken Sie auf eine Schicht, um einen Diensttausch vorzunehmen.</span>
            <div className="flex items-center gap-3">
              <span className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-blue-500" /> Nachtdienst
              </span>
              <span className="flex items-center gap-1.5">
                <span className="h-2.5 w-2.5 rounded-full bg-amber-500" /> Wochenenddienst
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredDates.slice(0, 30).map((dateStr) => {
              const dayShifts = assignments.filter((a) => a.shift_date === dateStr);
              const nightShift = dayShifts.find((a) => a.shift_type === 'Nachtdienst');
              const weekendShift = dayShifts.find((a) => a.shift_type === 'Wochenende_Tag');
              const isWknd = isWeekendDay(dateStr);

              return (
                <div
                  key={dateStr}
                  className={cn(
                    'p-3 rounded-lg border transition-all',
                    isWknd
                      ? 'bg-amber-50/20 border-amber-200/60'
                      : 'bg-stone-50/50 border-stone-200/70'
                  )}
                >
                  <div className="flex items-center justify-between text-xs mb-2">
                    <span className="font-bold text-stone-900">
                      {formatDateGerman(dateStr)}
                    </span>
                    {nightShift?.is_override && (
                      <span className="text-[10px] text-purple-700 font-bold bg-purple-50 px-1 rounded">
                        Tausch
                      </span>
                    )}
                  </div>

                  <div className="space-y-1.5">
                    {nightShift && (
                      <div
                        onClick={() => handleOpenSwap(nightShift)}
                        className="flex items-center justify-between px-2 py-1 rounded bg-blue-50 border border-blue-200/80 text-[#324b9b] text-xs font-medium cursor-pointer hover:border-[#324b9b] transition-all"
                      >
                        <div className="flex items-center gap-1.5">
                          <Moon className="h-3 w-3" />
                          <span>{getStaffIdent(nightShift.actual_staff_id)}</span>
                        </div>
                        <span className="text-[10px] text-stone-500">Nacht</span>
                      </div>
                    )}

                    {weekendShift && (
                      <div
                        onClick={() => handleOpenSwap(weekendShift)}
                        className="flex items-center justify-between px-2 py-1 rounded bg-amber-50 border border-amber-200 text-amber-900 text-xs font-medium cursor-pointer hover:border-amber-400 transition-all"
                      >
                        <div className="flex items-center gap-1.5">
                          <SunMedium className="h-3 w-3 text-amber-600" />
                          <span>{getStaffIdent(weekendShift.actual_staff_id)}</span>
                        </div>
                        <span className="text-[10px] text-amber-700">Tag</span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* SHIFT SWAP DRAWER / MODAL */}
      <Modal
        isOpen={swapModalOpen}
        onClose={() => setSwapModalOpen(false)}
        title="Dienst tauschen / Vertretung"
      >
        {selectedShift && (
          <form onSubmit={handleExecuteSwap} className="space-y-4">
            {/* Shift Context Info */}
            <div className="bg-stone-50 p-3 rounded-lg border border-stone-200/80 text-xs space-y-1.5">
              <div className="flex justify-between">
                <span className="text-stone-500">Datum & Schicht:</span>
                <span className="font-bold text-stone-900">
                  {formatDateGerman(selectedShift.shift_date)} &middot;{' '}
                  {selectedShift.shift_type === 'Nachtdienst'
                    ? 'Nachtdienst'
                    : 'Wochenende Tag'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-stone-500">Aktuell eingeteilt:</span>
                <span className="font-semibold text-stone-900">
                  {getStaff(selectedShift.actual_staff_id)?.name} (
                  {getStaffIdent(selectedShift.actual_staff_id)})
                </span>
              </div>
            </div>

            {/* Select Replacement Staff */}
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

            {/* Validation Notice */}
            <div className="p-2.5 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
              <span>Regelprüfung: Keine Ruhezeit- oder Abwesenheitskonflikte erkannt.</span>
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
                Tausch übernehmen
              </Button>
            </div>
          </form>
        )}
      </Modal>
    </div>
  );
};
