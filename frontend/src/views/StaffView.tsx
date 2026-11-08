import React, { useState, useEffect } from 'react';
import {
  Users,
  Search,
  Plus,
  Moon,
  ShieldCheck,
  Edit2,
  Stethoscope,
  AlertTriangle,
  Calendar,
  ChevronDown,
  Check,
  Trash2,
  Power,
  AlertCircle,
} from 'lucide-react';
import type { StaffMember, Beruf, Abteilung } from '../types/api';
import { fetchStaff, createStaff, updateStaff, deleteStaff } from '../lib/api';
import { RoleBadge, AbteilungBadge, NachtdienstBadge } from '../components/ui/Badge';
import { getStaffColorScheme } from '../lib/colors';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { cn, isBirthdayToday } from '../lib/utils';

const WEEKDAYS = [
  { id: 1, label: 'Mo', full: 'Montag' },
  { id: 2, label: 'Di', full: 'Dienstag' },
  { id: 3, label: 'Mi', full: 'Mittwoch' },
  { id: 4, label: 'Do', full: 'Donnerstag' },
  { id: 5, label: 'Fr', full: 'Freitag' },
  { id: 6, label: 'Sa', full: 'Samstag' },
  { id: 7, label: 'So', full: 'Sonntag' },
];

export const StaffView: React.FC = () => {
  const [staffList, setStaffList] = useState<StaffMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedRole, setSelectedRole] = useState<string>('ALL');

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingStaff, setEditingStaff] = useState<StaffMember | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Form State
  const [formData, setFormData] = useState({
    name: '',
    identifier: '',
    beruf: 'TFA' as Beruf,
    abteilung: 'other' as Abteilung,
    hours: 40,
    adult: true,
    reception: false,
    nd_possible: true,
    nd_alone: true,
    nd_min_consecutive: 2,
    nd_max_consecutive: 4 as number | null,
    birthday: '',
    available_from: '',
    is_active: true,
  });

  // Weekday availability: day IDs 1..7 (1=Mo..7=So) where staff is available
  const [availableWeekdays, setAvailableWeekdays] = useState<number[]>([1, 2, 3, 4, 5, 6, 7]);
  const [showAdvanced, setShowAdvanced] = useState(false);

  useEffect(() => {
    loadStaff();
  }, []);

  const loadStaff = async () => {
    setLoading(true);
    const data = await fetchStaff(false);
    setStaffList(data);
    setLoading(false);
  };

  const filteredStaff = staffList.filter((s) => {
    const matchesSearch =
      s.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      s.identifier.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesRole =
      selectedRole === 'ALL' ||
      s.beruf === selectedRole ||
      (selectedRole === 'Vet' && s.beruf === 'Tierarzt');
    return matchesSearch && matchesRole;
  });

  // Metric counts
  const totalActive = staffList.filter((s) => s.is_active).length;
  const totalVets = staffList.filter(
    (s) => s.is_active && (s.beruf === 'Vet' || s.beruf === 'Tierarzt')
  ).length;
  const totalTFAs = staffList.filter(
    (s) => s.is_active && (s.beruf === 'TFA' || s.beruf === 'Azubi')
  ).length;
  const totalNightCapable = staffList.filter((s) => s.is_active && s.nd_possible).length;
  const birthdayStaff = staffList.filter((s) => s.is_active && isBirthdayToday(s.birthday));

  const handleOpenAddModal = () => {
    setEditingStaff(null);
    setFormError(null);
    setFormData({
      name: '',
      identifier: '',
      beruf: 'TFA',
      abteilung: 'other',
      hours: 40,
      adult: true,
      reception: false,
      nd_possible: true,
      nd_alone: true,
      nd_min_consecutive: 2,
      nd_max_consecutive: 4,
      birthday: '',
      available_from: '',
      is_active: true,
    });
    setAvailableWeekdays([1, 2, 3, 4, 5, 6, 7]);
    setShowAdvanced(false);
    setIsModalOpen(true);
  };

  const handleOpenEditModal = (staff: StaffMember) => {
    setEditingStaff(staff);
    setFormError(null);
    const a = (staff.abteilung || '').trim().toLowerCase();
    const cleanAbteilung = a === 'station' ? 'Station' : a === 'op' ? 'OP' : 'other';
    setFormData({
      name: staff.name,
      identifier: staff.identifier,
      beruf: staff.beruf,
      abteilung: cleanAbteilung as Abteilung,
      hours: staff.hours,
      adult: staff.adult ?? true,
      reception: staff.reception ?? false,
      nd_possible: staff.nd_possible ?? true,
      nd_alone: staff.nd_alone ?? true,
      nd_min_consecutive: staff.nd_min_consecutive ?? 2,
      nd_max_consecutive: staff.nd_max_consecutive ?? 4,
      birthday: staff.birthday ?? '',
      available_from: staff.available_from ?? '',
      is_active: staff.is_active ?? true,
    });

    const ex = staff.nd_exceptions || [];
    setAvailableWeekdays([1, 2, 3, 4, 5, 6, 7].filter((d) => !ex.includes(d)));
    setShowAdvanced(Boolean(staff.birthday || staff.available_from));
    setIsModalOpen(true);
  };

  const toggleWeekday = (dayId: number) => {
    setAvailableWeekdays((prev) =>
      prev.includes(dayId) ? prev.filter((d) => d !== dayId) : [...prev, dayId].sort((a, b) => a - b)
    );
  };

  const handleSaveStaff = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name || !formData.identifier) return;

    // Blocked days are those not in availableWeekdays
    const nd_exceptions = [1, 2, 3, 4, 5, 6, 7].filter((d) => !availableWeekdays.includes(d));

    const isVet = formData.beruf === 'Vet' || formData.beruf === 'Tierarzt';
    const cleanHours = isVet ? 0 : Number(formData.hours);
    const cleanBirthday = formData.birthday && formData.birthday.trim() ? formData.birthday.trim() : null;
    const cleanAvailableFrom = formData.available_from && formData.available_from.trim() ? formData.available_from.trim() : null;

    setFormError(null);
    setSaving(true);

    try {
      if (editingStaff) {
        const updated: StaffMember = {
          ...editingStaff,
          name: formData.name.trim(),
          identifier: formData.identifier.trim().toUpperCase(),
          beruf: formData.beruf,
          abteilung: formData.abteilung,
          hours: cleanHours,
          adult: formData.adult,
          reception: formData.reception,
          nd_possible: formData.adult ? formData.nd_possible : false,
          nd_alone: formData.adult && formData.nd_possible ? formData.nd_alone : false,
          nd_min_consecutive: formData.nd_min_consecutive,
          nd_max_consecutive: formData.nd_max_consecutive,
          nd_exceptions,
          birthday: cleanBirthday,
          available_from: cleanAvailableFrom,
          is_active: formData.is_active,
        };

        const saved = await updateStaff(editingStaff.id, updated);
        setStaffList((prev) => prev.map((s) => (s.id === editingStaff.id ? saved : s)));
      } else {
        const newStaff: StaffMember = {
          id: formData.identifier.trim().toLowerCase(),
          identifier: formData.identifier.trim().toUpperCase(),
          name: formData.name.trim(),
          beruf: formData.beruf,
          abteilung: formData.abteilung,
          hours: cleanHours,
          adult: formData.adult,
          reception: formData.reception,
          nd_possible: formData.adult ? formData.nd_possible : false,
          nd_alone: formData.adult && formData.nd_possible ? formData.nd_alone : false,
          nd_min_consecutive: formData.nd_min_consecutive,
          nd_max_consecutive: formData.nd_max_consecutive,
          nd_exceptions,
          birthday: cleanBirthday,
          available_from: cleanAvailableFrom,
          is_active: formData.is_active,
        };

        const created = await createStaff(newStaff);
        setStaffList((prev) => [created, ...prev]);
      }
      setIsModalOpen(false);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Fehler beim Speichern des Mitarbeiters.');
    } finally {
      setSaving(false);
    }
  };

  const handleToggleStaffActive = async (staff: StaffMember) => {
    try {
      const updated = await updateStaff(staff.id, { ...staff, is_active: !staff.is_active });
      setStaffList((prev) => prev.map((s) => (s.id === staff.id ? updated : s)));
    } catch (err) {
      console.error('Failed to toggle active state:', err);
    }
  };

  const handleDeleteStaff = async (staff: StaffMember) => {
    setFormError(null);
    setSaving(true);
    try {
      await deleteStaff(staff.id, true);
      setStaffList((prev) => prev.filter((s) => s.id !== staff.id));
      setIsModalOpen(false);
    } catch (err) {
      setFormError(err instanceof Error ? err.message : 'Fehler beim Löschen des Mitarbeiters.');
    } finally {
      setSaving(false);
    }
  };

  const renderAvailabilityBadge = (exceptions?: number[]) => {
    const blocked = new Set(exceptions || []);
    const available = [1, 2, 3, 4, 5, 6, 7].filter((d) => !blocked.has(d));

    if (available.length === 7) {
      return (
        <span className="text-stone-400 text-xs font-normal">
          Alle
        </span>
      );
    }
    if (available.length === 0) {
      return (
        <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-rose-50 text-rose-700 border border-rose-200">
          Keine
        </span>
      );
    }
    const dayNames: Record<number, string> = {
      1: 'Mo', 2: 'Di', 3: 'Mi', 4: 'Do', 5: 'Fr', 6: 'Sa', 7: 'So',
    };
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-stone-100 text-stone-800 border border-stone-200/80">
        {available.map((d) => dayNames[d]).join(', ')}
      </span>
    );
  };

  return (
    <div className="space-y-6">
      {/* Page Title & Intro */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2.5 flex-wrap">
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-stone-900">
              Mitarbeiter
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
            Personalstamm, Qualifikationen, Jugendschutz und Wochentags-Verfügbarkeiten.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={handleOpenAddModal} variant="primary">
            <Plus className="h-4 w-4 mr-1.5" />
            Mitarbeiter anlegen
          </Button>
        </div>
      </div>

      {/* KPI Summary Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="rounded-xl border border-stone-200/80 bg-white p-4 shadow-2xs">
          <div className="flex items-center justify-between text-stone-500 text-xs font-medium">
            <span>Gesamt</span>
            <Users className="h-4 w-4 text-stone-400" />
          </div>
          <div className="mt-2">
            <span className="text-2xl font-bold text-stone-900">{totalActive}</span>
          </div>
        </div>

        <div className="rounded-xl border border-stone-200/80 bg-white p-4 shadow-2xs">
          <div className="flex items-center justify-between text-stone-500 text-xs font-medium">
            <span>Tierärzte</span>
            <Stethoscope className="h-4 w-4 text-rose-600" />
          </div>
          <div className="mt-2">
            <span className="text-2xl font-bold text-stone-900">{totalVets}</span>
          </div>
        </div>

        <div className="rounded-xl border border-stone-200/80 bg-white p-4 shadow-2xs">
          <div className="flex items-center justify-between text-stone-500 text-xs font-medium">
            <span>TFAs & Azubis</span>
            <ShieldCheck className="h-4 w-4 text-emerald-600" />
          </div>
          <div className="mt-2">
            <span className="text-2xl font-bold text-stone-900">{totalTFAs}</span>
          </div>
        </div>

        <div className="rounded-xl border border-stone-200/80 bg-white p-4 shadow-2xs">
          <div className="flex items-center justify-between text-stone-500 text-xs font-medium">
            <span>Nachtdienst</span>
            <Moon className="h-4 w-4 text-amber-600" />
          </div>
          <div className="mt-2">
            <span className="text-2xl font-bold text-stone-900">{totalNightCapable}</span>
          </div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 bg-white p-3 rounded-xl border border-stone-200/80 shadow-2xs">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-stone-400" />
          <input
            type="text"
            placeholder="Name oder Kürzel suchen..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-9 pr-4 py-1.5 text-sm bg-stone-50/70 border border-stone-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#324b9b]/20 focus:border-[#324b9b] transition-all"
          />
        </div>

        {/* Role Filter Tabs */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 sm:pb-0">
          {(['ALL', 'Vet', 'TFA', 'Azubi', 'Intern'] as const).map((role) => (
            <button
              key={role}
              onClick={() => setSelectedRole(role)}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all cursor-pointer whitespace-nowrap ${selectedRole === role
                  ? 'bg-stone-800 text-white font-semibold shadow-2xs'
                  : 'text-stone-600 hover:bg-stone-100 hover:text-stone-900'
                }`}
            >
              {role === 'ALL' ? 'Alle Rollen' : role === 'Vet' ? 'Tierärzte (Vet)' : role}
            </button>
          ))}
        </div>
      </div>

      {/* Clinical Staff Table */}
      <div className="bg-white rounded-xl border border-stone-200/80 shadow-2xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-[#faf9f6] border-b border-stone-200/80 text-xs font-semibold text-stone-600 uppercase tracking-wider">
              <tr>
                <th className="py-3.5 pl-6 pr-3">Mitarbeiter</th>
                <th className="px-3 py-3.5">Kürzel</th>
                <th className="px-3 py-3.5">Rolle</th>
                <th className="px-3 py-3.5">Abteilung</th>
                <th className="px-3 py-3.5 text-center">Wochenstunden</th>
                <th className="px-3 py-3.5 text-center">Volljährig</th>
                <th className="px-3 py-3.5">Nachtdienst</th>
                <th className="px-3 py-3.5 text-center">Anmeldung</th>
                <th className="px-3 py-3.5">Verfügbarkeit</th>
                <th className="py-3.5 pl-3 pr-6 text-right">Aktion</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {loading ? (
                <tr>
                  <td colSpan={10} className="py-8 text-center text-stone-500">
                    Lade Mitarbeiterdaten...
                  </td>
                </tr>
              ) : filteredStaff.length === 0 ? (
                <tr>
                  <td colSpan={10} className="py-8 text-center text-stone-500">
                    Keine Mitarbeiter gefunden.
                  </td>
                </tr>
              ) : (
                filteredStaff.map((staff) => (
                  <tr
                    key={staff.id}
                    className={cn(
                      'hover:bg-amber-50/20 transition-colors group',
                      staff.is_active === false && 'opacity-50 bg-stone-50/60'
                    )}
                  >
                    {/* Name + Initials Avatar + Birthday */}
                    <td className="py-3.5 pl-6 pr-3">
                      <div className="flex items-center gap-3">
                        <div
                          className={cn(
                            'h-8 w-8 rounded-full border font-bold text-xs flex items-center justify-center shadow-2xs shrink-0',
                            getStaffColorScheme(staff.beruf, staff.abteilung).avatar
                          )}
                        >
                          {staff.name
                            .split(' ')
                            .map((n) => n[0])
                            .slice(0, 2)
                            .join('')}
                        </div>
                        <div>
                          <div className="flex items-center gap-1.5">
                            <span className="font-semibold text-stone-900">{staff.name}</span>
                            {staff.is_active === false && (
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-stone-200 text-stone-700 font-semibold">
                                Inaktiv
                              </span>
                            )}
                          </div>
                          {staff.birthday && (
                            <span className="text-[11px] text-stone-400 block font-sans">
                              🎂 {staff.birthday}
                            </span>
                          )}
                        </div>
                      </div>
                    </td>

                    {/* Identifier */}
                    <td className="px-3 py-3.5 font-mono text-xs text-stone-600 font-bold">
                      {staff.identifier}
                    </td>

                    {/* Role Badge */}
                    <td className="px-3 py-3.5">
                      <RoleBadge role={staff.beruf} />
                    </td>

                    {/* Department */}
                    <td className="px-3 py-3.5">
                      <AbteilungBadge abteilung={staff.abteilung} beruf={staff.beruf} />
                    </td>

                    {/* Hours */}
                    <td className="px-3 py-3.5 text-center text-stone-700 text-xs font-semibold">
                      {staff.beruf === 'Vet' || staff.beruf === 'Tierarzt' ? '-' : `${staff.hours} h`}
                    </td>

                    {/* Volljährig */}
                    <td className="px-3 py-3.5 text-center text-xs">
                      {staff.adult !== false ? (
                        <span className="text-stone-700 font-medium">Ja</span>
                      ) : (
                        <span
                          className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[11px] font-bold bg-amber-50 text-amber-800 border border-amber-300 shadow-2xs"
                          title="Minderjährig (< 18 J.) – Jugendarbeitsschutzgesetz verbietet Nachtdienste"
                        >
                          <AlertTriangle className="h-2.5 w-2.5 text-amber-600" />
                          &lt; 18 J.
                        </span>
                      )}
                    </td>

                    {/* Nachtdienst */}
                    <td className="px-3 py-3.5">
                      <NachtdienstBadge nd_possible={staff.nd_possible} nd_alone={staff.nd_alone} />
                    </td>

                    {/* Anmeldung */}
                    <td className="px-3 py-3.5 text-center text-xs">
                      {staff.reception ? (
                        <span
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-teal-50 text-teal-800 border border-teal-200/80 shadow-2xs"
                          title="Anmeldung & Rezeption tauglich"
                        >
                          <Check className="h-3 w-3 text-teal-600" />
                          Ja
                        </span>
                      ) : (
                        <span className="text-stone-300 font-medium">—</span>
                      )}
                    </td>

                    {/* Weekday Availability */}
                    <td className="px-3 py-3.5">
                      {renderAvailabilityBadge(staff.nd_exceptions)}
                    </td>

                    {/* Actions */}
                    <td className="py-3.5 pl-3 pr-6 text-right">
                      <div className="inline-flex items-center justify-end gap-1">
                        <button
                          onClick={() => handleToggleStaffActive(staff)}
                          className={cn(
                            'inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded-md transition-colors cursor-pointer',
                            staff.is_active !== false
                              ? 'text-emerald-700 hover:bg-emerald-50'
                              : 'text-stone-400 hover:text-stone-700 hover:bg-stone-100'
                          )}
                          title={
                            staff.is_active !== false
                              ? 'Aktiv (Klicken zum Deaktivieren)'
                              : 'Inaktiv (Klicken zum Aktivieren)'
                          }
                        >
                          <Power className="h-3.5 w-3.5" />
                        </button>
                        <button
                          onClick={() => handleOpenEditModal(staff)}
                          className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-stone-600 hover:text-[#324b9b] hover:bg-blue-50/80 rounded-md transition-colors cursor-pointer"
                        >
                          <Edit2 className="h-3.5 w-3.5" />
                          Bearbeiten
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Add / Edit Staff Modal */}
      <Modal
        isOpen={isModalOpen}
        onClose={() => setIsModalOpen(false)}
        title={editingStaff ? `Mitarbeiter bearbeiten: ${editingStaff.name}` : 'Neuen Mitarbeiter anlegen'}
      >
        <form onSubmit={handleSaveStaff} className="space-y-4">
          {formError && (
            <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-start gap-2">
              <AlertCircle className="h-4 w-4 text-rose-600 shrink-0 mt-0.5" />
              <span>{formError}</span>
            </div>
          )}
          {/* Section 1: Basic Information */}
          <div>
            <label className="block text-xs font-semibold text-stone-700 mb-1">
              Vollständiger Name
            </label>
            <input
              type="text"
              required
              placeholder="z.B. Dr. Clara Meyer oder Sarah Schmidt"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full px-3 py-2 text-sm bg-stone-50/70 border border-stone-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#324b9b]/30 focus:border-[#324b9b]"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-stone-700 mb-1">
                Kürzel (max. 4 Zeichen)
              </label>
              <input
                type="text"
                required
                maxLength={4}
                placeholder="z.B. MEY"
                value={formData.identifier}
                onChange={(e) =>
                  setFormData({ ...formData, identifier: e.target.value.toUpperCase() })
                }
                className="w-full px-3 py-2 text-sm font-mono bg-stone-50/70 border border-stone-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#324b9b]/30 focus:border-[#324b9b]"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-stone-700 mb-1">
                Rolle / Beruf
              </label>
              <select
                value={formData.beruf}
                onChange={(e) => {
                  const b = e.target.value as Beruf;
                  setFormData({
                    ...formData,
                    beruf: b,
                    nd_min_consecutive: b === 'Azubi' ? 1 : formData.nd_min_consecutive,
                  });
                }}
                className="w-full px-3 py-2 text-sm bg-stone-50/70 border border-stone-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#324b9b]/30 focus:border-[#324b9b]"
              >
                <option value="Vet">Tierarzt (Vet)</option>
                <option value="TFA">TFA</option>
                <option value="Azubi">Azubi</option>
                <option value="Intern">Intern</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-stone-700 mb-1">
                Abteilung
              </label>
              <select
                value={formData.abteilung === 'Station' || formData.abteilung === 'OP' ? formData.abteilung : 'other'}
                onChange={(e) =>
                  setFormData({ ...formData, abteilung: e.target.value as Abteilung })
                }
                className="w-full px-3 py-2 text-sm bg-stone-50/70 border border-stone-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#324b9b]/30 focus:border-[#324b9b]"
              >
                <option value="other">Keine (—)</option>
                <option value="Station">Station</option>
                <option value="OP">OP</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-stone-700 mb-1">
                Wochenstunden
              </label>
              <input
                type="number"
                disabled={formData.beruf === 'Vet' || formData.beruf === 'Tierarzt'}
                min={0}
                max={60}
                value={formData.beruf === 'Vet' || formData.beruf === 'Tierarzt' ? 0 : formData.hours}
                onChange={(e) =>
                  setFormData({ ...formData, hours: Number(e.target.value) })
                }
                className="w-full px-3 py-2 text-sm bg-stone-50/70 border border-stone-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#324b9b]/30 focus:border-[#324b9b] disabled:opacity-50"
              />
            </div>
          </div>

          {/* Section 2: Qualifikationen & Schutz (Kompakt & Übersichtlich) */}
          <div className="pt-2 border-t border-stone-100 space-y-2">
            <h4 className="text-xs font-bold uppercase tracking-wider text-stone-500">
              Qualifikation & Schutz
            </h4>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
              {/* Aktiv / Inaktiv */}
              <label className="flex items-center gap-2.5 p-2 rounded-lg bg-stone-50/80 border border-stone-200/70 hover:bg-stone-100/70 cursor-pointer transition-colors">
                <input
                  type="checkbox"
                  checked={formData.is_active}
                  onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                  className="h-4 w-4 rounded text-[#324b9b] focus:ring-[#324b9b] border-stone-300"
                />
                <span className="text-xs font-semibold text-stone-800">
                  Aktiv im Dienstplan
                </span>
              </label>

              {/* Volljährig */}
              <label className="flex items-center gap-2.5 p-2 rounded-lg bg-stone-50/80 border border-stone-200/70 hover:bg-stone-100/70 cursor-pointer transition-colors">
                <input
                  type="checkbox"
                  checked={formData.adult}
                  onChange={(e) => {
                    const isAdult = e.target.checked;
                    setFormData({
                      ...formData,
                      adult: isAdult,
                      nd_possible: isAdult ? formData.nd_possible : false,
                      nd_alone: isAdult ? formData.nd_alone : false,
                    });
                  }}
                  className="h-4 w-4 rounded text-[#324b9b] focus:ring-[#324b9b] border-stone-300"
                />
                <span className="text-xs font-semibold text-stone-800">
                  Volljährig
                </span>
              </label>

              {/* Anmeldung / Rezeption */}
              <label className="flex items-center gap-2.5 p-2 rounded-lg bg-stone-50/80 border border-stone-200/70 hover:bg-stone-100/70 cursor-pointer transition-colors">
                <input
                  type="checkbox"
                  checked={formData.reception}
                  onChange={(e) => setFormData({ ...formData, reception: e.target.checked })}
                  className="h-4 w-4 rounded text-[#324b9b] focus:ring-[#324b9b] border-stone-300"
                />
                <span className="text-xs font-semibold text-stone-800">
                  Anmeldung & Rezeption
                </span>
              </label>
            </div>

            {/* Nachtdienst 1-Klick 3-Wege-Auswahl */}
            <div className="p-2.5 rounded-lg bg-stone-50/80 border border-stone-200/70 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-stone-800">
                  Nachtdienst
                </span>
                {!formData.adult && (
                  <span className="text-[11px] text-amber-700 font-medium">
                    ⚠️ U18: Nachtdienst gesetzlich gesperrt (JArbSchG)
                  </span>
                )}
              </div>

              {/* 3 Optionen: Kein Nachtdienst (None), Zu zweit (Together), Alleine (Alone) */}
              <div className="grid grid-cols-3 gap-1.5 p-1 bg-stone-200/70 rounded-lg text-xs font-medium">
                <button
                  type="button"
                  onClick={() =>
                    setFormData({ ...formData, nd_possible: false, nd_alone: false })
                  }
                  className={cn(
                    'py-2 px-2 rounded-md transition-all cursor-pointer text-center font-medium',
                    !formData.nd_possible
                      ? 'bg-white text-stone-900 font-bold shadow-2xs'
                      : 'text-stone-600 hover:text-stone-900'
                  )}
                >
                  Kein Nachtdienst
                </button>
                <button
                  type="button"
                  disabled={!formData.adult}
                  onClick={() =>
                    setFormData({ ...formData, nd_possible: true, nd_alone: false })
                  }
                  className={cn(
                    'py-2 px-2 rounded-md transition-all cursor-pointer text-center font-medium disabled:opacity-40 disabled:cursor-not-allowed',
                    formData.nd_possible && !formData.nd_alone
                      ? 'bg-white text-[#324b9b] font-bold shadow-2xs ring-1 ring-blue-200'
                      : 'text-stone-600 hover:text-stone-900'
                  )}
                >
                  Zu zweit
                </button>
                <button
                  type="button"
                  disabled={!formData.adult}
                  onClick={() =>
                    setFormData({ ...formData, nd_possible: true, nd_alone: true })
                  }
                  className={cn(
                    'py-2 px-2 rounded-md transition-all cursor-pointer text-center font-medium disabled:opacity-40 disabled:cursor-not-allowed',
                    formData.nd_possible && formData.nd_alone
                      ? 'bg-white text-purple-900 font-bold shadow-2xs ring-1 ring-purple-200'
                      : 'text-stone-600 hover:text-stone-900'
                  )}
                >
                  Alleine
                </button>
              </div>

              <div className="text-[11px] text-stone-500">
                {!formData.nd_possible ? (
                  <span>Wird für keine Notdienst-Nächte eingeteilt.</span>
                ) : !formData.nd_alone ? (
                  <span>Nur als Zweitbesetzung mit erfahrener Begleitung einteilbar.</span>
                ) : (
                  <span>Kann Notdienst-Nächte eigenständig alleine besetzen.</span>
                )}
              </div>
            </div>
          </div>

          {/* Section 3: Verfügbare Wochentage (Einfaches An-/Abwählen) */}
          <div className="pt-2 border-t border-stone-100 space-y-2">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-bold uppercase tracking-wider text-stone-500">
                Verfügbare Wochentage
              </h4>
              {availableWeekdays.length < 7 && (
                <button
                  type="button"
                  onClick={() => setAvailableWeekdays([1, 2, 3, 4, 5, 6, 7])}
                  className="text-[11px] text-[#324b9b] hover:underline font-medium cursor-pointer"
                >
                  Alle auswählen
                </button>
              )}
            </div>

            {/* 7 Day Pills */}
            <div className="grid grid-cols-7 gap-1.5">
              {WEEKDAYS.map((day) => {
                const isAvailable = availableWeekdays.includes(day.id);
                return (
                  <button
                    key={day.id}
                    type="button"
                    onClick={() => toggleWeekday(day.id)}
                    className={cn(
                      'py-2 rounded-lg text-xs font-bold transition-all cursor-pointer border text-center flex flex-col items-center justify-center gap-0.5',
                      isAvailable
                        ? 'bg-[#324b9b] text-white border-[#324b9b] shadow-2xs'
                        : 'bg-stone-100 text-stone-400 border-stone-200 hover:bg-stone-200/70'
                    )}
                    title={isAvailable ? `${day.full}: Verfügbar` : `${day.full}: Nicht verfügbar`}
                  >
                    <span>{day.label}</span>
                    <span className="text-[9px] font-normal opacity-85">
                      {isAvailable ? '✓' : '✕'}
                    </span>
                  </button>
                );
              })}
            </div>

            {/* Status Feedback only when restricted */}
            {availableWeekdays.length === 0 ? (
              <div className="text-[11px] text-rose-600 font-semibold">
                ⚠️ An keinem Tag verfügbar
              </div>
            ) : availableWeekdays.length < 7 ? (
              <div className="text-[11px] text-stone-500">
                Ausgewählt: <strong className="text-stone-800">{availableWeekdays.map((d) => WEEKDAYS.find((w) => w.id === d)?.label).join(', ')}</strong>
              </div>
            ) : null}
          </div>

          {/* Section 4: Collapsible Advanced Parameters */}
          <div className="pt-2 border-t border-stone-100">
            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="flex items-center gap-1.5 text-xs text-stone-600 font-medium hover:text-stone-900 cursor-pointer"
            >
              <Calendar className="h-3.5 w-3.5" />
              <span>Geburtstag & weitere Parameter {showAdvanced ? 'ausblenden' : 'einblenden'}</span>
              <ChevronDown className={cn('h-3.5 w-3.5 transition-transform', showAdvanced ? 'rotate-180' : '')} />
            </button>

            {showAdvanced && (
              <div className="mt-3 p-3 rounded-lg bg-stone-50 border border-stone-200/70 space-y-3 text-xs">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-stone-700 font-semibold mb-1">
                      Geburtstag (MM-DD)
                    </label>
                    <input
                      type="text"
                      placeholder="z.B. 04-15"
                      pattern="^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$"
                      value={formData.birthday}
                      onChange={(e) => setFormData({ ...formData, birthday: e.target.value })}
                      className="w-full px-2.5 py-1.5 bg-white border border-stone-200 rounded text-xs focus:ring-1 focus:ring-[#324b9b]"
                    />
                    <span className="text-[10px] text-stone-400 mt-0.5 block">
                      Wird vom Solver automatisch für alle Dienste freigehalten.
                    </span>
                  </div>
                  <div>
                    <label className="block text-stone-700 font-semibold mb-1">
                      Verfügbar ab (bei Neueintritt)
                    </label>
                    <input
                      type="date"
                      value={formData.available_from}
                      onChange={(e) => setFormData({ ...formData, available_from: e.target.value })}
                      className="w-full px-2.5 py-1.5 bg-white border border-stone-200 rounded text-xs focus:ring-1 focus:ring-[#324b9b]"
                    />
                    <span className="text-[10px] text-stone-400 mt-0.5 block">
                      Erst ab diesem Datum für Dienste verfügbar.
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3 pt-1 border-t border-stone-200/60">
                  <div>
                    <label className="block text-stone-700 font-semibold mb-1">
                      Min. Nächte am Stück
                    </label>
                    <input
                      type="number"
                      min={1}
                      max={4}
                      value={formData.nd_min_consecutive}
                      onChange={(e) => setFormData({ ...formData, nd_min_consecutive: Number(e.target.value) })}
                      className="w-full px-2.5 py-1.5 bg-white border border-stone-200 rounded text-xs"
                    />
                  </div>
                  <div>
                    <label className="block text-stone-700 font-semibold mb-1">
                      Max. Nächte am Stück
                    </label>
                    <input
                      type="number"
                      min={1}
                      max={7}
                      value={formData.nd_max_consecutive ?? 4}
                      onChange={(e) => setFormData({ ...formData, nd_max_consecutive: Number(e.target.value) })}
                      className="w-full px-2.5 py-1.5 bg-white border border-stone-200 rounded text-xs"
                    />
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="pt-4 flex items-center justify-between gap-2 border-t border-stone-100">
            <div>
              {editingStaff && (
                <Button
                  type="button"
                  variant="ghost"
                  disabled={saving}
                  onClick={() => handleDeleteStaff(editingStaff)}
                  className="text-rose-600 hover:bg-rose-50 hover:text-rose-700"
                >
                  <Trash2 className="h-4 w-4 mr-1.5" />
                  Löschen
                </Button>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="outline"
                disabled={saving}
                onClick={() => setIsModalOpen(false)}
              >
                Abbrechen
              </Button>
              <Button type="submit" variant="primary" disabled={saving}>
                <Check className="h-4 w-4 mr-1.5" />
                {editingStaff ? 'Änderungen speichern' : 'Mitarbeiter anlegen'}
              </Button>
            </div>
          </div>
        </form>
      </Modal>
    </div>
  );
};
