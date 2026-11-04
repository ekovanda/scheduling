import React, { useState, useEffect } from 'react';
import {
  CalendarDays,
  Plus,
  Palmtree,
  GraduationCap,
  HeartPulse,
  Trash2,
  Calendar,
} from 'lucide-react';
import type { AbsenceRecord, StaffMember, AbsenceType } from '../types/api';
import { fetchAbsences, fetchStaff, createAbsence, deleteAbsence } from '../lib/api';
import { AbsenceBadge } from '../components/ui/Badge';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';

export const AbsencesView: React.FC = () => {
  const [absences, setAbsences] = useState<AbsenceRecord[]>([]);
  const [staffList, setStaffList] = useState<StaffMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedStaff, setSelectedStaff] = useState<string>('ALL');
  const [selectedType, setSelectedType] = useState<string>('ALL');

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [formData, setFormData] = useState({
    staff_id: '',
    absence_type: 'Vacation' as AbsenceType,
    start_date: '2026-04-01',
    end_date: '2026-04-07',
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

  const getStaffName = (staffId: string) => {
    const s = staffList.find((item) => item.id === staffId);
    return s ? s.name : staffId;
  };

  const getStaffIdentifier = (staffId: string) => {
    const s = staffList.find((item) => item.id === staffId);
    return s ? s.identifier : '';
  };

  const filteredAbsences = absences.filter((a) => {
    const matchesStaff = selectedStaff === 'ALL' || a.staff_id === selectedStaff;
    const matchesType = selectedType === 'ALL' || a.absence_type === selectedType;
    return matchesStaff && matchesType;
  });

  // Calculate duration in days
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
      absence_type: formData.absence_type,
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

  // KPIs
  const totalEntries = absences.length;
  const totalVacations = absences.filter((a) => a.absence_type === 'Vacation').length;
  const totalTrainings = absences.filter((a) => a.absence_type === 'Training').length;
  const totalSickOrSpecial = absences.filter(
    (a) => a.absence_type === 'SickLeave' || a.absence_type === 'SpecialLeave'
  ).length;

  return (
    <div className="space-y-6">
      {/* Page Title & Action */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-stone-900">
            Abwesenheiten
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={handleOpenAddModal} variant="primary">
            <Plus className="h-4 w-4 mr-1.5" />
            Abwesenheit eintragen
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="rounded-xl border border-stone-200/80 bg-white p-4 shadow-2xs">
          <div className="flex items-center justify-between text-stone-500 text-xs font-medium">
            <span>Einträge Gesamt</span>
            <CalendarDays className="h-4 w-4 text-stone-400" />
          </div>
          <div className="mt-2">
            <span className="text-2xl font-bold text-stone-900">{totalEntries}</span>
          </div>
        </div>

        <div className="rounded-xl border border-stone-200/80 bg-white p-4 shadow-2xs">
          <div className="flex items-center justify-between text-stone-500 text-xs font-medium">
            <span>Urlaub</span>
            <Palmtree className="h-4 w-4 text-emerald-600" />
          </div>
          <div className="mt-2">
            <span className="text-2xl font-bold text-stone-900">{totalVacations}</span>
          </div>
        </div>

        <div className="rounded-xl border border-stone-200/80 bg-white p-4 shadow-2xs">
          <div className="flex items-center justify-between text-stone-500 text-xs font-medium">
            <span>Fortbildung</span>
            <GraduationCap className="h-4 w-4 text-sky-600" />
          </div>
          <div className="mt-2">
            <span className="text-2xl font-bold text-stone-900">{totalTrainings}</span>
          </div>
        </div>

        <div className="rounded-xl border border-stone-200/80 bg-white p-4 shadow-2xs">
          <div className="flex items-center justify-between text-stone-500 text-xs font-medium">
            <span>Krank / Sonderurlaub</span>
            <HeartPulse className="h-4 w-4 text-rose-600" />
          </div>
          <div className="mt-2">
            <span className="text-2xl font-bold text-stone-900">{totalSickOrSpecial}</span>
          </div>
        </div>
      </div>

      {/* Filter Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-white p-3 rounded-xl border border-stone-200/80 shadow-2xs">
        <div className="flex items-center gap-2">
          <select
            value={selectedStaff}
            onChange={(e) => setSelectedStaff(e.target.value)}
            className="px-3 py-1.5 text-xs bg-stone-50/70 border border-stone-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#324b9b]/20 font-medium text-stone-800"
          >
            <option value="ALL">Alle Mitarbeiter</option>
            {staffList.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name} ({s.identifier})
              </option>
            ))}
          </select>
        </div>

        {/* Type Tabs */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
          {[
            { id: 'ALL', label: 'Alle' },
            { id: 'Vacation', label: 'Urlaub' },
            { id: 'Training', label: 'Fortbildung' },
            { id: 'SickLeave', label: 'Krank' },
            { id: 'SpecialLeave', label: 'Sonderurlaub' },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setSelectedType(tab.id)}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all cursor-pointer whitespace-nowrap ${
                selectedType === tab.id
                  ? 'bg-stone-800 text-white font-semibold shadow-2xs'
                  : 'text-stone-600 hover:bg-stone-100 hover:text-stone-900'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-stone-200/80 shadow-2xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-[#faf9f6] border-b border-stone-200/80 text-xs font-semibold text-stone-600 uppercase tracking-wider">
              <tr>
                <th className="py-3.5 pl-6 pr-3">Mitarbeiter</th>
                <th className="px-3 py-3.5">Kürzel</th>
                <th className="px-3 py-3.5">Typ</th>
                <th className="px-3 py-3.5">Zeitraum</th>
                <th className="px-3 py-3.5">Dauer</th>
                <th className="px-3 py-3.5">Notiz</th>
                <th className="py-3.5 pl-3 pr-6 text-right">Aktion</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {loading ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-stone-500">
                    Lade Abwesenheiten...
                  </td>
                </tr>
              ) : filteredAbsences.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-stone-500">
                    Keine Abwesenheiten eingetragen.
                  </td>
                </tr>
              ) : (
                filteredAbsences.map((rec) => {
                  const days = getDayCount(rec.start_date, rec.end_date);
                  return (
                    <tr
                      key={rec.id}
                      className="hover:bg-amber-50/20 transition-colors group"
                    >
                      <td className="py-3.5 pl-6 pr-3">
                        <span className="font-semibold text-stone-900">
                          {getStaffName(rec.staff_id)}
                        </span>
                      </td>

                      <td className="px-3 py-3.5 font-mono text-xs text-stone-600 font-bold">
                        {getStaffIdentifier(rec.staff_id)}
                      </td>

                      <td className="px-3 py-3.5">
                        <AbsenceBadge type={rec.absence_type} />
                      </td>

                      <td className="px-3 py-3.5 text-stone-700 text-xs">
                        <div className="flex items-center gap-1.5 font-medium">
                          <Calendar className="h-3.5 w-3.5 text-stone-400" />
                          <span>
                            {formatDateGerman(rec.start_date)} – {formatDateGerman(rec.end_date)}
                          </span>
                        </div>
                      </td>

                      <td className="px-3 py-3.5 text-stone-600 text-xs">
                        {days} {days === 1 ? 'Tag' : 'Tage'}
                      </td>

                      <td className="px-3 py-3.5 text-stone-600 text-xs max-w-xs truncate">
                        {rec.note || '—'}
                      </td>

                      <td className="py-3.5 pl-3 pr-6 text-right">
                        <button
                          onClick={() => handleDeleteAbsence(rec.id)}
                          className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-stone-400 hover:text-rose-600 hover:bg-rose-50 rounded-md transition-colors cursor-pointer"
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

          <div>
            <label className="block text-xs font-semibold text-stone-700 mb-1">
              Typ der Abwesenheit
            </label>
            <select
              value={formData.absence_type}
              onChange={(e) =>
                setFormData({ ...formData, absence_type: e.target.value as AbsenceType })
              }
              className="w-full px-3 py-2 text-sm bg-stone-50/70 border border-stone-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#324b9b]/30 focus:border-[#324b9b]"
            >
              <option value="Vacation">Urlaub</option>
              <option value="Training">Fortbildung</option>
              <option value="SickLeave">Krank</option>
              <option value="SpecialLeave">Sonderurlaub</option>
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
