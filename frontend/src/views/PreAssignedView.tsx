import React, { useState, useEffect, useMemo } from 'react';
import {
  Pin,
  Plus,
  Trash2,
  Pencil,
  Calendar as CalendarIcon,
  Sparkles,
  Moon,
  SunMedium,
  CheckCircle2,
} from 'lucide-react';
import type { PreAssignedShift, StaffMember, PreAssignedShiftType } from '../types/api';
import { fetchPreAssigned, fetchStaff, createPreAssigned, updatePreAssigned, deletePreAssigned } from '../lib/api';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { SearchableSelect } from '../components/ui/SearchableSelect';
import { cn, isNightShift } from '../lib/utils';
import { getStaffColorScheme } from '../lib/colors';

interface ShiftOption {
  id: string;
  label: string;
  hours: string;
  icon: string;
  badge?: string;
  description: string;
  isHolidayDefault?: boolean;
}

const getWeekdayGerman = (dateStr: string): string => {
  if (!dateStr) return '';
  const [year, month, day] = dateStr.split('-').map(Number);
  const date = new Date(year, month - 1, day);
  return date.toLocaleDateString('de-DE', { weekday: 'long' });
};

const formatShiftLabel = (shiftType: string): string => {
  if (!shiftType) return '—';
  if (shiftType === 'Sa_10-21') return '☀️ Frühdienst 10–21 (Sa)';
  if (shiftType === 'Sa_10-19') return '☀️ Spätdienst 10–19 (Azubi)';
  if (shiftType === 'Sa_10-22') return '📞 Rufbereitschaft 10–22 (Sa)';
  if (shiftType === 'Sa_Intern') return '🎓 Intern Tagdienst (08:30–20:30)';
  if (shiftType === 'So_8-20') return '☀️ Frühdienst 8–20 (So/FT)';
  if (shiftType === 'So_10-22') return '📞 Rufbereitschaft 10–22 (So/FT)';
  if (shiftType === 'So_8-20:30') return '📞 Azubi Ruf 8–20:30 (So/FT)';
  if (shiftType === 'So_Intern') return '🎓 Intern Tagdienst (08:30–20:30)';
  if (shiftType.startsWith('N_')) return `🌙 Nacht (${shiftType})`;
  if (shiftType.toLowerCase().includes('nacht')) return '🌙 Nachtdienst';
  return shiftType;
};

