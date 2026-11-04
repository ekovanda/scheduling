import React, { useState, useEffect } from 'react';
import {
  Pin,
  Plus,
  Trash2,
  Calendar as CalendarIcon,
  ListFilter,
  Sparkles,
  ChevronLeft,
  ChevronRight,
  Moon,
  SunMedium,
} from 'lucide-react';
import type { PreAssignedShift, StaffMember, PreAssignedShiftType } from '../types/api';
import { fetchPreAssigned, fetchStaff, createPreAssigned, deletePreAssigned } from '../lib/api';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { cn } from '../lib/utils';

export const PreAssignedView: React.FC = () => {
  const [shifts, setShifts] = useState<PreAssignedShift[]>([]);
  const [staffList, setStaffList] = useState<StaffMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState<'list' | 'calendar'>('list');

  // Calendar month state (defaults to April 2026 for Q2)
  const [calMonth, setCalMonth] = useState({ year: 2026, month: 3 }); // 3 = April

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [formData, setFormData] = useState({
    staff_id: '',
    shift_date: '2026-04-12',
    shift_type: 'Nachtdienst' as PreAssignedShiftType,
    is_holiday: true,
    note: '',
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    const [paData, stfData] = await Promise.all([fetchPreAssigned(), fetchStaff()]);
    setShifts(paData);
    setStaffList(stfData);
    if (stfData.length > 0) {
      setFormData((prev) => ({ ...prev, staff_id: stfData[0].id }));
    }
    setLoading(false);
  };

  const getStaff = (staffId: string) => staffList.find((s) => s.id === staffId);

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

  const handleSavePreAssignment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.staff_id || !formData.shift_date) return;

    const stf = getStaff(formData.staff_id);
    const newRecord: PreAssignedShift = {
      id: `pa-${Date.now()}`,
      staff_id: formData.staff_id,
      staff_identifier: stf ? stf.identifier : formData.staff_id.toUpperCase(),
      shift_date: formData.shift_date,
      shift_type: formData.shift_type,
      is_holiday: formData.is_holiday,
      note: formData.note.trim() || undefined,
    };

    setShifts((prev) => [newRecord, ...prev]);
    setIsModalOpen(false);

    try {
      await createPreAssigned(newRecord);
    } catch (err) {
      console.warn('Backend sync failed, saved locally:', err);
    }
  };

  const handleDelete = async (id: string) => {
    setShifts((prev) => prev.filter((s) => s.id !== id));
    try {
      await deletePreAssigned(id);
    } catch (err) {
      console.warn('Backend delete failed, removed locally:', err);
    }
  };

  // Calendar Helpers
  const monthNames = [
    'Januar', 'Februar', 'März', 'April', 'Mai', 'Juni',
    'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember',
  ];

  const daysInMonth = new Date(calMonth.year, calMonth.month + 1, 0).getDate();
  const firstDayOfWeek = (new Date(calMonth.year, calMonth.month, 1).getDay() + 6) % 7;

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

  const getShiftsForDay = (day: number) => {
    const mStr = String(calMonth.month + 1).padStart(2, '0');
    const dStr = String(day).padStart(2, '0');
    const targetDate = `${calMonth.year}-${mStr}-${dStr}`;
    return shifts.filter((s) => s.shift_date === targetDate);
  };

  const sortedShifts = [...shifts].sort((a, b) => a.shift_date.localeCompare(b.shift_date));

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-stone-900">
            Vorbelegungen
          </h1>
        </div>

        <div className="flex items-center gap-3">
          {/* View Mode Toggle */}
          <div className="inline-flex rounded-lg border border-stone-200 bg-stone-100/70 p-0.5 text-xs font-medium shadow-2xs">
            <button
              onClick={() => setViewMode('list')}
              className={cn(
                'flex items-center gap-1.5 px-3 py-1.5 rounded-md transition-all cursor-pointer',
                viewMode === 'list'
                  ? 'bg-white text-stone-900 font-semibold shadow-2xs'
                  : 'text-stone-600 hover:text-stone-900'
              )}
            >
              <ListFilter className="h-3.5 w-3.5" />
              <span>Liste</span>
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
            Dienst vorab zuweisen
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        <div className="rounded-xl border border-stone-200/80 bg-white p-4 shadow-2xs">
          <div className="flex items-center justify-between text-stone-500 text-xs font-medium">
            <span>Vorbelegungen Gesamt</span>
            <Pin className="h-4 w-4 text-stone-400" />
          </div>
          <div className="mt-2">
            <span className="text-2xl font-bold text-stone-900">{shifts.length}</span>
          </div>
        </div>

        <div className="rounded-xl border border-stone-200/80 bg-white p-4 shadow-2xs">
          <div className="flex items-center justify-between text-stone-500 text-xs font-medium">
            <span>Nachtdienste fest</span>
            <Moon className="h-4 w-4 text-indigo-600" />
          </div>
          <div className="mt-2">
            <span className="text-2xl font-bold text-stone-900">
              {shifts.filter((s) => s.shift_type === 'Nachtdienst').length}
            </span>
          </div>
        </div>

        <div className="rounded-xl border border-stone-200/80 bg-white p-4 shadow-2xs col-span-2 sm:col-span-1">
          <div className="flex items-center justify-between text-stone-500 text-xs font-medium">
            <span>Feiertage belegt</span>
            <Sparkles className="h-4 w-4 text-amber-600" />
          </div>
          <div className="mt-2">
            <span className="text-2xl font-bold text-stone-900">
              {shifts.filter((s) => s.is_holiday).length}
            </span>
          </div>
        </div>
      </div>

      {/* LIST VIEW */}
      {viewMode === 'list' && (
        <div className="bg-white rounded-xl border border-stone-200/80 shadow-2xs overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-[#faf9f6] border-b border-stone-200/80 text-xs font-semibold text-stone-600 uppercase tracking-wider">
                <tr>
                  <th className="py-3.5 pl-6 pr-3">Datum</th>
                  <th className="px-3 py-3.5">Mitarbeiter</th>
                  <th className="px-3 py-3.5">Kürzel</th>
                  <th className="px-3 py-3.5">Schicht</th>
                  <th className="px-3 py-3.5">Feiertag</th>
                  <th className="px-3 py-3.5">Notiz</th>
                  <th className="py-3.5 pl-3 pr-6 text-right">Aktion</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {loading ? (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-stone-500">
                      Lade Vorbelegungen...
                    </td>
                  </tr>
                ) : sortedShifts.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="py-8 text-center text-stone-500">
                      Keine festen Vorbelegungen hinterlegt.
                    </td>
                  </tr>
                ) : (
                  sortedShifts.map((rec) => {
                    const stf = getStaff(rec.staff_id);
                    return (
                      <tr
                        key={rec.id}
                        className="hover:bg-amber-50/20 transition-colors group"
                      >
                        <td className="py-3.5 pl-6 pr-3 text-stone-900 font-medium text-xs">
                          <div className="flex items-center gap-1.5">
                            <CalendarIcon className="h-3.5 w-3.5 text-stone-400" />
                            <span>{formatDateGerman(rec.shift_date)}</span>
                          </div>
                        </td>

                        <td className="px-3 py-3.5 text-stone-800 font-semibold text-xs">
                          {stf ? stf.name : rec.staff_id}
                        </td>

                        <td className="px-3 py-3.5 font-mono text-xs text-stone-600 font-bold">
                          {rec.staff_identifier}
                        </td>

                        <td className="px-3 py-3.5">
                          {rec.shift_type === 'Nachtdienst' ? (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-indigo-50 text-indigo-700 border border-indigo-200 shadow-2xs">
                              <Moon className="h-3 w-3" />
                              Nachtdienst
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-50 text-amber-800 border border-amber-200 shadow-2xs">
                              <SunMedium className="h-3 w-3" />
                              Wochenende Tag
                            </span>
                          )}
                        </td>

                        <td className="px-3 py-3.5 text-xs">
                          {rec.is_holiday ? (
                            <span className="inline-flex items-center gap-1 text-amber-700 font-semibold">
                              <Sparkles className="h-3 w-3" />
                              Ja
                            </span>
                          ) : (
                            <span className="text-stone-400">—</span>
                          )}
                        </td>

                        <td className="px-3 py-3.5 text-stone-500 text-xs max-w-xs truncate">
                          {rec.note || '—'}
                        </td>

                        <td className="py-3.5 pl-3 pr-6 text-right">
                          <button
                            onClick={() => handleDelete(rec.id)}
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

      {/* CALENDAR VIEW */}
      {viewMode === 'calendar' && (
        <div className="bg-white rounded-xl border border-stone-200/80 shadow-2xs overflow-hidden">
          {/* Month Navigation */}
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
            {Array.from({ length: firstDayOfWeek }).map((_, idx) => (
              <div key={`empty-${idx}`} className="min-h-[90px] bg-stone-50/30 p-1" />
            ))}

            {Array.from({ length: daysInMonth }).map((_, idx) => {
              const day = idx + 1;
              const dayOfWeek = (firstDayOfWeek + idx) % 7;
              const isWeekend = dayOfWeek === 5 || dayOfWeek === 6;
              const dayShifts = getShiftsForDay(day);

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
                  </div>

                  <div className="space-y-1 flex-1">
                    {dayShifts.map((s) => (
                      <div
                        key={s.id}
                        className={cn(
                          'rounded border px-1.5 py-1 text-[11px] font-medium shadow-2xs flex items-center justify-between',
                          s.shift_type === 'Nachtdienst'
                            ? 'bg-indigo-50 border-indigo-200 text-indigo-900'
                            : 'bg-amber-50 border-amber-200 text-amber-900'
                        )}
                      >
                        <div className="flex items-center gap-1">
                          <Pin className="h-3 w-3 text-stone-400 rotate-45" />
                          <span className="font-bold">{s.staff_identifier}</span>
                        </div>
                        <span className="text-[9px] font-semibold">
                          {s.shift_type === 'Nachtdienst' ? 'ND' : 'WE'}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Add Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Dienst vorab fest zuweisen"
      >
        <form onSubmit={handleSavePreAssignment} className="space-y-4">
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
                Datum
              </label>
              <input
                type="date"
                required
                value={formData.shift_date}
                onChange={(e) => setFormData({ ...formData, shift_date: e.target.value })}
                className="w-full px-3 py-2 text-sm bg-stone-50/70 border border-stone-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#324b9b]/30 focus:border-[#324b9b]"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-stone-700 mb-1">
                Schichtart
              </label>
              <select
                value={formData.shift_type}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    shift_type: e.target.value as PreAssignedShiftType,
                  })
                }
                className="w-full px-3 py-2 text-sm bg-stone-50/70 border border-stone-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#324b9b]/30 focus:border-[#324b9b]"
              >
                <option value="Nachtdienst">Nachtdienst</option>
                <option value="Wochenenddienst">Wochenenddienst</option>
              </select>
            </div>
          </div>

          <div>
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={formData.is_holiday}
                onChange={(e) =>
                  setFormData({ ...formData, is_holiday: e.target.checked })
                }
                className="h-4 w-4 rounded text-[#324b9b] focus:ring-[#324b9b] border-stone-300"
              />
              <span className="text-xs font-medium text-stone-700">
                Gesetzlicher Feiertag
              </span>
            </label>
          </div>

          <div>
            <label className="block text-xs font-semibold text-stone-700 mb-1">
              Notiz / Anlass (optional)
            </label>
            <input
              type="text"
              placeholder="z.B. Ostersonntag, Tauschzusage, etc."
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
              Vorbelegung speichern
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
