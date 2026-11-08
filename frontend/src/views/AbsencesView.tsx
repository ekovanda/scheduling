import React, { useState, useEffect, useMemo } from 'react';
import {
  CalendarDays,
  Plus,
  Trash2,
  Calendar as CalendarIcon,
  User,
  Search,
  X,
} from 'lucide-react';
import type { AbsenceRecord, StaffMember } from '../types/api';
import { fetchAbsences, fetchStaff, createAbsence, deleteAbsence } from '../lib/api';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { SearchableSelect } from '../components/ui/SearchableSelect';
import { cn } from '../lib/utils';
import { getStaffColorScheme } from '../lib/colors';

export const AbsencesView: React.FC = () => {
  const [absences, setAbsences] = useState<AbsenceRecord[]>([]);
  const [staffList, setStaffList] = useState<StaffMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [formData, setFormData] = useState({
    staff_id: '',
    start_date: '',
    end_date: '',
  });

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    setLoading(true);
    const [absData, stfData] = await Promise.all([fetchAbsences(), fetchStaff()]);
    setAbsences(absData);
    setStaffList(stfData);
    setLoading(false);
  };

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
    setFormData({
      staff_id: '',
      start_date: '',
      end_date: '',
    });
    setIsModalOpen(true);
  };

  const handleSaveAbsence = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.staff_id || !formData.start_date || !formData.end_date) return;

    const newRecord: AbsenceRecord = {
      id: `abs-${Date.now()}`,
      staff_id: formData.staff_id,
      absence_type: 'Vacation',
      start_date: formData.start_date,
      end_date: formData.end_date,
    };

    setAbsences((prev) => [newRecord, ...prev]);
    setFormData({
      staff_id: '',
      start_date: '',
      end_date: '',
    });
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

  // Group absences by person with search filter applied
  const staffWithAbsences = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();

    return staffList
      .filter((stf) => {
        if (!q) return true;
        return (
          stf.name.toLowerCase().includes(q) ||
          stf.identifier.toLowerCase().includes(q) ||
          (stf.beruf && stf.beruf.toLowerCase().includes(q))
        );
      })
      .map((stf) => {
        const records = absences
          .filter(
            (a) =>
              a.staff_id === stf.id ||
              a.staff_id.toLowerCase() === stf.identifier.toLowerCase()
          )
          .sort((a, b) => a.start_date.localeCompare(b.start_date));
        const totalDays = records.reduce(
          (sum, r) => sum + getDayCount(r.start_date, r.end_date),
          0
        );
        return { staff: stf, records, totalDays };
      });
  }, [staffList, absences, searchQuery]);

  const totalFilteredDays = staffWithAbsences.reduce((sum, s) => sum + s.totalDays, 0);
  const totalFilteredRecords = staffWithAbsences.reduce((sum, s) => sum + s.records.length, 0);

  return (
    <div className="space-y-6">
      {/* Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-stone-900">
            Abwesenheiten
          </h1>
          <p className="text-xs text-stone-500 mt-0.5">
            Übersicht aller erfassten Urlaube und Fehlzeiten nach Mitarbeitern.
          </p>
        </div>

        <div className="flex items-center gap-3">
          {/* Live Search Input */}
          <div className="relative min-w-[220px] sm:min-w-[280px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-stone-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Nach Name oder Kürzel filtern..."
              className="w-full pl-9 pr-8 py-1.5 text-xs bg-white border border-stone-200 rounded-lg text-stone-900 placeholder:text-stone-400 focus:outline-none focus:ring-2 focus:ring-[#324b9b]/20 focus:border-[#324b9b] shadow-2xs transition-all"
            />
            {searchQuery && (
              <button
                type="button"
                onClick={() => setSearchQuery('')}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-stone-400 hover:text-stone-600 p-0.5"
                title="Filter zurücksetzen"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </div>

          <Button onClick={handleOpenAddModal} variant="primary">
            <Plus className="h-4 w-4 mr-1.5" />
            Eintragen
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
        <div className="rounded-xl border border-stone-200/80 bg-white p-4 shadow-2xs">
          <div className="flex items-center justify-between text-stone-500 text-xs font-medium">
            <span>Einträge {searchQuery ? '(gefiltert)' : 'Gesamt'}</span>
            <CalendarDays className="h-4 w-4 text-stone-400" />
          </div>
          <div className="mt-2">
            <span className="text-2xl font-bold text-stone-900">{totalFilteredRecords}</span>
            {searchQuery && (
              <span className="text-xs text-stone-400 ml-1.5">von {absences.length}</span>
            )}
          </div>
        </div>

        <div className="rounded-xl border border-stone-200/80 bg-white p-4 shadow-2xs">
          <div className="flex items-center justify-between text-stone-500 text-xs font-medium">
            <span>Personen mit Urlaub</span>
            <User className="h-4 w-4 text-[#324b9b]" />
          </div>
          <div className="mt-2">
            <span className="text-2xl font-bold text-stone-900">
              {staffWithAbsences.filter((s) => s.records.length > 0).length}
            </span>
            <span className="text-xs text-stone-400 ml-1.5">
              von {staffWithAbsences.length} {searchQuery ? 'gefiltert' : 'Mitarbeitern'}
            </span>
          </div>
        </div>

        <div className="rounded-xl border border-stone-200/80 bg-white p-4 shadow-2xs col-span-2 sm:col-span-1">
          <div className="flex items-center justify-between text-stone-500 text-xs font-medium">
            <span>Fehltage {searchQuery ? '(gefiltert)' : 'Gesamt'}</span>
            <CalendarIcon className="h-4 w-4 text-emerald-600" />
          </div>
          <div className="mt-2">
            <span className="text-2xl font-bold text-stone-900">{totalFilteredDays}</span>
          </div>
        </div>
      </div>

      {/* Person-by-Person View */}
      {loading ? (
        <div className="bg-white rounded-xl border border-stone-200/80 p-8 text-center text-sm text-stone-500">
          Lade Abwesenheiten...
        </div>
      ) : staffWithAbsences.length === 0 ? (
        <div className="bg-white rounded-xl border border-stone-200/80 p-8 text-center text-sm text-stone-500 space-y-2">
          <p>Keine Mitarbeiter für Suchbegriff „{searchQuery}“ gefunden.</p>
          <Button variant="outline" size="sm" onClick={() => setSearchQuery('')}>
            Filter zurücksetzen
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          {staffWithAbsences.map(({ staff, records, totalDays }) => (
            <div
              key={staff.id}
              className="bg-white rounded-xl border border-stone-200/80 shadow-2xs overflow-hidden"
            >
              {/* Person Summary Header */}
              <div className="bg-[#faf9f6] px-5 py-3 border-b border-stone-200/80 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div
                    className={cn(
                      'h-7 w-7 rounded-full border font-bold text-xs flex items-center justify-center shrink-0',
                      getStaffColorScheme(staff.beruf, staff.abteilung).avatar
                    )}
                  >
                    {staff.name
                      .split(' ')
                      .map((n) => n[0])
                      .slice(0, 2)
                      .join('')}
                  </div>
                  <span className="font-semibold text-stone-900 text-sm">{staff.name}</span>
                  <span className="font-mono text-xs text-stone-500 font-bold">
                    ({staff.identifier})
                  </span>
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-stone-100 text-stone-700 border border-stone-200 font-medium">
                    {staff.beruf}
                  </span>
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
                        className="px-5 py-2.5 flex items-center justify-between hover:bg-stone-50/60 transition-colors text-xs"
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

      {/* Add Absence Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title="Abwesenheit eintragen"
      >
        <form onSubmit={handleSaveAbsence} className="space-y-4">
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
                Von (Startdatum)
              </label>
              <input
                type="date"
                required
                min="2027-01-01"
                value={formData.start_date}
                onChange={(e) => {
                  const newStart = e.target.value;
                  setFormData((prev) => ({
                    ...prev,
                    start_date: newStart,
                    end_date: prev.end_date && prev.end_date >= newStart ? prev.end_date : newStart,
                  }));
                }}
                onClick={(e) => {
                  try {
                    e.currentTarget.showPicker();
                  } catch {}
                }}
                className="w-full px-3 py-2 text-sm bg-stone-50/70 border border-stone-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#324b9b]/30 focus:border-[#324b9b] cursor-pointer"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-stone-700 mb-1">
                Bis (Enddatum)
              </label>
              <input
                type="date"
                required
                min={formData.start_date || '2027-01-01'}
                value={formData.end_date}
                onChange={(e) => setFormData({ ...formData, end_date: e.target.value })}
                onClick={(e) => {
                  try {
                    e.currentTarget.showPicker();
                  } catch {}
                }}
                className="w-full px-3 py-2 text-sm bg-stone-50/70 border border-stone-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#324b9b]/30 focus:border-[#324b9b] cursor-pointer"
              />
            </div>
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
