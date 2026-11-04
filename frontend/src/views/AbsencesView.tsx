import React, { useState, useEffect } from 'react';
import {
  CalendarDays,
  Plus,
  Trash2,
  Calendar as CalendarIcon,
  ListFilter,
  User,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import type { AbsenceRecord, StaffMember } from '../types/api';
import { fetchAbsences, fetchStaff, createAbsence, deleteAbsence } from '../lib/api';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { cn } from '../lib/utils';

type AbsenceViewMode = 'by_person' | 'chronological' | 'calendar';

export const AbsencesView: React.FC = () => {
  const [absences, setAbsences] = useState<AbsenceRecord[]>([]);
  const [staffList, setStaffList] = useState<StaffMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState<AbsenceViewMode>('by_person');

  // Calendar month state (defaults to April 2026 for Q2)
  const [calMonth, setCalMonth] = useState({ year: 2026, month: 3 }); // 3 = April (0-indexed)

  // Hovered absence ID for highlighting across calendar
  const [hoveredAbsenceId, setHoveredAbsenceId] = useState<string | null>(null);

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [formData, setFormData] = useState({
    staff_id: '',
    start_date: '2026-04-10',
    end_date: '2026-04-18',
    note: '',
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    const [absData, stfData] = await Promise.all([fetchAbsences(), fetchStaff()]);
    setAbsences(absData);
    setStaffList(stfData);
    if (stfData.length > 0) {
      setFormData((prev) => ({ ...prev, staff_id: stfData[0].id }));
    }
    setLoading(false);
  };

  const getStaff = (staffId: string) => staffList.find((s) => s.id === staffId);

  // Palette of warm, distinct badge colors assigned per staff member for calendar blockers
  const getStaffColor = (identifier: string) => {
    const colors = [
      'bg-amber-100 text-amber-900 border-amber-300',
      'bg-blue-100 text-blue-900 border-blue-300',
      'bg-emerald-100 text-emerald-900 border-emerald-300',
      'bg-purple-100 text-purple-900 border-purple-300',
      'bg-rose-100 text-rose-900 border-rose-300',
      'bg-teal-100 text-teal-900 border-teal-300',
      'bg-orange-100 text-orange-900 border-orange-300',
    ];
    let hash = 0;
    for (let i = 0; i < identifier.length; i++) {
      hash = identifier.charCodeAt(i) + ((hash << 5) - hash);
    }
    return colors[Math.abs(hash) % colors.length];
  };

  // Helper date utilities
  const getDayCount = (start: string, end: string) => {
    const d1 = new Date(start);
    const d2 = new Date(end);
    const diff = Math.round((d2.getTime() - d1.getTime()) / (1000 * 60 * 60 * 24)) + 1;
    return diff > 0 ? diff : 1;
  };

  const formatDateGerman = (dateStr: string) => {
    if (!dateStr) return '';
    const [year, month, day] = dateStr.split('-');
    return `${day}.${month}.${year}`;
  };

  const handleOpenAddModal = () => {
    if (staffList.length > 0 && !formData.staff_id) {
      setFormData((prev) => ({ ...prev, staff_id: staffList[0].id }));
    }
    setIsModalOpen(true);
  };

  const handleSaveAbsence = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.staff_id || !formData.start_date || !formData.end_date) return;

    const newRecord: AbsenceRecord = {
      id: `abs-${Date.now()}`,
      staff_id: formData.staff_id,
      absence_type: 'Vacation', // Unified internally
      start_date: formData.start_date,
      end_date: formData.end_date,
      note: formData.note.trim() || undefined,
    };

    setAbsences((prev) => [newRecord, ...prev]);
    setIsModalOpen(false);

    try {
      await createAbsence(newRecord);
    } catch (err) {
      console.warn('Backend sync failed, saved locally:', err);
    }
  };

  const handleDeleteAbsence = async (id: string) => {
    setAbsences((prev) => prev.filter((a) => a.id !== id));
    try {
      await deleteAbsence(id);
    } catch (err) {
      console.warn('Backend delete failed, removed locally:', err);
    }
  };

  // Sorted chronological list
  const chronologicalAbsences = [...absences].sort((a, b) =>
    a.start_date.localeCompare(b.start_date)
  );

  // Group absences by person
  const staffWithAbsences = staffList.map((stf) => {
    const records = absences
      .filter((a) => a.staff_id === stf.id)
      .sort((a, b) => a.start_date.localeCompare(b.start_date));
    const totalDays = records.reduce(
      (sum, r) => sum + getDayCount(r.start_date, r.end_date),
      0
    );
    return { staff: stf, records, totalDays };
  });

  // Calendar generation helpers
  const monthNames = [
    'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
    'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember',
  ];

  const daysInMonth = new Date(calMonth.year, calMonth.month + 1, 0).getDate();
  const firstDayOfWeek = (new Date(calMonth.year, calMonth.month, 1).getDay() + 6) % 7; // Monday = 0

  const handlePrevMonth = () => {
    setCalMonth((prev) => {
      if (prev.month === 0) return { year: prev.year - 1, month: 11 };
      return { year: prev.year, month: prev.month - 1 };
    });
  };

  const handleNextMonth = () => {
    setCalMonth((prev) => {
      if (prev.month === 11) return { year: prev.year + 1, month: 0 };
      return { year: prev.year, month: prev.month + 1 };
    });
  };

  // Check which absences fall on a specific calendar day
  const getAbsencesForDay = (day: number) => {
    const mStr = String(calMonth.month + 1).padStart(2, '0');
    const dStr = String(day).padStart(2, '0');
    const targetDate = `${calMonth.year}-${mStr}-${dStr}`;

    return absences.filter((a) => a.start_date <= targetDate && targetDate <= a.end_date);
  };

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-stone-900">
            Abwesenheiten
          </h1>
        </div>

        {/* View Switcher & Action Button */}
        <div className="flex items-center gap-3">
          {/* 3-View Switcher Pill */}
          <div className="inline-flex rounded-lg border border-stone-200 bg-stone-100/70 p-0.5 text-xs font-medium shadow-2xs">
            <button
              onClick={() => setViewMode('by_person')}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-all cursor-pointer',
                viewMode === 'by_person'
                  ? 'bg-white text-stone-900 font-semibold shadow-2xs'
                  : 'text-stone-600 hover:text-stone-900'
              )}
            >
              <User className="h-3.5 w-3.5" />
              <span>Nach Person</span>
            </button>
            <button
              onClick={() => setViewMode('chronological')}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-all cursor-pointer',
                viewMode === 'chronological'
                  ? 'bg-white text-stone-900 font-semibold shadow-2xs'
                  : 'text-stone-600 hover:text-stone-900'
              )}
            >
              <ListFilter className="h-3.5 w-3.5" />
              <span>Chronologisch</span>
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

          <Button onClick={handleOpenAddModal} variant="primary">
            <Plus className="h-4 w-4 mr-1.5" />
            Eintragen
          </Button>
        </div>
      </div>

      {/* KPI Summary Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        <div className="rounded-xl border border-stone-200/80 bg-white p-4 shadow-2xs">
          <div className="flex items-center justify-between text-stone-500 text-xs font-medium">
            <span>Einträge Gesamt</span>
            <CalendarDays className="h-4 w-4 text-stone-400" />
          </div>
          <div className="mt-2">
            <span className="text-2xl font-bold text-stone-900">{absences.length}</span>
          </div>
        </div>

        <div className="rounded-xl border border-stone-200/80 bg-white p-4 shadow-2xs">
          <div className="flex items-center justify-between text-stone-500 text-xs font-medium">
            <span>Personen mit Abwesenheit</span>
            <User className="h-4 w-4 text-[#324b9b]" />
          </div>
          <div className="mt-2">
            <span className="text-2xl font-bold text-stone-900">
              {staffWithAbsences.filter((s) => s.records.length > 0).length}
            </span>
          </div>
        </div>

        <div className="rounded-xl border border-stone-200/80 bg-white p-4 shadow-2xs col-span-2 sm:col-span-1">
          <div className="flex items-center justify-between text-stone-500 text-xs font-medium">
            <span>Fehltage Gesamt</span>
            <CalendarIcon className="h-4 w-4 text-emerald-600" />
          </div>
          <div className="mt-2">
            <span className="text-2xl font-bold text-stone-900">
              {absences.reduce((sum, r) => sum + getDayCount(r.start_date, r.end_date), 0)}
            </span>
          </div>
        </div>
      </div>

      {/* VIEW 1: BY PERSON */}
      {viewMode === 'by_person' && (
        <div className="space-y-4">
          {staffWithAbsences.map(({ staff, records, totalDays }) => (
            <div
              key={staff.id}
              className="bg-white rounded-xl border border-stone-200/80 shadow-2xs overflow-hidden"
            >
              {/* Person Summary Header */}
              <div className="bg-[#faf9f6] px-5 py-3 border-b border-stone-200/80 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="h-7 w-7 rounded-full bg-stone-100 border border-stone-200 text-stone-700 font-bold text-xs flex items-center justify-center">
                    {staff.name
                      .split(' ')
                      .map((n) => n[0])
                      .slice(0, 2)
                      .join('')}
                  </div>
                  <span className="font-semibold text-stone-900 text-sm">{staff.name}</span>
                  <span className="font-mono text-xs text-stone-500 font-bold">
                    {staff.identifier}
                  </span>
                  <span className="text-xs text-stone-500">({staff.beruf})</span>
                </div>
                <div className="text-xs font-medium text-stone-600">
                  {records.length === 0 ? (
                    <span className="text-stone-400">Keine Abwesenheiten</span>
                  ) : (
                    <span>
                      {records.length} {records.length === 1 ? 'Zeitraum' : 'Zeiträume'} &middot;{' '}
                      <strong>{totalDays} Fehltage</strong>
                    </span>
                  )}
                </div>
              </div>

              {/* Records List for Person */}
              {records.length > 0 && (
                <div className="divide-y divide-stone-100">
                  {records.map((rec) => {
                    const days = getDayCount(rec.start_date, rec.end_date);
                    return (
                      <div
                        key={rec.id}
                        className="px-5 py-3 flex items-center justify-between hover:bg-stone-50/60 transition-colors text-xs"
                      >
                        <div className="flex items-center gap-4">
                          <div className="flex items-center gap-1.5 font-medium text-stone-800">
                            <CalendarIcon className="h-3.5 w-3.5 text-stone-400" />
                            <span>
                              {formatDateGerman(rec.start_date)} – {formatDateGerman(rec.end_date)}
                            </span>
                          </div>
                          <span className="px-2 py-0.5 rounded-full bg-stone-100 text-stone-700 border border-stone-200 font-semibold text-[11px]">
                            {days} {days === 1 ? 'Tag' : 'Tage'}
                          </span>
                          {rec.note && (
                            <span className="text-stone-500 italic max-w-sm truncate">
                              „{rec.note}“
                            </span>
                          )}
                        </div>

                        <button
                          onClick={() => handleDeleteAbsence(rec.id)}
                          className="text-stone-400 hover:text-rose-600 p-1 hover:bg-rose-50 rounded transition-colors cursor-pointer"
                          title="Löschen"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* VIEW 2: CHRONOLOGICAL */}
      {viewMode === 'chronological' && (
        <div className="bg-white rounded-xl border border-stone-200/80 shadow-2xs overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-[#faf9f6] border-b border-stone-200/80 text-xs font-semibold text-stone-600 uppercase tracking-wider">
                <tr>
                  <th className="py-3.5 pl-6 pr-3">Zeitraum</th>
                  <th className="px-3 py-3.5">Mitarbeiter</th>
                  <th className="px-3 py-3.5">Kürzel</th>
                  <th className="px-3 py-3.5">Dauer</th>
                  <th className="px-3 py-3.5">Notiz</th>
                  <th className="py-3.5 pl-3 pr-6 text-right">Aktion</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {loading ? (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-stone-500">
                      Lade Abwesenheiten...
                    </td>
                  </tr>
                ) : chronologicalAbsences.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-8 text-center text-stone-500">
                      Keine Abwesenheiten eingetragen.
                    </td>
                  </tr>
                ) : (
                  chronologicalAbsences.map((rec) => {
                    const stf = getStaff(rec.staff_id);
                    const days = getDayCount(rec.start_date, rec.end_date);
                    return (
                      <tr
                        key={rec.id}
                        className="hover:bg-amber-50/20 transition-colors group"
                      >
                        <td className="py-3.5 pl-6 pr-3 text-stone-900 font-medium text-xs">
                          <div className="flex items-center gap-1.5">
                            <CalendarIcon className="h-3.5 w-3.5 text-stone-400" />
                            <span>
                              {formatDateGerman(rec.start_date)} – {formatDateGerman(rec.end_date)}
                            </span>
                          </div>
                        </td>

                        <td className="px-3 py-3.5 text-stone-800 font-semibold text-xs">
                          {stf ? stf.name : rec.staff_id}
                        </td>

                        <td className="px-3 py-3.5 font-mono text-xs text-stone-600 font-bold">
                          {stf ? stf.identifier : ''}
                        </td>

                        <td className="px-3 py-3.5 text-stone-600 text-xs">
                          {days} {days === 1 ? 'Tag' : 'Tage'}
                        </td>

                        <td className="px-3 py-3.5 text-stone-500 text-xs max-w-xs truncate">
                          {rec.note || '—'}
                        </td>

                        <td className="py-3.5 pl-3 pr-6 text-right">
                          <button
                            onClick={() => handleDeleteAbsence(rec.id)}
                            className="inline-flex items-center p-1 text-stone-400 hover:text-rose-600 hover:bg-rose-50 rounded transition-colors cursor-pointer"
                            title="Löschen"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
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

      {/* VIEW 3: CALENDAR WITH MULTI-DAY BLOCKERS */}
      {viewMode === 'calendar' && (
        <div className="bg-white rounded-xl border border-stone-200/80 shadow-2xs overflow-hidden">
          {/* Month Navigation Bar */}
          <div className="bg-[#faf9f6] px-6 py-3 border-b border-stone-200/80 flex items-center justify-between">
            <h2 className="text-base font-bold text-stone-900">
              {monthNames[calMonth.month]} {calMonth.year}
            </h2>
            <div className="flex items-center gap-1">
              <button
                onClick={handlePrevMonth}
                className="p-1.5 rounded-lg border border-stone-200 bg-white hover:bg-stone-50 text-stone-600 transition-colors cursor-pointer"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <button
                onClick={handleNextMonth}
                className="p-1.5 rounded-lg border border-stone-200 bg-white hover:bg-stone-50 text-stone-600 transition-colors cursor-pointer"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Weekday Header */}
          <div className="grid grid-cols-7 border-b border-stone-200/80 bg-stone-50/50 text-center text-xs font-semibold text-stone-500 py-2">
            <div>Mo</div>
            <div>Di</div>
            <div>Mi</div>
            <div>Do</div>
            <div>Fr</div>
            <div className="text-amber-700">Sa</div>
            <div className="text-amber-700">So</div>
          </div>

          {/* Days Grid */}
          <div className="grid grid-cols-7 auto-rows-fr divide-x divide-y divide-stone-100 border-b border-stone-200/80">
            {/* Empty prefix cells */}
            {Array.from({ length: firstDayOfWeek }).map((_, idx) => (
              <div key={`empty-${idx}`} className="min-h-[90px] bg-stone-50/30 p-1" />
            ))}

            {/* Days of current month */}
            {Array.from({ length: daysInMonth }).map((_, idx) => {
              const day = idx + 1;
              const dayOfWeek = (firstDayOfWeek + idx) % 7;
              const isWeekend = dayOfWeek === 5 || dayOfWeek === 6;
              const dayAbsences = getAbsencesForDay(day);

              return (
                <div
                  key={`day-${day}`}
                  className={cn(
                    'min-h-[90px] p-1.5 flex flex-col transition-colors',
                    isWeekend ? 'bg-amber-50/15' : 'bg-white hover:bg-stone-50/40'
                  )}
                >
                  <div className="flex items-center justify-between text-xs mb-1">
                    <span
                      className={cn(
                        'font-bold',
                        isWeekend ? 'text-amber-800' : 'text-stone-800'
                      )}
                    >
                      {day}
                    </span>
                    {dayAbsences.length > 0 && (
                      <span className="text-[10px] text-stone-400 font-mono">
                        {dayAbsences.length} abwesend
                      </span>
                    )}
                  </div>

                  {/* Absence Blockers Stack */}
                  <div className="space-y-1 flex-1">
                    {dayAbsences.map((a) => {
                      const stf = getStaff(a.staff_id);
                      const ident = stf ? stf.identifier : a.staff_id;
                      const name = stf ? stf.name : a.staff_id;
                      const days = getDayCount(a.start_date, a.end_date);
                      const isHovered = hoveredAbsenceId === a.id;

                      return (
                        <div
                          key={a.id}
                          onMouseEnter={() => setHoveredAbsenceId(a.id)}
                          onMouseLeave={() => setHoveredAbsenceId(null)}
                          className={cn(
                            'relative rounded border px-1.5 py-0.5 text-[11px] font-medium transition-all duration-150 cursor-pointer select-none',
                            getStaffColor(ident),
                            isHovered
                              ? 'scale-110 z-30 shadow-md ring-2 ring-stone-900/10'
                              : 'shadow-2xs opacity-90 hover:opacity-100'
                          )}
                          title={`${name} (${ident}) &middot; ${formatDateGerman(a.start_date)} - ${formatDateGerman(a.end_date)} (${days} Tage)${a.note ? `\nNotiz: ${a.note}` : ''}`}
                        >
                          <div className="flex items-center justify-between truncate">
                            <span className="font-bold tracking-tight">{ident}</span>
                            {isHovered && (
                              <span className="text-[9px] font-semibold pl-1">
                                {days}d
                              </span>
                            )}
                          </div>

                          {/* Hover Tooltip Overlay with Full Name & Duration */}
                          {isHovered && (
                            <div className="absolute left-0 bottom-full mb-1 z-40 bg-stone-900 text-white text-[10px] rounded px-2 py-1 shadow-lg whitespace-nowrap pointer-events-none">
                              <span className="font-bold">{name}</span>
                              <span className="text-stone-300 ml-1">
                                ({formatDateGerman(a.start_date)} – {formatDateGerman(a.end_date)}, {days} Tage)
                              </span>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Add Absence Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Abwesenheit eintragen"
      >
        <form onSubmit={handleSaveAbsence} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-stone-700 mb-1">
              Mitarbeiter
            </label>
            <select
              required
              value={formData.staff_id}
              onChange={(e) => setFormData({ ...formData, staff_id: e.target.value })}
              className="w-full px-3 py-2 text-sm bg-stone-50/70 border border-stone-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#324b9b]/30 focus:border-[#324b9b]"
            >
              {staffList.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name} ({s.identifier} &middot; {s.beruf})
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-stone-700 mb-1">
                Von (Startdatum)
              </label>
              <input
                type="date"
                required
                value={formData.start_date}
                onChange={(e) => setFormData({ ...formData, start_date: e.target.value })}
                className="w-full px-3 py-2 text-sm bg-stone-50/70 border border-stone-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#324b9b]/30 focus:border-[#324b9b]"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-stone-700 mb-1">
                Bis (Enddatum)
              </label>
              <input
                type="date"
                required
                value={formData.end_date}
                onChange={(e) => setFormData({ ...formData, end_date: e.target.value })}
                className="w-full px-3 py-2 text-sm bg-stone-50/70 border border-stone-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#324b9b]/30 focus:border-[#324b9b]"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-stone-700 mb-1">
              Notiz (optional)
            </label>
            <input
              type="text"
              placeholder="z.B. Kongress Berlin oder Sommerurlaub"
              value={formData.note}
              onChange={(e) => setFormData({ ...formData, note: e.target.value })}
              className="w-full px-3 py-2 text-sm bg-stone-50/70 border border-stone-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#324b9b]/30 focus:border-[#324b9b]"
            />
          </div>

          <div className="pt-4 flex items-center justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => setIsModalOpen(false)}
            >
              Abbrechen
            </Button>
            <Button type="submit" variant="primary">
              Eintragen
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
