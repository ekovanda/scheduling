import React from 'react';
import { Calendar, Users, CalendarDays, Scale, Info, ChevronDown } from 'lucide-react';
import { cn } from '../lib/utils';

export type NavTab = 'staff' | 'absences' | 'matrix' | 'fairness' | 'about';

interface NavbarProps {
  activeTab: NavTab;
  onTabChange: (tab: NavTab) => void;
  currentQuarter: string;
  onQuarterChange: (q: string) => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  onTabChange,
  currentQuarter,
  onQuarterChange,
}) => {
  const tabs = [
    { id: 'staff' as NavTab, label: 'Mitarbeiter', icon: Users },
    { id: 'absences' as NavTab, label: 'Abwesenheiten', icon: CalendarDays },
    { id: 'matrix' as NavTab, label: 'Dienstplan Matrix', icon: Calendar },
    { id: 'fairness' as NavTab, label: 'Fairness & Balance', icon: Scale },
    { id: 'about' as NavTab, label: 'Über das System', icon: Info },
  ];

  return (
    <header className="sticky top-0 z-40 w-full border-b border-slate-200 bg-white/95 backdrop-blur-xs">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8 h-16">
        {/* Left: Branding & Quarter Select */}
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-indigo-600 text-white font-bold text-lg shadow-xs">
              TP
            </div>
            <div>
              <span className="text-sm font-bold tracking-tight text-slate-900 block leading-tight">
                Tierklinik Posthausen
              </span>
              <span className="text-[11px] font-medium text-slate-500 uppercase tracking-wider block">
                Dienstplan Navigator
              </span>
            </div>
          </div>

          {/* Quarter Pill Selector */}
          <div className="hidden sm:flex items-center gap-1.5 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs">
            <span className="text-slate-500 font-medium">Quartal:</span>
            <div className="relative inline-flex items-center">
              <select
                value={currentQuarter}
                onChange={(e) => onQuarterChange(e.target.value)}
                className="appearance-none bg-transparent pr-5 font-semibold text-slate-900 focus:outline-none cursor-pointer"
              >
                <option value="2026-Q2">2026 - Q2 (Apr - Jun)</option>
                <option value="2026-Q1">2026 - Q1 (Jan - Mär)</option>
                <option value="2025-Q4">2025 - Q4 (Okt - Dez)</option>
              </select>
              <ChevronDown className="pointer-events-none absolute right-0 h-3.5 w-3.5 text-slate-400" />
            </div>
            <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-800">
              AKTIV
            </span>
          </div>
        </div>

        {/* Center/Right: Navigation Tabs */}
        <nav className="flex space-x-1 sm:space-x-2">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => onTabChange(tab.id)}
                className={cn(
                  'flex items-center gap-2 px-3 py-2 text-xs sm:text-sm font-medium rounded-lg transition-colors cursor-pointer',
                  isActive
                    ? 'bg-indigo-50 text-indigo-700 shadow-2xs font-semibold'
                    : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
                )}
              >
                <Icon className={cn('h-4 w-4', isActive ? 'text-indigo-600' : 'text-slate-400')} />
                <span className="hidden md:inline">{tab.label}</span>
              </button>
            );
          })}
        </nav>
      </div>
    </header>
  );
};
