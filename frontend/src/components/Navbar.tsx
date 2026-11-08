import React from 'react';
import { Users, CalendarDays, Calendar, Scale, HelpCircle, ChevronDown, Pin, LogOut } from 'lucide-react';
import { cn } from '../lib/utils';

export type NavTab = 'staff' | 'absences' | 'preassignments' | 'matrix' | 'fairness' | 'about';

interface NavbarProps {
  activeTab: NavTab;
  onTabChange: (tab: NavTab) => void;
  currentQuarter: string;
  onQuarterChange: (q: string) => void;
  onLogout?: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  onTabChange,
  currentQuarter,
  onQuarterChange,
  onLogout,
}) => {
  const tabs = [
    { id: 'staff' as NavTab, label: 'Mitarbeiter', icon: Users },
    { id: 'absences' as NavTab, label: 'Abwesenheiten', icon: CalendarDays },
    { id: 'preassignments' as NavTab, label: 'Vorbelegungen', icon: Pin },
    { id: 'matrix' as NavTab, label: 'Dienstplan', icon: Calendar },
    { id: 'fairness' as NavTab, label: 'Fairness', icon: Scale },
    { id: 'about' as NavTab, label: 'Hilfe', icon: HelpCircle },
  ];

  return (
    <header className="sticky top-0 z-40 w-full border-b border-stone-200/90 bg-white/95 backdrop-blur-md shadow-2xs">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8 h-14">
        {/* Left: Official Clinic Logo + Quarter Selector on one single line */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <img
              src="/logo-trillig.png"
              alt="Tierklinik Dr. Trillig"
              className="h-8 sm:h-9 w-auto object-contain"
            />
          </div>

          <div className="h-5 w-[1px] bg-stone-200 hidden sm:block" />

          {/* Quarter Selector */}
          <div className="flex items-center gap-1.5 rounded-lg border border-stone-200 bg-stone-50/80 px-2.5 py-1 text-xs shadow-2xs">
            <span className="text-stone-500 font-medium hidden md:inline">Planungsquartal:</span>
            <div className="relative inline-flex items-center">
              <select
                value={currentQuarter}
                onChange={(e) => onQuarterChange(e.target.value)}
                className="appearance-none bg-transparent pr-4 font-semibold text-stone-800 focus:outline-none cursor-pointer text-xs"
              >
                <option value="2027-Q1">Q1 / 2027 (Planung)</option>
                <option value="2026-Q4">Q4 / 2026</option>
                <option value="2026-Q3">Q3 / 2026</option>
                <option value="2026-Q2">Q2 / 2026</option>
                <option value="2026-Q1">Q1 / 2026</option>
              </select>
              <ChevronDown className="pointer-events-none absolute right-0 h-3 w-3 text-stone-400" />
            </div>
          </div>
        </div>

        {/* Right: Single-Line Nav Tabs */}
        <nav className="flex space-x-1 sm:space-x-1.5">
          {tabs.map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => onTabChange(tab.id)}
                className={cn(
                  'flex items-center gap-1.5 px-3 py-1.5 text-xs sm:text-sm font-medium rounded-lg transition-all cursor-pointer whitespace-nowrap',
                  isActive
                    ? 'bg-[#324b9b] text-white shadow-xs font-semibold'
                    : 'text-stone-600 hover:text-stone-900 hover:bg-stone-100/80'
                )}
              >
                <Icon className={cn('h-3.5 w-3.5 sm:h-4 sm:w-4', isActive ? 'text-white' : 'text-stone-400')} />
                <span>{tab.label}</span>
              </button>
            );
          })}

          {onLogout && (
            <button
              onClick={onLogout}
              title="Abmelden"
              className="flex items-center gap-1 px-2.5 py-1.5 text-xs text-stone-400 hover:text-stone-700 hover:bg-stone-100/80 rounded-lg transition-all cursor-pointer border-l border-stone-200/80 pl-3 ml-1"
            >
              <LogOut className="h-3.5 w-3.5" />
              <span className="hidden xl:inline">Abmelden</span>
            </button>
          )}
        </nav>
      </div>
    </header>
  );
};