const getShiftOptionsForDate = (dateStr: string): ShiftOption[] => {
  if (!dateStr) {
    return [
      {
        id: 'Nachtdienst',
        label: 'Nachtdienst',
        hours: '20:00–08:00',
        icon: '🌙',
        badge: 'Nacht',
        description: 'Regulärer Nachtdienst (Mo–So)',
      },
      {
        id: 'So_8-20',
        label: 'Frühdienst (So/FT)',
        hours: '08:00–20:00',
        icon: '☀️',
        badge: 'Tag',
        description: 'Frühdienst an Sonntagen & Feiertagen',
        isHolidayDefault: true,
      },
      {
        id: 'Sa_10-21',
        label: 'Frühdienst (Sa)',
        hours: '10:00–21:00',
        icon: '☀️',
        badge: 'Tag Sa',
        description: 'Samstag Frühdienst mit Anmeldung',
      },
      {
        id: 'Sa_10-19',
        label: 'Spätdienst Azubi',
        hours: '10:00–19:00',
        icon: '☀️',
        badge: 'Azubi Sa',
        description: 'Samstag Spätdienst für Azubis',
      },
      {
        id: 'So_10-22',
        label: 'Rufbereitschaft',
        hours: '10:00–22:00',
        icon: '📞',
        badge: 'Ruf',
        description: 'Rufbereitschaft Wochenende & Feiertage',
        isHolidayDefault: true,
      },
      {
        id: 'So_8-20:30',
        label: 'Azubi Rufbereitschaft',
        hours: '08:00–20:30',
        icon: '📞',
        badge: 'Azubi Ruf',
        description: 'Präsenz 8–12, Ruf 12–20:30',
        isHolidayDefault: true,
      },
      {
        id: 'So_Intern',
        label: 'Intern Tagdienst',
        hours: '08:30–20:30',
        icon: '🎓',
        badge: 'Intern',
        description: 'Wochenend-Tagdienst für Interns',
        isHolidayDefault: true,
      },
    ];
  }

  const [y, m, d] = dateStr.split('-').map(Number);
  const dateObj = new Date(y, m - 1, d);
  const day = dateObj.getDay(); // 0 = Sunday, 6 = Saturday

  if (day === 6) {
    // Saturday
    return [
      {
        id: 'Sa_10-21',
        label: 'Frühdienst (10–21)',
        hours: '10:00–21:00',
        icon: '☀️',
        badge: 'Sa',
        description: 'Anmeldung & Rufbereitschaft',
      },
      {
        id: 'Sa_10-19',
        label: 'Spätdienst (10–19)',
        hours: '10:00–19:00',
        icon: '☀️',
        badge: 'Azubi Sa',
        description: 'Samstag Azubidienst',
      },
      {
        id: 'Sa_10-22',
        label: 'Rufbereitschaft (10–22)',
        hours: '10:00–22:00',
        icon: '📞',
        badge: 'Ruf Sa',
        description: 'TFA Rufbereitschaft Samstag',
      },
      {
        id: 'Sa_Intern',
        label: 'Intern Tagdienst',
        hours: '08:30–20:30',
        icon: '🎓',
        badge: 'Intern Sa',
        description: 'Wochenenddienst Interns',
      },
      {
        id: 'N_Sa-So',
        label: 'Nachtdienst (Sa ➔ So)',
        hours: '20:00–08:00',
        icon: '🌙',
        badge: 'Nacht',
        description: 'Samstagnacht auf Sonntag',
      },
    ];
  }

  if (day === 0) {
    // Sunday
    return [
      {
        id: 'So_8-20',
        label: 'Frühdienst (8–20)',
        hours: '08:00–20:00',
        icon: '☀️',
        badge: 'So',
        description: 'Sonntag Tagdienst in der Klinik',
      },
      {
        id: 'So_10-22',
        label: 'Rufbereitschaft (10–22)',
        hours: '10:00–22:00',
        icon: '📞',
        badge: 'Ruf So',
        description: 'Sonntag Rufbereitschaft',
      },
      {
        id: 'So_8-20:30',
        label: 'Azubi Rufbereitschaft',
        hours: '08:00–20:30',
        icon: '📞',
        badge: 'Azubi Ruf',
        description: 'Präsenz 8–12, Ruf 12–20:30',
      },
      {
        id: 'So_Intern',
        label: 'Intern Tagdienst',
        hours: '08:30–20:30',
        icon: '🎓',
        badge: 'Intern So',
        description: 'Sonntag Tagdienst Interns',
      },
      {
        id: 'N_So-Mo',
        label: 'Nachtdienst (So ➔ Mo)',
        hours: '20:00–08:00',
        icon: '🌙',
        badge: 'Nacht',
        description: 'Sonntagnacht auf Montag',
      },
    ];
  }

  // Weekdays (Montag bis Freitag)
  const weekdayNights: Record<number, { id: string; label: string }> = {
    1: { id: 'N_Mo-Di', label: 'Nachtdienst (Mo ➔ Di)' },
    2: { id: 'N_Di-Mi', label: 'Nachtdienst (Di ➔ Mi)' },
    3: { id: 'N_Mi-Do', label: 'Nachtdienst (Mi ➔ Do)' },
    4: { id: 'N_Do-Fr', label: 'Nachtdienst (Do ➔ Fr)' },
    5: { id: 'N_Fr-Sa', label: 'Nachtdienst (Fr ➔ Sa)' },
  };
  const nightInfo = weekdayNights[day] || { id: 'Nachtdienst', label: 'Nachtdienst' };

  return [
    {
      id: nightInfo.id,
      label: nightInfo.label,
      hours: '20:00–08:00',
      icon: '🌙',
      badge: 'Nacht',
      description: 'Regulärer Nachtdienst',
    },
    {
      id: 'So_8-20',
      label: 'Feiertags-Frühdienst (8–20)',
      hours: '08:00–20:00',
      icon: '☀️',
      badge: 'Feiertag',
      description: 'Sonntags-Schema für Feiertage',
      isHolidayDefault: true,
    },
    {
      id: 'So_10-22',
      label: 'Feiertags-Rufbereitschaft (10–22)',
      hours: '10:00–22:00',
      icon: '📞',
      badge: 'Feiertag Ruf',
      description: 'Feiertags-Rufbereitschaft',
      isHolidayDefault: true,
    },
    {
      id: 'So_8-20:30',
      label: 'Feiertags-Azubi Ruf (8–20:30)',
      hours: '08:00–20:30',
      icon: '📞',
      badge: 'Azubi FT',
      description: 'Präsenz 8–12, Ruf 12–20:30',
      isHolidayDefault: true,
    },
    {
      id: 'So_Intern',
      label: 'Feiertags-Intern Tag (08:30–20:30)',
      hours: '08:30–20:30',
      icon: '🎓',
      badge: 'Intern FT',
      description: 'Intern Feiertagsdienst',
      isHolidayDefault: true,
    },
  ];
};

