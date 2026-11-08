import React, { useState, useEffect, useCallback } from 'react';
import {
  Scale,
  TrendingUp,
  Search,
  RefreshCw,
  X,
  ArrowRight,
  CheckCircle2,
  AlertTriangle,
  Check,
} from 'lucide-react';
import type {
  QuarterFairnessOverviewResponse,
  GroupFairnessSummary,
  StaffFairnessRecord,
} from '../types/api';
import { fetchFairnessOverview } from '../lib/api';
import { getStaffColorScheme } from '../lib/colors';
import { cn } from '../lib/utils';

interface FairnessViewProps {
  currentQuarter?: string;
  onQuarterChange?: (quarter: string) => void;
}

type ArrowSortMode = 'improvement' | 'initial_desc' | 'final_desc' | 'name';
type ArrowFilterMode = 'all' | 'with_cf' | 'outliers' | 'improved';
type ArrowSubMode = 'dumbbell' | 'funnel';

export const FairnessView: React.FC<FairnessViewProps> = ({
  currentQuarter = '2026-Q4',
  onQuarterChange,
}) => {
  const [quarter, setQuarter] = useState<string>(currentQuarter);
  const [prevPropQuarter, setPrevPropQuarter] = useState<string>(currentQuarter);
  const [data, setData] = useState<QuarterFairnessOverviewResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedRole, setSelectedRole] = useState<string>('TFA');
  const [arrowSubMode, setArrowSubMode] = useState<ArrowSubMode>('dumbbell');
  const [arrowSort, setArrowSort] = useState<ArrowSortMode>('improvement');
  const [arrowFilter, setArrowFilter] = useState<ArrowFilterMode>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [selectedStaffId, setSelectedStaffId] = useState<string | null>(null);
  const [hoveredStaffId, setHoveredStaffId] = useState<string | null>(null);

  // Sync if parent quarter changes
  if (currentQuarter && currentQuarter !== prevPropQuarter) {
    setPrevPropQuarter(currentQuarter);
    setQuarter(currentQuarter);
  }

  const loadFairnessData = useCallback(async (qk: string) => {
    setLoading(true);
    const res = await fetchFairnessOverview(qk);
    setData(res);
    setLoading(false);
  }, []);

  useEffect(() => {
    loadFairnessData(quarter);
  }, [quarter, loadFairnessData]);

  const handleQuarterSwitch = (newQ: string) => {
    setQuarter(newQ);
    if (onQuarterChange) {
      onQuarterChange(newQ);
    }
  };

  // Filter records by selected role
  const roleRecords = (data?.records || []).filter(
    (r) => r.beruf.toLowerCase() === selectedRole.toLowerCase()
  );

  const selectedStaff = roleRecords.find((r) => r.identifier === selectedStaffId) || null;
  const currentGroupSummary: GroupFairnessSummary | undefined = data?.groups[selectedRole];

  // Helper calculations for each record using business tolerance:
  // <= 1.0 = balanced, <= 2.0 = slight_deviation, > 2.0 = outlier/warning
  const getRecordMetrics = (r: StaffFairnessRecord) => {
    const init = r.cf_delta;
    const final = r.net_delta;
    const plan = r.plan_delta;
    const absInit = Math.abs(init);
    const absFinal = Math.abs(final);

    const isBalanced = absFinal <= 1.0;
    const isSlight = absFinal > 1.0 && absFinal <= 2.0;
    const isOutlier = absFinal > 2.0;

    // Distance to 0 decreased by at least 0.05 OR stayed cleanly within target zone
    const isImproved = absFinal < absInit - 0.05 || (absInit <= 1.0 && isBalanced);

    // Right direction: plan compensating initial sign
    const isRightDirection =
      isImproved ||
      (init > 0.05 && plan < 0) ||
      (init < -0.05 && plan > 0) ||
      (absInit <= 1.0 && isBalanced);

    const deltaImprovement = absInit - absFinal; // Positive: moved closer to 0

    return {
      init,
      final,
      plan,
      absInit,
      absFinal,
      isBalanced,
      isSlight,
      isOutlier,
      isImproved,
      isRightDirection,
      deltaImprovement,
    };
  };

  const enriched = roleRecords.map((r) => ({
    record: r,
    ...getRecordMetrics(r),
  }));

  // Overall statistics
  const totalCount = enriched.length;
  const improvedCount = enriched.filter((e) => e.isImproved).length;
  const rightDirCount = enriched.filter((e) => e.isRightDirection).length;
  const inTargetCount = enriched.filter((e) => e.isBalanced).length;
  const outlierCount = enriched.filter((e) => e.isOutlier).length;
  const withCfCount = enriched.filter((e) => Math.abs(e.init) > 0.05).length;

  const avgInit =
    totalCount > 0
      ? enriched.reduce((s, e) => s + e.absInit, 0) / totalCount
      : 0;
  const avgFinal =
    totalCount > 0
      ? enriched.reduce((s, e) => s + e.absFinal, 0) / totalCount
      : 0;
  const reductionPct =
    avgInit > 0 ? Math.round(((avgInit - avgFinal) / avgInit) * 100) : 0;

  // Filter records for dumbbell view
  const filteredList = enriched.filter((e) => {
    const matchesSearch =
      searchQuery.trim() === '' ||
      e.record.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      e.record.identifier.toLowerCase().includes(searchQuery.toLowerCase());

    if (!matchesSearch) return false;
    if (arrowFilter === 'with_cf') return Math.abs(e.init) > 0.05;
    if (arrowFilter === 'improved') return e.isImproved;
    if (arrowFilter === 'outliers') return e.isOutlier;
    return true;
  });

  // Sort records
  const sortedList = [...filteredList].sort((a, b) => {
    if (arrowSort === 'improvement') {
      return b.deltaImprovement - a.deltaImprovement;
    }
    if (arrowSort === 'initial_desc') {
      return b.absInit - a.absInit;
    }
    if (arrowSort === 'final_desc') {
      return b.absFinal - a.absFinal;
    }
    if (arrowSort === 'name') {
      return a.record.name.localeCompare(b.record.name);
    }
    return 0;
  });

  // Dynamic scale for coordinates
  const maxObserved = Math.max(
    3.0,
    ...enriched.map((e) => Math.max(e.absInit, e.absFinal))
  );
  // Round up to nice number, clamp max scale at 15
  const plotScale = Math.min(15, Math.max(4, Math.ceil(maxObserved * 1.05)));

  // Percentage mapping for dumbbell: 0 -> 50%, -plotScale -> 5%, +plotScale -> 95%
  const valToPct = (val: number): number => {
    const clamped = Math.max(-plotScale, Math.min(plotScale, val));
    return 50 + (clamped / plotScale) * 45;
  };

  const targetBandLeft = 50 - (1.0 / plotScale) * 45;
  const targetBandWidth = (2.0 / plotScale) * 45;

  return (
    <div className="space-y-5">
      {/* 1. Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-stone-200/80">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-stone-900 flex items-center gap-2">
              <Scale className="h-6 w-6 text-[#324b9b]" />
              Fairness- & Belastungs-Übersicht
            </h1>
            <span className="text-xs px-2.5 py-0.5 rounded-full font-semibold bg-blue-50 text-[#324b9b] border border-blue-200">
              {quarter}
            </span>
          </div>
          <p className="text-xs text-stone-500 mt-0.5">
            Ausgleichs-Pfeile zur Visualisierung des Vorquartals-Ausgleichs auf 40h-Vollzeitbasis.
          </p>
        </div>

        {/* Quarter Selector & Refresh */}
        <div className="flex items-center gap-2">
          <div className="inline-flex rounded-lg border border-stone-200 bg-stone-100/70 p-0.5 text-xs font-medium">
            {['2026-Q3', '2026-Q4', '2027-Q1'].map((q) => (
              <button
                key={q}
                onClick={() => handleQuarterSwitch(q)}
                className={cn(
                  'px-3 py-1.5 rounded-md transition-all cursor-pointer font-semibold',
                  quarter === q
                    ? 'bg-white text-stone-900 shadow-2xs'
                    : 'text-stone-600 hover:text-stone-900'
                )}
              >
                {q}
              </button>
            ))}
          </div>

          <button
            onClick={() => loadFairnessData(quarter)}
            title="Daten neu laden"
            className="p-1.5 rounded-lg border border-stone-200 hover:bg-stone-100 text-stone-600 hover:text-stone-900 cursor-pointer transition-colors"
          >
            <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
          </button>
        </div>
      </div>

      {/* 2. Role Tabs (Berufsgruppen) */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="inline-flex rounded-xl border border-stone-200 bg-stone-100/80 p-1 text-xs font-semibold gap-1">
          {[
            { id: 'TFA', label: 'TFA', roleType: 'tfa' },
            { id: 'Azubi', label: 'Azubis', roleType: 'azubi' },
            { id: 'Intern', label: 'Interns', roleType: 'intern' },
            { id: 'Vet', label: 'Tierärzte (Vet)', roleType: 'vet' },
          ].map((tab) => {
            const count = (data?.records || []).filter(
              (r) => r.beruf.toLowerCase() === tab.id.toLowerCase()
            ).length;
            const isSelected = selectedRole === tab.id;
            const colors = getStaffColorScheme(tab.roleType);

            return (
              <button
                key={tab.id}
                onClick={() => {
                  setSelectedRole(tab.id);
                  setSelectedStaffId(null);
                }}
                className={cn(
                  'flex items-center gap-2 px-3.5 py-1.5 rounded-lg transition-all cursor-pointer font-medium text-xs',
                  isSelected
                    ? 'bg-white text-stone-900 shadow-2xs font-bold'
                    : 'text-stone-600 hover:text-stone-900 hover:bg-stone-200/50'
                )}
              >
                <span className={cn('w-2 h-2 rounded-full', colors.dot)} />
                <span>{tab.label}</span>
                <span
                  className={cn(
                    'px-1.5 py-0.2 rounded-full text-[10px]',
                    isSelected ? 'bg-stone-100 text-stone-700' : 'bg-stone-200/60 text-stone-600'
                  )}
                >
                  {count}
                </span>
              </button>
            );
          })}
        </div>

        {/* Group KPI Summary */}
        {currentGroupSummary && (
          <div className="flex items-center gap-3 text-xs text-stone-600">
            <span className="bg-white border border-stone-200/80 rounded-lg px-2.5 py-1 font-medium shadow-2xs">
              Gruppen-Soll: <strong className="text-stone-900">{currentGroupSummary.group_mean_40h}</strong> Dienste/40h
            </span>
            <span className="bg-white border border-stone-200/80 rounded-lg px-2.5 py-1 font-medium shadow-2xs">
              Im Zielbereich (±1.0): <strong className="text-emerald-700">{currentGroupSummary.balanced_pct}%</strong>
            </span>
          </div>
        )}
      </div>

      {/* 3. Main Ausgleichs-Pfeile Visualization Section */}
      <div className="rounded-xl border border-stone-200/80 bg-white p-4 sm:p-5 shadow-2xs space-y-4">
        {loading ? (
          <div className="py-16 text-center text-stone-400 text-xs flex items-center justify-center gap-2">
            <RefreshCw className="h-4 w-4 animate-spin text-[#324b9b]" />
            Lade Fairnessdaten...
          </div>
        ) : roleRecords.length === 0 ? (
          <div className="py-12 text-center text-stone-400 text-xs">
            Keine Daten für die Rolle {selectedRole} in {quarter} verfügbar.
          </div>
        ) : (
          <div className="space-y-4">
            {/* A. 3 KPI Summary Cards */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {/* Card 1: Right direction / Improvement */}
              <div className="rounded-lg bg-stone-50 border border-stone-200/80 p-3 flex flex-col justify-between">
                <div className="flex items-center justify-between text-xs text-stone-500">
                  <span className="font-semibold text-stone-700 flex items-center gap-1.5">
                    <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                    Korrektur-Erfolg
                  </span>
                  <span className="font-mono text-emerald-700 font-bold bg-emerald-50 px-1.5 py-0.5 rounded text-[11px] border border-emerald-200">
                    {totalCount > 0 ? Math.round((rightDirCount / totalCount) * 100) : 0}%
                  </span>
                </div>
                <div className="mt-2">
                  <div className="text-xl font-extrabold text-stone-900">
                    {rightDirCount} <span className="text-xs font-normal text-stone-500">von {totalCount} Personen</span>
                  </div>
                  <p className="text-[11px] text-stone-500 mt-0.5">
                    in die richtige Richtung korrigiert oder im Soll gehalten
                  </p>
                </div>
                <div className="w-full h-1.5 bg-stone-200 rounded-full mt-2 overflow-hidden flex">
                  <div
                    className="bg-emerald-500 h-full"
                    style={{ width: `${(rightDirCount / (totalCount || 1)) * 100}%` }}
                  />
                  <div
                    className="bg-amber-400 h-full"
                    style={{
                      width: `${((totalCount - rightDirCount) / (totalCount || 1)) * 100}%`,
                    }}
                  />
                </div>
              </div>

              {/* Card 2: In Target Band (±1.0) */}
              <div className="rounded-lg bg-stone-50 border border-stone-200/80 p-3 flex flex-col justify-between">
                <div className="flex items-center justify-between text-xs text-stone-500">
                  <span className="font-semibold text-stone-700 flex items-center gap-1.5">
                    <TrendingUp className="h-4 w-4 text-[#324b9b]" />
                    Im Zielkorridor (±1.0)
                  </span>
                  <span className="font-mono text-[#324b9b] font-bold bg-blue-50 px-1.5 py-0.5 rounded text-[11px] border border-blue-200">
                    {totalCount > 0 ? Math.round((inTargetCount / totalCount) * 100) : 0}%
                  </span>
                </div>
                <div className="mt-2">
                  <div className="text-xl font-extrabold text-stone-900">
                    {inTargetCount} <span className="text-xs font-normal text-stone-500">von {totalCount} Personen</span>
                  </div>
                  <p className="text-[11px] text-stone-500 mt-0.5">
                    {outlierCount > 0 ? `${outlierCount} Ausreißer (> ±2.0)` : 'Keine kritischen Ausreißer (> ±2.0)'}
                  </p>
                </div>
                <div className="w-full h-1.5 bg-stone-200 rounded-full mt-2 overflow-hidden flex">
                  <div
                    className="bg-[#324b9b] h-full"
                    style={{ width: `${(inTargetCount / (totalCount || 1)) * 100}%` }}
                  />
                </div>
              </div>

              {/* Card 3: Imbalance Reduction */}
              <div className="rounded-lg bg-stone-50 border border-stone-200/80 p-3 flex flex-col justify-between">
                <div className="flex items-center justify-between text-xs text-stone-500">
                  <span className="font-semibold text-stone-700 flex items-center gap-1.5">
                    <Scale className="h-4 w-4 text-purple-600" />
                    Mittlere Unwucht
                  </span>
                  <span className="font-mono text-purple-700 font-bold bg-purple-50 px-1.5 py-0.5 rounded text-[11px] border border-purple-200">
                    {reductionPct > 0 ? `-${reductionPct}%` : `${reductionPct}%`}
                  </span>
                </div>
                <div className="mt-2">
                  <div className="text-xl font-extrabold text-stone-900 font-mono">
                    {avgInit.toFixed(2)} → {avgFinal.toFixed(2)}{' '}
                    <span className="text-xs font-normal text-stone-500">Dienste</span>
                  </div>
                  <p className="text-[11px] text-stone-500 mt-0.5">
                    Durchschnittlicher Abstand zur idealen Nulllinie
                  </p>
                </div>
                <div className="w-full h-1.5 bg-stone-200 rounded-full mt-2 overflow-hidden flex">
                  <div
                    className="bg-purple-600 h-full"
                    style={{ width: `${Math.min(100, Math.max(10, 100 - reductionPct))}%` }}
                  />
                </div>
              </div>
            </div>

            {/* B. Sub-Mode Toggle & Controls */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-1 border-t border-stone-100">
              {/* View Switcher: Dumbbell vs Rotated Funnel */}
              <div className="inline-flex rounded-lg border border-stone-200 bg-stone-100/70 p-0.5 text-xs font-medium">
                <button
                  onClick={() => setArrowSubMode('dumbbell')}
                  className={cn(
                    'px-3 py-1 rounded-md transition-all cursor-pointer font-medium',
                    arrowSubMode === 'dumbbell'
                      ? 'bg-white text-stone-900 font-bold shadow-2xs'
                      : 'text-stone-600 hover:text-stone-900'
                  )}
                >
                  Einzel-Vektoren (pro Mitarbeiter)
                </button>
                <button
                  onClick={() => setArrowSubMode('funnel')}
                  className={cn(
                    'px-3 py-1 rounded-md transition-all cursor-pointer font-medium',
                    arrowSubMode === 'funnel'
                      ? 'bg-white text-stone-900 font-bold shadow-2xs'
                      : 'text-stone-600 hover:text-stone-900'
                  )}
                >
                  Konvergenz-Trichter (Vertikal)
                </button>
              </div>

              {/* Filter, Search & Sort Controls */}
              {arrowSubMode === 'dumbbell' && (
                <div className="flex flex-wrap items-center gap-2">
                  {/* Search Input */}
                  <div className="relative">
                    <Search className="absolute left-2 top-2 h-3 w-3 text-stone-400" />
                    <input
                      type="text"
                      placeholder="Mitarbeiter..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="pl-6 pr-2 py-0.5 bg-stone-50 border border-stone-200 rounded-lg text-xs text-stone-800 placeholder-stone-400 focus:outline-none focus:ring-1 focus:ring-[#324b9b] w-28 sm:w-36"
                    />
                  </div>

                  {/* Filter Chips */}
                  <div className="inline-flex rounded-lg border border-stone-200 bg-stone-100/70 p-0.5 text-xs font-medium">
                    {[
                      { id: 'all', label: `Alle (${totalCount})` },
                      { id: 'with_cf', label: `Vorbelastet (${withCfCount})` },
                      { id: 'improved', label: `Verbessert (${improvedCount})` },
                      { id: 'outliers', label: `Ausreißer (${outlierCount})` },
                    ].map((f) => (
                      <button
                        key={f.id}
                        onClick={() => setArrowFilter(f.id as ArrowFilterMode)}
                        className={cn(
                          'px-2 py-0.5 rounded transition-all cursor-pointer text-[11px]',
                          arrowFilter === f.id
                            ? 'bg-white text-stone-900 font-bold shadow-2xs'
                            : 'text-stone-600 hover:text-stone-900'
                        )}
                      >
                        {f.label}
                      </button>
                    ))}
                  </div>

                  {/* Sort Selector */}
                  <select
                    value={arrowSort}
                    onChange={(e) => setArrowSort(e.target.value as ArrowSortMode)}
                    className="text-xs bg-white border border-stone-200 rounded-lg px-2 py-1 text-stone-700 font-medium cursor-pointer focus:outline-none focus:ring-1 focus:ring-[#324b9b]"
                  >
                    <option value="improvement">Größte Verbesserung</option>
                    <option value="initial_desc">Höchste Vorbelastung</option>
                    <option value="final_desc">Größter Rest-Saldo</option>
                    <option value="name">Name (A-Z)</option>
                  </select>
                </div>
              )}
            </div>

            {/* C. Legende & Achsen-Header */}
            <div className="flex flex-wrap items-center justify-between text-[11px] text-stone-500 px-2.5 py-1.5 bg-stone-50/80 rounded-lg border border-stone-200/50 gap-2">
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded-full border-2 border-stone-400 bg-stone-200" />
                  <span>Ausgegraut = <strong>Vorher</strong> (Vorquartal)</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded-full bg-emerald-500 shadow-2xs" />
                  <span>Farbig = Neuer Saldo <strong>Nachher</strong> (Plan)</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <ArrowRight className="h-3 w-3 text-emerald-600" />
                  <span>Ausgleichsbewegung zur Mitte</span>
                </div>
              </div>
              <span className="font-semibold text-emerald-800 bg-emerald-100/70 px-2 py-0.5 rounded text-[10px]">
                Grüner Korridor = Zielzone (±1.0 Dienste)
              </span>
            </div>

            {/* D. SUB-MODE 1: DUMBBELL LIST (Per Person Vectors) */}
            {arrowSubMode === 'dumbbell' && (
              <div className="space-y-1.5 max-h-[500px] overflow-y-auto pr-1">
                {sortedList.length === 0 ? (
                  <div className="py-12 text-center text-stone-400 text-xs">
                    Keine Personen entsprechen dem ausgewählten Filter.
                  </div>
                ) : (
                  sortedList.map(({ record: r, init, final, absInit, absFinal, isBalanced, isSlight, isImproved, deltaImprovement }) => {
                    const isSelected = selectedStaffId === r.identifier;
                    const isHovered = hoveredStaffId === r.identifier;

                    const x1Pct = valToPct(init);
                    const x2Pct = valToPct(final);

                    // Color for the arrow / line
                    const arrowColor = isImproved
                      ? '#10b981' // Emerald
                      : absFinal > absInit + 0.1
                      ? '#f43f5e' // Rose
                      : '#78716c'; // Neutral Stone

                    // Endpoint dot color based on +-1.0 (balanced), +-2.0 (slight), >2.0 (outlier)
                    const dotClass = isBalanced
                      ? 'bg-emerald-500 ring-2 ring-emerald-200'
                      : isSlight
                      ? 'bg-amber-500 ring-2 ring-amber-200'
                      : 'bg-rose-500 ring-2 ring-rose-200';

                    const x1Coord = (x1Pct / 100) * 1000;
                    const x2Coord = (x2Pct / 100) * 1000;
                    const dx = x2Coord - x1Coord;
                    const hasArrow = Math.abs(dx) > 18;
                    const lineStart = x1Coord + (dx > 0 ? 8 : -8);
                    const lineEnd = x2Coord - (dx > 0 ? 12 : -12);

                    return (
                      <div
                        key={r.identifier}
                        onClick={() => setSelectedStaffId(isSelected ? null : r.identifier)}
                        onMouseEnter={() => setHoveredStaffId(r.identifier)}
                        onMouseLeave={() => setHoveredStaffId(null)}
                        className={cn(
                          'group flex items-center gap-3 p-2 rounded-lg cursor-pointer transition-all border text-xs',
                          isSelected
                            ? 'bg-blue-50/90 border-[#324b9b] shadow-2xs'
                            : isHovered
                            ? 'bg-stone-50 border-stone-300'
                            : 'bg-white border-stone-200/70 hover:border-stone-300'
                        )}
                      >
                        {/* Staff Info */}
                        <div className="w-36 shrink-0">
                          <div className="flex items-center gap-1.5">
                            <span className="font-bold text-stone-900 truncate">{r.name}</span>
                            <span className="text-[10px] text-stone-500 font-mono">({r.identifier})</span>
                          </div>
                          <div className="text-[10px] text-stone-400 mt-0.5">
                            {r.hours}h Vertrag {r.vacation_days > 0 ? `· ${r.vacation_days} Tg. Ur.` : ''}
                          </div>
                        </div>

                        {/* Vector Track */}
                        <div className="flex-1 relative h-8 bg-stone-100/80 rounded-md border border-stone-200/60 overflow-hidden flex items-center">
                          {/* Neutral Zero Line */}
                          <div className="absolute left-1/2 top-0 bottom-0 w-0.5 bg-stone-300 z-10" />

                          {/* Target Band ±1.0 */}
                          <div
                            className="absolute top-0 bottom-0 bg-emerald-100/50 border-x border-emerald-300/40 z-0"
                            style={{
                              left: `${targetBandLeft}%`,
                              width: `${targetBandWidth}%`,
                            }}
                          />

                          {/* SVG Arrow Vector */}
                          <svg
                            className="absolute inset-0 w-full h-full pointer-events-none z-15 overflow-visible"
                            viewBox="0 0 1000 32"
                            preserveAspectRatio="none"
                          >
                            <defs>
                              <marker
                                id={`arr-head-${r.identifier}`}
                                viewBox="0 0 10 10"
                                refX="8"
                                refY="5"
                                markerWidth="6"
                                markerHeight="6"
                                orient="auto"
                              >
                                <path d="M 0 1 L 9 5 L 0 9 z" fill={arrowColor} />
                              </marker>
                            </defs>

                            {/* Draw line and arrowhead if moved */}
                            {hasArrow && (
                              <line
                                x1={lineStart}
                                y1="16"
                                x2={lineEnd}
                                y2="16"
                                stroke={arrowColor}
                                strokeWidth={isSelected || isHovered ? '2.8' : '2'}
                                strokeDasharray={isImproved ? undefined : '4 3'}
                                markerEnd={`url(#arr-head-${r.identifier})`}
                              />
                            )}
                          </svg>

                          {/* Vorher Point (Ausgegrauter Startpunkt) */}
                          <div
                            className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-3.5 h-3.5 rounded-full border-2 border-stone-400 bg-stone-200 shadow-2xs z-20 transition-transform group-hover:scale-110"
                            style={{ left: `${x1Pct}%` }}
                            title={`Vorher (Vorquartal): ${init > 0 ? `+${init.toFixed(2)}` : init.toFixed(2)}`}
                          />

                          {/* Nachher Point (Aktiver Zielpunkt) */}
                          <div
                            className={cn(
                              'absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-5 h-5 rounded-full z-25 flex items-center justify-center font-mono font-bold text-[8px] text-white shadow-xs transition-transform group-hover:scale-125',
                              dotClass
                            )}
                            style={{ left: `${x2Pct}%` }}
                            title={`Nachher (Gesamtsaldo): ${final > 0 ? `+${final.toFixed(2)}` : final.toFixed(2)}`}
                          >
                            {Math.abs(final) <= 1.0 ? '✓' : final > 0 ? `+${final.toFixed(1)}` : final.toFixed(1)}
                          </div>
                        </div>

                        {/* Value Transition & Badge */}
                        <div className="w-48 shrink-0 flex items-center justify-between text-right">
                          <div className="text-[11px] font-mono text-stone-600">
                            <span className="text-stone-400" title="Vorquartals-Saldo">
                              {init > 0 ? `+${init.toFixed(2)}` : init.toFixed(2)}
                            </span>
                            <span className="text-stone-300 mx-1">→</span>
                            <span
                              className={cn(
                                'font-bold',
                                isBalanced ? 'text-emerald-700' : isSlight ? 'text-amber-700' : 'text-rose-700'
                              )}
                              title="Neuer Netto-Saldo"
                            >
                              {final > 0 ? `+${final.toFixed(2)}` : final.toFixed(2)}
                            </span>
                          </div>

                          {/* Status / Improvement Pill */}
                          <div className="ml-2">
                            {isBalanced ? (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-800 border border-emerald-200 text-[10px] font-bold">
                                <Check className="h-3 w-3" />
                                Im Ziel
                              </span>
                            ) : isImproved ? (
                              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-blue-50 text-blue-800 border border-blue-200 text-[10px] font-bold">
                                <TrendingUp className="h-3 w-3" />
                                {deltaImprovement > 0 ? `Δ -${deltaImprovement.toFixed(1)}` : 'Kompensiert'}
                              </span>
                            ) : isSlight ? (
                              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-amber-50 text-amber-800 border border-amber-200 text-[10px] font-bold">
                                Leichte Abw.
                              </span>
                            ) : (
                              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-rose-50 text-rose-800 border border-rose-200 text-[10px] font-bold">
                                <AlertTriangle className="h-3 w-3" />
                                Ausreißer
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            )}

            {/* E. SUB-MODE 2: ROTATED KONVERGENZ-TRICHTER (90° Rotated: Top=Vorher, Bottom=Nachher, Vertical Corridor) */}
            {arrowSubMode === 'funnel' && (
              <div className="relative w-full h-[430px] bg-[#faf9f6] rounded-xl border border-stone-200 p-3 overflow-hidden flex items-center justify-center">
                <svg className="w-full h-full select-none" viewBox="0 0 960 420">
                  <defs>
                    <linearGradient id="verticalCorridorGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                      <stop offset="0%" stopColor="#10b981" stopOpacity="0.08" />
                      <stop offset="100%" stopColor="#10b981" stopOpacity="0.22" />
                    </linearGradient>
                  </defs>

                  {/* Funnel coordinate mapping:
                      X axis: horizontal across the screen. Center X = 480.
                      Scale: 400px half-width corresponds to plotScale.
                      Y axis: top Y = 85 (Vorher), bottom Y = 335 (Nachher).
                  */}
                  {(() => {
                    const centerX = 480;
                    const halfWidthPx = 400;
                    const valToFunnelX = (val: number): number => {
                      const clamped = Math.max(-plotScale, Math.min(plotScale, val));
                      return centerX + (clamped / plotScale) * halfWidthPx;
                    };

                    const xCorridorLeft = valToFunnelX(-1.0);
                    const xCorridorRight = valToFunnelX(1.0);
                    const corridorW = xCorridorRight - xCorridorLeft;

                    // Tick marks to render
                    const tickValues: number[] = [];
                    for (let t = -Math.floor(plotScale); t <= Math.floor(plotScale); t++) {
                      if (t !== 0 && Math.abs(t) <= plotScale) {
                        tickValues.push(t);
                      }
                    }

                    return (
                      <g>
                        {/* 1. Vertical Target Corridor Rectangle (±1.0 Dienste) */}
                        <rect
                          x={xCorridorLeft}
                          y={65}
                          width={corridorW}
                          height={285}
                          fill="url(#verticalCorridorGrad)"
                          stroke="#10b981"
                          strokeWidth="1"
                          strokeDasharray="4 3"
                          strokeOpacity="0.6"
                        />

                        {/* 2. Central Zero Baseline (x = 480) */}
                        <line
                          x1={centerX}
                          y1={65}
                          x2={centerX}
                          y2={355}
                          stroke="#10b981"
                          strokeWidth="1.5"
                          strokeDasharray="3 3"
                          strokeOpacity="0.7"
                        />
                        <text
                          x={centerX}
                          y={55}
                          fontSize="10"
                          fontWeight="bold"
                          fill="#059669"
                          textAnchor="middle"
                        >
                          Netto 0.0 (Fairness-Ziel)
                        </text>

                        {/* 3. Top Axis: VORHER (Vorquartals-Saldo) at Y = 85 */}
                        <line x1="70" y1="85" x2="890" y2="85" stroke="#a8a29e" strokeWidth="2" />
                        <text
                          x={centerX}
                          y={28}
                          fontSize="12"
                          fontWeight="bold"
                          fill="#44403c"
                          textAnchor="middle"
                        >
                          VORHER (Vorquartals-Saldo)
                        </text>
                        <text x="75" y="78" fontSize="10" fill="#78716c" textAnchor="start">
                          ← Entlastung (-)
                        </text>
                        <text x="885" y="78" fontSize="10" fill="#78716c" textAnchor="end">
                          Mehrarbeit (+) →
                        </text>

                        {/* Top Axis Ticks */}
                        {tickValues.map((t) => {
                          const tx = valToFunnelX(t);
                          return (
                            <g key={`top-tick-${t}`}>
                              <line x1={tx} y1="80" x2={tx} y2="85" stroke="#a8a29e" strokeWidth="1" />
                              <text
                                x={tx}
                                y={76}
                                fontSize="9"
                                fill="#78716c"
                                textAnchor="middle"
                                fontWeight="bold"
                              >
                                {t > 0 ? `+${t}` : t}
                              </text>
                            </g>
                          );
                        })}

                        {/* 4. Bottom Axis: NACHHER (Neuer Netto-Saldo) at Y = 335 */}
                        <line x1="70" y1="335" x2="890" y2="335" stroke="#324b9b" strokeWidth="2" />
                        <text
                          x={centerX}
                          y={390}
                          fontSize="12"
                          fontWeight="bold"
                          fill="#324b9b"
                          textAnchor="middle"
                        >
                          NACHHER (Neuer Netto-Saldo nach Plan)
                        </text>
                        <text x="75" y="352" fontSize="10" fill="#78716c" textAnchor="start">
                          ← Rest-Minus (-)
                        </text>
                        <text x="885" y="352" fontSize="10" fill="#78716c" textAnchor="end">
                          Rest-Plus (+) →
                        </text>

                        {/* Bottom Axis Ticks */}
                        {tickValues.map((t) => {
                          const tx = valToFunnelX(t);
                          return (
                            <g key={`bot-tick-${t}`}>
                              <line x1={tx} y1="335" x2={tx} y2="340" stroke="#324b9b" strokeWidth="1" />
                              <text
                                x={tx}
                                y={352}
                                fontSize="9"
                                fill="#324b9b"
                                textAnchor="middle"
                                fontWeight="bold"
                              >
                                {t > 0 ? `+${t}` : t}
                              </text>
                            </g>
                          );
                        })}

                        {/* 5. Smooth Flow Curves (Top -> Bottom) for all staff */}
                        {enriched.map(({ record: r, init, final, isImproved, isBalanced, isSlight }) => {
                          const x1 = valToFunnelX(init);
                          const x2 = valToFunnelX(final);
                          const y1 = 85;
                          const y2 = 335;

                          const isSelected = selectedStaffId === r.identifier;
                          const isHovered = hoveredStaffId === r.identifier;

                          // Color by final outcome status
                          const strokeColor = isBalanced
                            ? '#10b981' // Emerald
                            : isSlight
                            ? '#f59e0b' // Amber
                            : '#f43f5e'; // Rose

                          const strokeW = isSelected ? 3.8 : isHovered ? 3.2 : 1.8;
                          const strokeOp = hoveredStaffId
                            ? isHovered || isSelected
                              ? 1.0
                              : 0.12
                            : isSelected
                            ? 1.0
                            : isBalanced
                            ? 0.75
                            : 0.6;

                          // Cubic bezier vertical S-curve
                          const dy = y2 - y1;
                          const pathD = `M ${x1} ${y1} C ${x1} ${y1 + dy * 0.45}, ${x2} ${y2 - dy * 0.45}, ${x2} ${y2}`;

                          return (
                            <g
                              key={r.identifier}
                              onClick={() => setSelectedStaffId(isSelected ? null : r.identifier)}
                              onMouseEnter={() => setHoveredStaffId(r.identifier)}
                              onMouseLeave={() => setHoveredStaffId(null)}
                              className="cursor-pointer"
                            >
                              <title>
                                {`${r.name} (${r.identifier})\nVorher: ${init > 0 ? `+${init.toFixed(2)}` : init.toFixed(2)}\nPlan: ${r.plan_delta > 0 ? `+${r.plan_delta.toFixed(2)}` : r.plan_delta.toFixed(2)}\nNachher: ${final > 0 ? `+${final.toFixed(2)}` : final.toFixed(2)}`}
                              </title>

                              {/* Flow Bezier Path */}
                              <path
                                d={pathD}
                                fill="none"
                                stroke={strokeColor}
                                strokeWidth={strokeW}
                                strokeOpacity={strokeOp}
                                strokeDasharray={!isImproved && !isBalanced ? '5 3' : undefined}
                                className="transition-all"
                              />

                              {/* Vorher Circle (Top Axis) */}
                              <circle
                                cx={x1}
                                cy={y1}
                                r={isSelected ? 5.5 : isHovered ? 5 : 3.5}
                                fill="#ffffff"
                                stroke="#78716c"
                                strokeWidth="2"
                                opacity={strokeOp}
                              />

                              {/* Nachher Circle (Bottom Axis) */}
                              <circle
                                cx={x2}
                                cy={y2}
                                r={isSelected ? 6.5 : isHovered ? 6 : 4.5}
                                fill={strokeColor}
                                stroke="#ffffff"
                                strokeWidth="1.5"
                                opacity={strokeOp}
                              />

                              {/* Label on Hover / Selected */}
                              {(isSelected || isHovered) && (
                                <g>
                                  <rect
                                    x={x2 - 45}
                                    y={y2 - 28}
                                    width="90"
                                    height="20"
                                    rx="4"
                                    fill="#1e293b"
                                    opacity="0.9"
                                  />
                                  <text
                                    x={x2}
                                    y={y2 - 14}
                                    fontSize="10"
                                    fontWeight="bold"
                                    fill="#ffffff"
                                    textAnchor="middle"
                                  >
                                    {r.identifier}: {final > 0 ? `+${final.toFixed(2)}` : final.toFixed(2)}
                                  </text>
                                </g>
                              )}
                            </g>
                          );
                        })}
                      </g>
                    );
                  })()}
                </svg>

                {/* Floating Inspector in Funnel */}
                {hoveredStaffId && (() => {
                  const h = enriched.find((x) => x.record.identifier === hoveredStaffId);
                  if (!h) return null;
                  return (
                    <div className="absolute bottom-3 left-4 bg-white/95 backdrop-blur-xs border border-stone-300 rounded-lg shadow-sm px-3 py-1.5 text-[11px] pointer-events-none flex items-center gap-2">
                      <span className="font-bold text-stone-900">{h.record.name} ({h.record.identifier}):</span>
                      <span className="text-stone-500">Vorher: {h.init > 0 ? `+${h.init.toFixed(2)}` : h.init.toFixed(2)}</span>
                      <span className="text-stone-300">→</span>
                      <span className="text-blue-700 font-semibold">Plan: {h.plan > 0 ? `+${h.plan.toFixed(2)}` : h.plan.toFixed(2)}</span>
                      <span className="text-stone-300">→</span>
                      <span className={cn('font-bold font-mono px-1.5 py-0.2 rounded', h.isBalanced ? 'bg-emerald-100 text-emerald-900' : h.isSlight ? 'bg-amber-100 text-amber-900' : 'bg-rose-100 text-rose-900')}>
                        Nachher: {h.final > 0 ? `+${h.final.toFixed(2)}` : h.final.toFixed(2)}
                      </span>
                    </div>
                  );
                })()}
              </div>
            )}
          </div>
        )}
      </div>

      {/* 4. Detail Inspector Drawer (Shows when clicking an employee in either view) */}
      {selectedStaff && (
        <div className="rounded-xl border border-blue-200 bg-blue-50/40 p-4 sm:p-5 shadow-2xs relative transition-all">
          <button
            onClick={() => setSelectedStaffId(null)}
            className="absolute top-4 right-4 text-stone-400 hover:text-stone-700 p-1 rounded-md hover:bg-stone-200/50 cursor-pointer"
            title="Schließen"
          >
            <X className="h-4 w-4" />
          </button>

          <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
            <div>
              <div className="flex items-center gap-2">
                <span className="text-base font-bold text-stone-900">{selectedStaff.name}</span>
                <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-white border border-stone-200 text-stone-700">
                  {selectedStaff.identifier}
                </span>
                <span className="text-xs px-2.5 py-0.5 rounded-full font-medium bg-stone-100 text-stone-700">
                  {selectedStaff.beruf} · {selectedStaff.hours}h Vertrag
                </span>
              </div>
              <p className="text-xs text-stone-600 mt-1 max-w-2xl leading-relaxed">
                {selectedStaff.explanation}
              </p>
            </div>

            {/* Net Status Badge */}
            <div className="shrink-0 flex items-center gap-2">
              <span className="text-xs font-semibold text-stone-500">Netto-Gesamtsaldo:</span>
              <span
                className={cn(
                  'text-sm font-bold font-mono px-3 py-1 rounded-lg border',
                  selectedStaff.status === 'balanced'
                    ? 'bg-emerald-100 text-emerald-900 border-emerald-300'
                    : selectedStaff.status === 'slight_deviation'
                    ? 'bg-amber-100 text-amber-900 border-amber-300'
                    : 'bg-rose-100 text-rose-900 border-rose-300'
                )}
              >
                {selectedStaff.net_delta > 0
                  ? `+${selectedStaff.net_delta.toFixed(2)}`
                  : selectedStaff.net_delta.toFixed(2)}{' '}
                Dienste
              </span>
            </div>
          </div>

          {/* Breakdown Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4 pt-3 border-t border-blue-200/60 text-xs">
            <div className="bg-white p-2.5 rounded-lg border border-stone-200/80">
              <span className="text-[11px] text-stone-500 block">Vertrag & Anwesenheit</span>
              <strong className="text-stone-900 text-sm">
                {selectedStaff.hours} h · {Math.round(selectedStaff.presence_factor * 100)}%
              </strong>
              <span className="text-[10px] text-stone-400 block mt-0.5">
                {selectedStaff.vacation_days} Tage Urlaub/Abwesend
              </span>
            </div>

            <div className="bg-white p-2.5 rounded-lg border border-stone-200/80">
              <span className="text-[11px] text-stone-500 block">Tatsächliche Dienste</span>
              <strong className="text-stone-900 text-sm">
                {selectedStaff.effective_nights} Nächte · {selectedStaff.weekend_shifts} WE
              </strong>
              <span className="text-[10px] text-stone-400 block mt-0.5">
                Gesamt: {selectedStaff.total_notdienst} Schichten
              </span>
            </div>

            <div className="bg-white p-2.5 rounded-lg border border-stone-200/80">
              <span className="text-[11px] text-stone-500 block">① Plan vs. Soll (dieses Q.)</span>
              <strong className="text-blue-900 text-sm font-mono">
                {selectedStaff.plan_delta > 0
                  ? `+${selectedStaff.plan_delta.toFixed(2)}`
                  : selectedStaff.plan_delta.toFixed(2)}
              </strong>
              <span className="text-[10px] text-stone-400 block mt-0.5">
                Norm: {selectedStaff.normalized_40h} vs. Ø {selectedStaff.group_mean_40h}
              </span>
            </div>

            <div className="bg-white p-2.5 rounded-lg border border-stone-200/80">
              <span className="text-[11px] text-stone-500 block">② Vorquartals-Saldo</span>
              <strong className="text-stone-900 text-sm font-mono">
                {selectedStaff.cf_delta > 0
                  ? `+${selectedStaff.cf_delta.toFixed(2)}`
                  : selectedStaff.cf_delta.toFixed(2)}
              </strong>
              <span className="text-[10px] text-stone-400 block mt-0.5">
                Ausgleichs-Puffer aus Q3
              </span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
