import React, { useState, useEffect } from 'react';
import {
  Pin,
  Plus,
  Trash2,
  Calendar as CalendarIcon,
  Sparkles,
  Moon,
  SunMedium,
} from 'lucide-react';
import type { PreAssignedShift, StaffMember, PreAssignedShiftType } from '../types/api';
import { fetchPreAssigned, fetchStaff, createPreAssigned, deletePreAssigned } from '../lib/api';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { SearchableSelect } from '../components/ui/SearchableSelect';
import { cn, isNightShift } from '../lib/utils';
import { getStaffColorScheme } from '../lib/colors';

export const PreAssignedView: React.FC = () => {
  const [shifts, setShifts] = useState<PreAssignedShift[]>([]);
  const [staffList, setStaffList] = useState<StaffMember[]>([]);
  const [loading, setLoading] = useState(true);

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

  const getStaff = (staffId: string) => {
    if (!staffId) return undefined;
    const needle = staffId.trim().toLowerCase();
    return staffList.find(
      (s) => s.id.toLowerCase() === needle || s.identifier.toLowerCase() === needle
    );
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

  const sortedShifts = [...shifts].sort((a, b) => a.shift_date.localeCompare(b.shift_date));

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-stone-900">
            Vorbelegungen (Feiertage & feste Dienste)
          </h1>
          <p className="text-xs text-stone-500 mt-0.5">
            Feste Schichtzusagen für Feiertage, die vorab verbindlich in den Plan übernommen werden.
          </p>
        </div>

        <div>
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
              {shifts.filter((s) => isNightShift(s.shift_type)).length}
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

      {/* LIST VIEW ONLY */}
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
                  const stf = getStaff(rec.staff_id) || getStaff(rec.staff_identifier);
                  const isNight = isNightShift(rec.shift_type);

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
                        <div className="flex items-center gap-2">
                          <div
                            className={cn(
                              'h-6 w-6 rounded-full border font-bold text-[10px] flex items-center justify-center shrink-0',
                              getStaffColorScheme(stf?.beruf, stf?.abteilung).avatar
                            )}
                          >
                            {(stf ? stf.name : rec.staff_identifier || rec.staff_id)
                              .split(' ')
                              .map((n) => n[0])
                              .slice(0, 2)
                              .join('')}
                          </div>
                          <span>{stf ? stf.name : rec.staff_identifier || rec.staff_id}</span>
                        </div>
                      </td>

                      <td className="px-3 py-3.5 font-mono text-xs text-stone-600 font-bold">
                        {rec.staff_identifier}
                      </td>

                      <td className="px-3 py-3.5">
                        {isNight ? (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200 shadow-2xs">
                            <Moon className="h-3.5 w-3.5" />
                            <span>
                              Nachtdienst
                              {rec.shift_type !== 'Nachtdienst' ? ` (${rec.shift_type})` : ''}
                            </span>
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-800 border border-amber-200 shadow-2xs">
                            <SunMedium className="h-3.5 w-3.5" />
                            <span>
                              Tagdienst
                              {rec.shift_type !== 'Tagdienst' && rec.shift_type !== 'Wochenenddienst'
                                ? ` (${rec.shift_type})`
                                : ''}
                            </span>
                          </span>
                        )}
                      </td>

                      <td className="px-3 py-3.5 text-xs">
                        {rec.is_holiday ? (
                          <span className="inline-flex items-center gap-1 text-amber-700 font-medium">
                            <Sparkles className="h-3 w-3 text-amber-500" />
                            Ja
                          </span>
                        ) : (
                          <span className="text-stone-400">Nein</span>
                        )}
                      </td>

                      <td className="px-3 py-3.5 text-stone-600 text-xs max-w-[200px] truncate">
                        {rec.note || <span className="text-stone-300 italic">—</span>}
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

      {/* Add Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Dienst vorab zuweisen"
      >
        <form onSubmit={handleSavePreAssignment} className="space-y-4">
          <div>
            <label className="block text-xs font-semibold text-stone-700 mb-1">
              Mitarbeiter (Name oder Kürzel suchen)
            </label>
            <SearchableSelect
              staffList={staffList}
              value={formData.staff_id}
              onChange={(staffId) => setFormData({ ...formData, staff_id: staffId })}
              placeholder="Name oder Kürzel tippen..."
              required
            />
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
                Dienstart
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
                <option value="Wochenenddienst">Wochenenddienst (Tag)</option>
                <option value="Tagdienst">Tagdienst (Feiertag)</option>
              </select>
            </div>
          </div>

          <div>
            <label className="flex items-center gap-2 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={formData.is_holiday}
                onChange={(e) => setFormData({ ...formData, is_holiday: e.target.checked })}
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
              placeholder="z.B. Ostersonntag, Tag der Arbeit..."
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