export const PreAssignedView: React.FC = () => {
  const [shifts, setShifts] = useState<PreAssignedShift[]>([]);
  const [staffList, setStaffList] = useState<StaffMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionError, setActionError] = useState<string | null>(null);

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingShiftId, setEditingShiftId] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({
    staff_id: '',
    shift_date: '',
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
    setEditingShiftId(null);
    setFormError(null);
    setFormData({
      staff_id: '',
      shift_date: '',
      shift_type: 'Nachtdienst',
      is_holiday: true,
      note: '',
    });
    setIsModalOpen(true);
  };

  const handleOpenEditModal = (rec: PreAssignedShift) => {
    setEditingShiftId(rec.id);
    setFormError(null);
    setFormData({
      staff_id: rec.staff_id,
      shift_date: rec.shift_date,
      shift_type: rec.shift_type as PreAssignedShiftType,
      is_holiday: !!rec.is_holiday,
      note: rec.note || '',
    });
    setIsModalOpen(true);
  };

  const handleSavePreAssignment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.staff_id || !formData.shift_date) return;

    const stf = getStaff(formData.staff_id);
    setFormError(null);
    setSaving(true);

    try {
      if (editingShiftId) {
        const updatedRecord: PreAssignedShift = {
          id: editingShiftId,
          staff_id: formData.staff_id,
          staff_identifier: stf ? stf.identifier : formData.staff_id.toUpperCase(),
          shift_date: formData.shift_date,
          shift_type: formData.shift_type,
          is_holiday: formData.is_holiday,
          note: formData.note.trim() || undefined,
        };

        const saved = await updatePreAssigned(editingShiftId, updatedRecord);
        setShifts((prev) => prev.map((s) => (s.id === editingShiftId ? saved : s)));
      } else {
        const newRecord: PreAssignedShift = {
          id: `pa-${Date.now()}`,
          staff_id: formData.staff_id,
          staff_identifier: stf ? stf.identifier : formData.staff_id.toUpperCase(),
          shift_date: formData.shift_date,
          shift_type: formData.shift_type,
          is_holiday: formData.is_holiday,
          note: formData.note.trim() || undefined,
        };

        const created = await createPreAssigned(newRecord);
        setShifts((prev) => [created, ...prev]);
      }

      setFormData({
        staff_id: '',
        shift_date: '',
        shift_type: 'Nachtdienst',
        is_holiday: true,
        note: '',
      });
      setIsModalOpen(false);
      setEditingShiftId(null);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Fehler beim Speichern der Vorbelegung');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    setActionError(null);
    try {
      await deletePreAssigned(id);
      setShifts((prev) => prev.filter((s) => s.id !== id));
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'Fehler beim Löschen der Vorbelegung');
    }
  };

  const sortedShifts = [...shifts].sort((a, b) => a.shift_date.localeCompare(b.shift_date));
  const currentShiftOptions = useMemo(
    () => getShiftOptionsForDate(formData.shift_date),
    [formData.shift_date]
  );

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

      {actionError && (
        <div className="rounded-lg bg-rose-50 border border-rose-200 px-4 py-2.5 text-xs text-rose-700 font-medium">
          {actionError}
        </div>
      )}

      {/* LIST VIEW ONLY */}
      <div className="bg-white rounded-xl border border-stone-200/80 shadow-2xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-[#faf9f6] border-b border-stone-200/80 text-xs font-semibold text-stone-600 uppercase tracking-wider">
              <tr>
                <th className="py-3.5 pl-6 pr-3">Datum</th>
                <th className="px-3 py-3.5">Wochentag</th>
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
                  <td colSpan={8} className="py-8 text-center text-stone-500">
                    Lade Vorbelegungen...
                  </td>
                </tr>
              ) : sortedShifts.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-stone-500">
                    Keine festen Vorbelegungen hinterlegt.
                  </td>
                </tr>
              ) : (
                sortedShifts.map((rec) => {
                  const stf = getStaff(rec.staff_id) || getStaff(rec.staff_identifier);
                  const isNight = isNightShift(rec.shift_type);
                  const weekday = getWeekdayGerman(rec.shift_date);

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

                      <td className="px-3 py-3.5 text-xs font-semibold">
                        <span
                          className={cn(
                            'inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold',
                            weekday === 'Samstag' || weekday === 'Sonntag'
                              ? 'bg-amber-100 text-amber-900 border border-amber-200'
                              : weekday === 'Freitag'
                                ? 'bg-purple-100 text-purple-900 border border-purple-200'
                                : 'bg-stone-100 text-stone-700 border border-stone-200'
                          )}
                        >
                          {weekday}
                        </span>
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
                            <span>{formatShiftLabel(rec.shift_type)}</span>
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-800 border border-amber-200 shadow-2xs">
                            <SunMedium className="h-3.5 w-3.5" />
                            <span>{formatShiftLabel(rec.shift_type)}</span>
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
                        <div className="inline-flex items-center justify-end gap-1">
                          <button
                            onClick={() => handleOpenEditModal(rec)}
                            className="inline-flex items-center p-1 text-stone-400 hover:text-[#324b9b] hover:bg-[#324b9b]/10 rounded transition-colors cursor-pointer"
                            title="Bearbeiten"
                          >
                            <Pencil className="h-3.5 w-3.5" />
                          </button>
                          <button
                            onClick={() => handleDelete(rec.id)}
                            className="inline-flex items-center p-1 text-stone-400 hover:text-rose-600 hover:bg-rose-50 rounded transition-colors cursor-pointer"
                            title="Löschen"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add / Edit Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => {
          setIsModalOpen(false);
          setEditingShiftId(null);
          setFormError(null);
        }}
        title={editingShiftId ? 'Vorbelegung bearbeiten' : 'Dienst vorab zuweisen'}
      >
        <form onSubmit={handleSavePreAssignment} className="space-y-4">
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

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-stone-700 mb-1">
                Datum
              </label>
              <input
                type="date"
                required
                value={formData.shift_date}
                onChange={(e) => {
                  const newDate = e.target.value;
                  const opts = getShiftOptionsForDate(newDate);
                  const stillValid = opts.some((o) => o.id === formData.shift_type);
                  setFormData((prev) => ({
                    ...prev,
                    shift_date: newDate,
                    shift_type: stillValid ? prev.shift_type : (opts[0]?.id || 'Nachtdienst'),
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
                Wochentag & Status
              </label>
              <div className="h-[38px] px-3 flex items-center justify-between rounded-lg border border-stone-200 bg-stone-50/60 text-xs">
                <span className="font-semibold text-stone-800">
                  {formData.shift_date ? getWeekdayGerman(formData.shift_date) : 'Erst Datum wählen'}
                </span>
                <label className="inline-flex items-center gap-1.5 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={formData.is_holiday}
                    onChange={(e) => setFormData({ ...formData, is_holiday: e.target.checked })}
                    className="h-3.5 w-3.5 rounded text-[#324b9b] focus:ring-[#324b9b] border-stone-300"
                  />
                  <span className="text-[11px] font-medium text-amber-900 flex items-center gap-0.5">
                    <Sparkles className="h-3 w-3 text-amber-500" />
                    Feiertag
                  </span>
                </label>
              </div>
            </div>
          </div>

          {/* Schicht-Auswahl als Klick-Kacheln statt Dropdown */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <label className="block text-xs font-semibold text-stone-700">
                Schicht auswählen (Klick)
              </label>
              <span className="text-[11px] text-stone-500">
                {formData.shift_date
                  ? `Verfügbar für ${getWeekdayGerman(formData.shift_date)}`
                  : 'Schichten'}
              </span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-56 overflow-y-auto p-1 border border-stone-200/80 rounded-lg bg-stone-50/40">
              {currentShiftOptions.map((opt) => {
                const isSelected = formData.shift_type === opt.id;
                return (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => {
                      setFormData((prev) => ({
                        ...prev,
                        shift_type: opt.id,
                        is_holiday: opt.isHolidayDefault ? true : prev.is_holiday,
                      }));
                    }}
                    className={cn(
                      'flex items-center justify-between p-2.5 rounded-lg border text-left transition-all cursor-pointer',
                      isSelected
                        ? 'bg-[#324b9b]/10 border-[#324b9b] ring-2 ring-[#324b9b]/25 shadow-2xs font-semibold'
                        : 'bg-white border-stone-200/80 hover:bg-stone-50 hover:border-stone-300 text-stone-700'
                    )}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-base shrink-0">{opt.icon}</span>
                      <div className="min-w-0">
                        <div className="text-xs font-semibold text-stone-900 flex items-center gap-1.5">
                          <span className="truncate">{opt.label}</span>
                          {opt.badge && (
                            <span className="text-[9px] px-1.5 py-0.2 rounded font-medium bg-stone-100 text-stone-600 border border-stone-200 shrink-0">
                              {opt.badge}
                            </span>
                          )}
                        </div>
                        <div className="text-[11px] text-stone-500 font-mono mt-0.5 truncate">
                          {opt.hours}
                        </div>
                      </div>
                    </div>
                    {isSelected ? (
                      <CheckCircle2 className="h-4 w-4 text-[#324b9b] shrink-0 ml-1.5" />
                    ) : (
                      <div className="h-3.5 w-3.5 rounded-full border border-stone-300 shrink-0 ml-1.5" />
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-stone-700 mb-1">
              Notiz / Anlass (optional)
            </label>
            <input
              type="text"
              placeholder="z.B. Ostersonntag, Tag der Arbeit, Tausch..."
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
                setEditingShiftId(null);
                setFormError(null);
              }}
            >
              Abbrechen
            </Button>
            <Button type="submit" variant="primary" disabled={saving}>
              {saving ? 'Speichert...' : editingShiftId ? 'Änderungen speichern' : 'Vorbelegung speichern'}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
