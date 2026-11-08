import React, { useState, useEffect, useMemo } from 'react';
import {
  CalendarDays,
  Plus,
  Trash2,
  Pencil,
  Calendar as CalendarIcon,
  User,
  Search,
  X,
} from 'lucide-react';
import type { AbsenceRecord, AbsenceType, StaffMember } from '../types/api';
import { fetchAbsences, fetchStaff, createAbsence, updateAbsence, deleteAbsence } from '../lib/api';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { SearchableSelect } from '../components/ui/SearchableSelect';
import { cn } from '../lib/utils';
import { getStaffColorScheme } from '../lib/colors';

const ABSENCE_TYPE_LABELS: Record<AbsenceType, string> = {
  Vacation: 'Urlaub',
  SickLeave: 'Krankheit',
  Training: 'Fortbildung',
  SpecialLeave: 'Sonderurlaub',
};

export const AbsencesView: React.FC = () => {
  const [absences, setAbsences] = useState<AbsenceRecord[]>([]);
  const [staffList, setStaffList] = useState<StaffMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [actionError, setActionError] = useState<string | null>(null);

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingAbsenceId, setEditingAbsenceId] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    staff_id: '',
    absence_type: 'Vacation' as AbsenceType,
    start_date: '',
    end_date: '',
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
    setEditingAbsenceId(null);
    setFormError(null);
    setFormData({
      staff_id: '',
      absence_type: 'Vacation',
      start_date: '',
      end_date: '',
      note: '',
    });
    setIsModalOpen(true);
  };

  const handleOpenEditModal = (rec: AbsenceRecord) => {
    setEditingAbsenceId(rec.id);
    setFormError(null);
    setFormData({
      staff_id: rec.staff_id,
      absence_type: rec.absence_type || 'Vacation',
      start_date: rec.start_date,
      end_date: rec.end_date,
      note: rec.note || '',
    });
    setIsModalOpen(true);
  };

  const handleSaveAbsence = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.staff_id || !formData.start_date || !formData.end_date) return;

    setFormError(null);
    setSaving(true);
    try {
      if (editingAbsenceId) {
        const updatedRecord: AbsenceRecord = {
          id: editingAbsenceId,
          staff_id: formData.staff_id,
          absence_type: formData.absence_type,
          start_date: formData.start_date,
          end_date: formData.end_date,
          note: formData.note.trim() || null,
        };

        const saved = await updateAbsence(editingAbsenceId, updatedRecord);
        setAbsences((prev) => prev.map((a) => (a.id === editingAbsenceId ? saved : a)));
      } else {
        const newRecord: AbsenceRecord = {
          id: `abs-${Date.now()}`,
          staff_id: formData.staff_id,
          absence_type: formData.absence_type,
          start_date: formData.start_date,
          end_date: formData.end_date,
          note: formData.note.trim() || null,
        };

        const created = await createAbsence(newRecord);
        setAbsences((prev) => [created, ...prev]);
      }

      setFormData({
        staff_id: '',
        absence_type: 'Vacation',
        start_date: '',
        end_date: '',
        note: '',
      });
      setIsModalOpen(false);
      setEditingAbsenceId(null);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Fehler beim Speichern der Abwesenheit');
    } finally {
      setSaving(false);
    }
  };

  const handleDeleteAbsence = async (id: string) => {
    setActionError(null);
    try {
      await deleteAbsence(id);
      setAbsences((prev) => prev.filter((a) => a.id !== id));
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Fehler beim Löschen der Abwesenheit');
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

      {actionError && (
        <div className="rounded-lg bg-rose-50 border border-rose-200 px-4 py-2.5 text-xs text-rose-700 font-medium flex items-center justify-between">
          <span>{actionError}</span>
          <button
            type="button"
            onClick={() => setActionError(null)}
            className="text-rose-500 hover:text-rose-700 p-0.5"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

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
                        <div className="flex items-center gap-4 flex-wrap">
                          <div className="flex items-center gap-1.5 font-medium text-stone-800">
                            <CalendarIcon className="h-3.5 w-3.5 text-stone-400" />
                            <span>
                              {formatDateGerman(rec.start_date)} – {formatDateGerman(rec.end_date)}
                            </span>
                          </div>
                          <span className="px-2 py-0.5 rounded-full bg-stone-100 text-stone-700 border border-stone-200 font-semibold text-[11px]">
                            {days} {days === 1 ? 'Tag' : 'Tage'}
                          </span>
                          <span className="px-2 py-0.5 rounded-full bg-blue-50 text-[#324b9b] border border-blue-200/70 font-medium text-[11px]">
                            {ABSENCE_TYPE_LABELS[rec.absence_type] || rec.absence_type}
                          </span>
                          {rec.note && (
                            <span className="text-stone-500 italic truncate max-w-[240px]">
                              {rec.note}
                            </span>
                          )}
                        </div>

                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleOpenEditModal(rec)}
                            className="text-stone-400 hover:text-[#324b9b] p-1 hover:bg-[#324b9b]/10 rounded transition-colors cursor-pointer"
                            title="Bearbeiten"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                          <button
                            onClick={() => handleDeleteAbsence(rec.id)}
                            className="text-stone-400 hover:text-rose-600 p-1 hover:bg-rose-50 rounded transition-colors cursor-pointer"
                            title="Löschen"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Add / Edit Absence Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          setEditingAbsenceId(null);
          setFormError(null);
        }}
        title={editingAbsenceId ? 'Abwesenheit bearbeiten' : 'Abwesenheit eintragen'}
      >
        <form onSubmit={handleSaveAbsence} className="space-y-4">
          {formError && (
            <div className="rounded-lg bg-rose-50 border border-rose-200 px-3 py-2 text-xs text-rose-700 font-medium">
              {formError}
            </div>
          )}

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

          <div>
            <label className="block text-xs font-semibold text-stone-700 mb-1">
              Art der Abwesenheit
            </label>
            <select
              value={formData.absence_type}
              onChange={(e) =>
                setFormData({ ...formData, absence_type: e.target.value as AbsenceType })
              }
              className="w-full px-3 py-2 text-sm bg-stone-50/70 border border-stone-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#324b9b]/30 focus:border-[#324b9b]"
            >
              <option value="Vacation">Urlaub</option>
              <option value="SickLeave">Krankheit</option>
              <option value="Training">Fortbildung</option>
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
                min={formData.start_date || undefined}
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

          <div>
            <label className="block text-xs font-semibold text-stone-700 mb-1">
              Notiz (optional)
            </label>
            <input
              type="text"
              placeholder="z.B. Sommerurlaub, Kongress..."
              value={formData.note}
              onChange={(e) => setFormData({ ...formData, note: e.target.value })}
              className="w-full px-3 py-2 text-sm bg-stone-50/70 border border-stone-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#324b9b]/30 focus:border-[#324b9b]"
            />
          </div>

          <div className="pt-4 flex items-center justify-end gap-2">
            <Button
              type="button"
              variant="outline"
              disabled={saving}
              onClick={() => {
                setIsModalOpen(false);
                setEditingAbsenceId(null);
                setFormError(null);
              }}
            >
              Abbrechen
            </Button>
            <Button type="submit" variant="primary" disabled={saving}>
              {saving ? 'Speichert...' : editingAbsenceId ? 'Speichern' : 'Eintragen'}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
