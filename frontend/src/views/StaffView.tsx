import React, { useState, useEffect } from 'react';
import {
  Users,
  Search,
  Plus,
  Moon,
  ShieldCheck,
  Edit2,
  Stethoscope,
} from 'lucide-react';
import type { StaffMember, Beruf, Abteilung } from '../types/api';
import { fetchStaff, createStaff } from '../lib/api';
import { RoleBadge, AbteilungBadge, NachtdienstBadge } from '../components/ui/Badge';
import { getStaffColorScheme } from '../lib/colors';
import { Button } from '../components/ui/Button';
import { Modal } from '../components/ui/Modal';
import { cn } from '../lib/utils';

export const StaffView: React.FC = () => {
  const [staffList, setStaffList] = useState<StaffMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedRole, setSelectedRole] = useState<string>('ALL');

  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingStaff, setEditingStaff] = useState<StaffMember | null>(null);

  // Form State
  const [formData, setFormData] = useState({
    name: '',
    identifier: '',
    beruf: 'TFA' as Beruf,
    abteilung: 'Station' as Abteilung,
    hours: 40,
    nd_possible: true,
    nd_alone: true,
  });

  useEffect(() => {
    loadStaff();
  }, []);

  const loadStaff = async () => {
    setLoading(true);
    const data = await fetchStaff();
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

  const handleOpenAddModal = () => {
    setEditingStaff(null);
    setFormData({
      name: '',
      identifier: '',
      beruf: 'TFA',
      abteilung: 'Station',
      hours: 40,
      nd_possible: true,
      nd_alone: true,
    });
    setIsModalOpen(true);
  };

  const handleOpenEditModal = (staff: StaffMember) => {
    setEditingStaff(staff);
    setFormData({
      name: staff.name,
      identifier: staff.identifier,
      beruf: staff.beruf,
      abteilung: staff.abteilung,
      hours: staff.hours,
      nd_possible: staff.nd_possible,
      nd_alone: staff.nd_alone,
    });
    setIsModalOpen(true);
  };

  const handleSaveStaff = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name || !formData.identifier) return;

    if (editingStaff) {
      setStaffList((prev) =>
        prev.map((s) =>
          s.id === editingStaff.id
            ? { ...s, ...formData }
            : s
        )
      );
    } else {
      const newStaff: StaffMember = {
        id: formData.identifier.toLowerCase(),
        identifier: formData.identifier.toUpperCase(),
        name: formData.name,
        beruf: formData.beruf,
        abteilung: formData.abteilung,
        hours: (formData.beruf === 'Vet' || formData.beruf === 'Tierarzt') ? 0 : Number(formData.hours),
        adult: true,
        reception: false,
        nd_possible: formData.nd_possible,
        nd_alone: formData.nd_alone,
        nd_min_consecutive: 2,
        nd_max_consecutive: 4,
        is_active: true,
      };
      setStaffList((prev) => [newStaff, ...prev]);
      try {
        await createStaff(newStaff);
      } catch (err) {
        console.warn('Backend sync failed, saved locally:', err);
      }
    }
    setIsModalOpen(false);
  };

  return (
    <div className="space-y-6">
      {/* Page Title & Intro */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-stone-900">
            Mitarbeiter
          </h1>
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
            <Stethoscope className="h-4 w-4 text-[#324b9b]" />
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
              className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-all cursor-pointer whitespace-nowrap ${
                selectedRole === role
                  ? 'bg-stone-800 text-white font-semibold shadow-2xs'
                  : 'text-stone-600 hover:bg-stone-100 hover:text-stone-900'
              }`}
            >
              {role === 'ALL' ? 'Alle Rollen' : role === 'Vet' ? 'Tierärzte (Vet)' : role}
            </button>
          ))}
        </div>
      </div>

      {/* Warm Clinical Data Table */}
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
                <th className="px-3 py-3.5">Nachtdienst</th>
                <th className="py-3.5 pl-3 pr-6 text-right">Aktion</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {loading ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-stone-500">
                    Lade Mitarbeiterdaten...
                  </td>
                </tr>
              ) : filteredStaff.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-stone-500">
                    Keine Mitarbeiter gefunden.
                  </td>
                </tr>
              ) : (
                filteredStaff.map((staff) => (
                  <tr
                    key={staff.id}
                    className="hover:bg-amber-50/20 transition-colors group"
                  >
                    {/* Name + Warm Initials Avatar */}
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
                        <span className="font-semibold text-stone-900">{staff.name}</span>
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

                    {/* Hours (Centered) */}
                    <td className="px-3 py-3.5 text-center text-stone-700 text-xs font-semibold">
                      {staff.beruf === 'Vet' || staff.beruf === 'Tierarzt' ? '-' : staff.hours}
                    </td>

                    {/* Night Shift Qualification */}
                    <td className="px-3 py-3.5">
                      <NachtdienstBadge nd_possible={staff.nd_possible} nd_alone={staff.nd_alone} />
                    </td>

                    {/* Actions */}
                    <td className="py-3.5 pl-3 pr-6 text-right">
                      <button
                        onClick={() => handleOpenEditModal(staff)}
                        className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-stone-600 hover:text-[#324b9b] hover:bg-blue-50/80 rounded-md transition-colors cursor-pointer"
                      >
                        <Edit2 className="h-3.5 w-3.5" />
                        Bearbeiten
                      </button>
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
          <div>
            <label className="block text-xs font-semibold text-stone-700 mb-1">
              Vollständiger Name
            </label>
            <input
              type="text"
              required
              placeholder="z.B. Dr. Clara Meyer"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              className="w-full px-3 py-2 text-sm bg-stone-50/70 border border-stone-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#324b9b]/30 focus:border-[#324b9b]"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-semibold text-stone-700 mb-1">
                Kürzel
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
                onChange={(e) =>
                  setFormData({ ...formData, beruf: e.target.value as Beruf })
                }
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
                value={formData.abteilung}
                onChange={(e) =>
                  setFormData({ ...formData, abteilung: e.target.value as Abteilung })
                }
                className="w-full px-3 py-2 text-sm bg-stone-50/70 border border-stone-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-[#324b9b]/30 focus:border-[#324b9b]"
              >
                <option value="Station">Station</option>
                <option value="OP">OP</option>
                <option value="Sprechstunde">Sprechstunde</option>
                <option value="Sonstiges">Sonstiges</option>
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

          {/* Night Shift Switches */}
          <div className="pt-2 border-t border-stone-100 space-y-3">
            <label className="flex items-center gap-2.5 cursor-pointer">
              <input
                type="checkbox"
                checked={formData.nd_possible}
                onChange={(e) =>
                  setFormData({ ...formData, nd_possible: e.target.checked })
                }
                className="h-4 w-4 rounded text-[#324b9b] focus:ring-[#324b9b] border-stone-300"
              />
              <span className="text-xs font-medium text-stone-700">
                Nachtdienst-fähig
              </span>
            </label>

            {formData.nd_possible && (
              <label className="flex items-center gap-2.5 cursor-pointer pl-6">
                <input
                  type="checkbox"
                  checked={formData.nd_alone}
                  onChange={(e) =>
                    setFormData({ ...formData, nd_alone: e.target.checked })
                  }
                  className="h-4 w-4 rounded text-[#324b9b] focus:ring-[#324b9b] border-stone-300"
                />
                <span className="text-xs font-medium text-stone-700">
                  Alleine tauglich
                </span>
              </label>
            )}
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
              {editingStaff ? 'Änderungen speichern' : 'Mitarbeiter erstellen'}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
