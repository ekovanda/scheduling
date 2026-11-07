import React, { useState, useEffect } from 'react';
import {
  Scale,
  TrendingUp,
  BarChart3,
  ScatterChart,
  SlidersHorizontal,
  Info,
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

type VisualizationMode = 'bars' | 'arrows' | 'scatter' | 'strip';
type ArrowSortMode = 'improvement' | 'initial_desc' | 'final_desc' | 'name';
type ArrowFilterMode = 'all' | 'with_cf' | 'outliers' | 'improved';
type ArrowSubMode = 'dumbbell' | 'funnel';
type FilterStatus = 'ALL' | 'balanced' | 'slight_deviation' | 'warning';

export const FairnessView: React.FC<FairnessViewProps> = ({
  currentQuarter = '2026-Q4',
  onQuarterChange,
}) => {
  const [quarter, setQuarter] = useState<string>(currentQuarter);
  const [data, setData] = useState<QuarterFairnessOverviewResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedRole, setSelectedRole] = useState<string>('TFA');
  const [vizMode, setVizMode] = useState<VisualizationMode>('bars');
  const [arrowSubMode, setArrowSubMode] = useState<ArrowSubMode>('dumbbell');
  const [arrowSort, setArrowSort] = useState<ArrowSortMode>('improvement');
  const [arrowFilter, setArrowFilter] = useState<ArrowFilterMode>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<FilterStatus>('ALL');
  const [selectedStaffId, setSelectedStaffId] = useState<string | null>(null);
  const [hoveredStaffId, setHoveredStaffId] = useState<string | null>(null);

  // Sync if parent quarter changes
  useEffect(() => {
    if (currentQuarter && currentQuarter !== quarter) {
      setQuarter(currentQuarter);
    }
  }, [currentQuarter]);

  useEffect(() => {
    loadFairnessData(quarter);
  }, [quarter]);

  const loadFairnessData = async (qk: string) => {
    setLoading(true);
    const res = await fetchFairnessOverview(qk);
    setData(res);
    setLoading(false);
  };

  const handleQuarterSwitch = (newQ: string) => {
    setQuarter(newQ);
    if (onQuarterChange) {
      onQuarterChange(newQ);
    }
  };

  // Filter records by selected role and search query
  const roleRecords = (data?.records || []).filter(
    (r) => r.beruf.toLowerCase() === selectedRole.toLowerCase()
  );

  const filteredRecords = roleRecords.filter((r) => {
    const matchesSearch =
      r.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      r.identifier.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus =
      statusFilter === 'ALL' || r.status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const selectedStaff = roleRecords.find((r) => r.identifier === selectedStaffId) || null;
  const currentGroupSummary: GroupFairnessSummary | undefined = data?.groups[selectedRole];

  return (
    <div className="space-y-6">
      {/* 1. Header & Controls */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-stone-200/80">
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
          <p className="text-sm text-stone-500 mt-1">
            Transparenter Abgleich der Dienstbelastung auf 40h-Basis mit automatischem Vorquartals-Ausgleichskonto.
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

      {/* 2. Explanatory Banner: The 3 Core Numbers in Plain Language */}
      <div className="rounded-xl border border-stone-200/90 bg-white p-4 shadow-2xs">
        <div className="flex items-center gap-2 mb-3">
          <Info className="h-4 w-4 text-[#324b9b]" />
          <h2 className="text-xs font-bold uppercase tracking-wider text-stone-800">
            Das Fairness-Modell: Wie die Zahlen zu lesen sind
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
          {/* Card 1: Plan vs Soll */}
          <div className="rounded-lg bg-stone-50 border border-stone-200/70 p-3 space-y-1">
            <div className="flex items-center justify-between font-bold text-stone-900">
              <span className="text-[#324b9b]">① Plan vs. Soll (dieses Q.)</span>
              <span className="text-[11px] font-mono px-1.5 py-0.5 rounded bg-blue-100 text-blue-800">+0.45</span>
            </div>
            <p className="text-stone-600 leading-relaxed text-[11px]">
              Weicht die Zuteilung im aktuellen Quartal vom fairen Soll ab? Normiert auf 40h-Vollzeit und Urlaubstage.
            </p>
          </div>

          {/* Card 2: Carry-Forward */}
          <div className="rounded-lg bg-stone-50 border border-stone-200/70 p-3 space-y-1">
            <div className="flex items-center justify-between font-bold text-stone-900">
              <span className="text-stone-800">② Vorquartals-Saldo</span>
              <span className="text-[11px] font-mono px-1.5 py-0.5 rounded bg-stone-200 text-stone-800">-0.60</span>
            </div>
            <p className="text-stone-600 leading-relaxed text-[11px]">
              Guthaben oder Rückstand aus dem vorherigen Quartal. Wer zuletzt weniger Dienste hatte, gleicht dies jetzt aus.
            </p>
          </div>

          {/* Card 3: Net Balance */}
          <div className="rounded-lg bg-emerald-50/70 border border-emerald-200 p-3 space-y-1">
            <div className="flex items-center justify-between font-bold text-emerald-900">
              <span>③ Netto-Gesamtsaldo</span>
              <span className="text-[11px] font-mono px-1.5 py-0.5 rounded bg-emerald-200 text-emerald-950 font-bold">-0.15</span>
            </div>
            <p className="text-emerald-800 leading-relaxed text-[11px]">
              Die Summe aus ① + ②: Liegt der Wert nahe 0.0 (grün), ist die Belastung über beide Quartale hinweg perfekt ausgeglichen!
            </p>
          </div>
        </div>
      </div>

      {/* 3. Role Tabs (Berufsgruppen) */}
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
              Im Zielbereich: <strong className="text-emerald-700">{currentGroupSummary.balanced_pct}%</strong>
            </span>
          </div>
        )}
      </div>

      {/* 4. Interactive Visualisation Section with 3 Options */}
      <div className="rounded-xl border border-stone-200/80 bg-white p-5 shadow-2xs space-y-4">
        {/* Viz Header with Toggle */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-stone-100 pb-3">
          <div>
            <h3 className="text-sm font-bold text-stone-900 flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-[#324b9b]" />
              Gesamtverteilung: {selectedRole}
            </h3>
            <p className="text-xs text-stone-500 mt-0.5">
              Wähle eine Darstellungsform, um die Verteilung und einzelne Personen zu untersuchen:
            </p>
          </div>

          {/* 4 Visualization Mode Options */}
          <div className="inline-flex rounded-lg border border-stone-200 bg-stone-100/80 p-0.5 text-xs font-medium">
            <button
              onClick={() => setVizMode('bars')}
              className={cn(
                'flex items-center gap-1.5 px-2.5 py-1 rounded-md transition-all cursor-pointer',
                vizMode === 'bars'
                  ? 'bg-white text-stone-900 font-bold shadow-2xs'
                  : 'text-stone-600 hover:text-stone-900'
              )}
            >
              <BarChart3 className="h-3.5 w-3.5 text-[#324b9b]" />
              <span>1. Balance-Balken</span>
            </button>
            <button
              onClick={() => setVizMode('arrows')}
              className={cn(
                'flex items-center gap-1.5 px-2.5 py-1 rounded-md transition-all cursor-pointer',
                vizMode === 'arrows'
                  ? 'bg-white text-stone-900 font-bold shadow-2xs'
                  : 'text-stone-600 hover:text-stone-900'
              )}
            >
              <ArrowRight className="h-3.5 w-3.5 text-blue-600" />
              <span>2. Ausgleichs-Pfeile</span>
            </button>
            <button
              onClick={() => setVizMode('scatter')}
              className={cn(
                'flex items-center gap-1.5 px-2.5 py-1 rounded-md transition-all cursor-pointer',
                vizMode === 'scatter'
                  ? 'bg-white text-stone-900 font-bold shadow-2xs'
                  : 'text-stone-600 hover:text-stone-900'
              )}
            >
              <ScatterChart className="h-3.5 w-3.5 text-emerald-600" />
              <span>3. 2D-Scatterplot</span>
            </button>
            <button
              onClick={() => setVizMode('strip')}
              className={cn(
                'flex items-center gap-1.5 px-2.5 py-1 rounded-md transition-all cursor-pointer',
                vizMode === 'strip'
                  ? 'bg-white text-stone-900 font-bold shadow-2xs'
                  : 'text-stone-600 hover:text-stone-900'
              )}
            >
              <SlidersHorizontal className="h-3.5 w-3.5 text-amber-600" />
              <span>4. Dichte-Streifen</span>
            </button>
          </div>
        </div>

        {/* Visualisation Area */}
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
          <div>
            {/* OPTION 1: Balance-Balken (Diverging Bar Chart) */}
            {vizMode === 'bars' && (
              <div className="space-y-3">
                <div className="flex items-center justify-between text-[11px] text-stone-500 pb-1 border-b border-stone-100">
                  <span>← Entlastet (Netto-Minus)</span>
                  <span className="font-semibold text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200">
                    Zielkorridor: ±0.5 Dienste
                  </span>
                  <span>Mehrbelastet (Netto-Plus) →</span>
                </div>

                <div className="space-y-2 max-h-[360px] overflow-y-auto pr-1">
                  {roleRecords
                    .slice()
                    .sort((a, b) => a.net_delta - b.net_delta)
                    .map((r) => {
                      const isSelected = selectedStaffId === r.identifier;
                      const isHovered = hoveredStaffId === r.identifier;
                      // Max range for bar clamp: -3 to +3
                      const maxAbs = 3.0;
                      const netClamped = Math.max(-maxAbs, Math.min(maxAbs, r.net_delta));
                      const pct = Math.abs(netClamped) / maxAbs * 45; // max 45% width from center

                      const isBalanced = Math.abs(r.net_delta) <= 0.5;
                      const isSlight = Math.abs(r.net_delta) <= 1.0;

                      return (
                        <div
                          key={r.identifier}
                          onClick={() => setSelectedStaffId(r.identifier)}
                          onMouseEnter={() => setHoveredStaffId(r.identifier)}
                          onMouseLeave={() => setHoveredStaffId(null)}
                          className={cn(
                            'group flex items-center gap-3 p-2 rounded-lg cursor-pointer transition-all border text-xs',
                            isSelected
                              ? 'bg-blue-50/80 border-[#324b9b] shadow-2xs'
                              : isHovered
                              ? 'bg-stone-50 border-stone-300'
                              : 'bg-white border-stone-200/70 hover:border-stone-300'
                          )}
                        >
                          {/* Staff Info */}
                          <div className="w-40 shrink-0 flex items-center gap-2">
                            <span className="font-bold text-stone-900 truncate">{r.name}</span>
                            <span className="text-[10px] text-stone-500 font-mono">({r.identifier})</span>
                          </div>

                          {/* Diverging Bar Track */}
                          <div className="flex-1 relative h-6 bg-stone-100/90 rounded flex items-center overflow-hidden">
                            {/* Neutral Zero Line */}
                            <div className="absolute left-1/2 top-0 bottom-0 w-0.5 bg-stone-300 z-10" />

                            {/* ±0.5 Target Band in background */}
                            <div
                              className="absolute top-0 bottom-0 bg-emerald-100/50 z-0"
                              style={{
                                left: `${50 - (0.5 / maxAbs) * 45}%`,
                                width: `${(1.0 / maxAbs) * 45}%`,
                              }}
                            />

                            {/* Left Bar (Negative Delta) */}
                            {r.net_delta < 0 && (
                              <div
                                className={cn(
                                  'absolute top-1 bottom-1 rounded-l transition-all z-20 flex items-center justify-start pl-1.5 text-[10px] font-bold text-white',
                                  isBalanced
                                    ? 'bg-emerald-500'
                                    : isSlight
                                    ? 'bg-amber-500'
                                    : 'bg-rose-500'
                                )}
                                style={{
                                  right: '50%',
                                  width: `${Math.max(pct, 2)}%`,
                                }}
                              >
                                {r.net_delta.toFixed(2)}
                              </div>
                            )}

                            {/* Right Bar (Positive Delta) */}
                            {r.net_delta >= 0 && (
                              <div
                                className={cn(
                                  'absolute top-1 bottom-1 rounded-r transition-all z-20 flex items-center justify-end pr-1.5 text-[10px] font-bold text-white',
                                  isBalanced
                                    ? 'bg-emerald-500'
                                    : isSlight
                                    ? 'bg-amber-500'
                                    : 'bg-rose-500'
                                )}
                                style={{
                                  left: '50%',
                                  width: `${Math.max(pct, 2)}%`,
                                }}
                              >
                                {r.net_delta.toFixed(2)}
                              </div>
                            )}
                          </div>

                          {/* Detail Pill */}
                          <div className="w-32 shrink-0 text-right text-[11px] font-mono text-stone-600">
                            <span title="Plan vs. Soll">P: {r.plan_delta > 0 ? `+${r.plan_delta.toFixed(2)}` : r.plan_delta.toFixed(2)}</span>
                            <span className="text-stone-300 mx-1">|</span>
                            <span title="Vorquartal">V: {r.cf_delta > 0 ? `+${r.cf_delta.toFixed(2)}` : r.cf_delta.toFixed(2)}</span>
                          </div>
                        </div>
                      );
                    })}
                </div>
              </div>
            )}

            {/* OPTION 2: Ausgleichs-Pfeile / Vorher-Nachher Vektor-Plot */}
            {vizMode === 'arrows' && (() => {
              // Helper calculations for each record
              const getRecordMetrics = (r: StaffFairnessRecord) => {
                const init = r.cf_delta;
                const final = r.net_delta;
                const plan = r.plan_delta;
                const absInit = Math.abs(init);
                const absFinal = Math.abs(final);
                const isBalanced = absFinal <= 0.5;
                const isSlight = absFinal <= 1.0;

                // Distance to 0 decreased by at least 0.05 OR stayed cleanly within target zone
                const isImproved = absFinal < absInit - 0.05 || (absInit <= 0.5 && isBalanced);

                // Right direction: plan compensating initial sign
                const isRightDirection =
                  isImproved ||
                  (init > 0.05 && plan < 0) ||
                  (init < -0.05 && plan > 0) ||
                  (absInit <= 0.5 && isBalanced);

                const isOutlier = absFinal > 1.0;
                const deltaImprovement = absInit - absFinal; // Positive: moved closer to 0

                return {
                  init,
                  final,
                  plan,
                  absInit,
                  absFinal,
                  isBalanced,
                  isSlight,
                  isImproved,
                  isRightDirection,
                  isOutlier,
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

              // Percentage mapping: 0 -> 50%, -plotScale -> 5%, +plotScale -> 95%
              const valToPct = (val: number): number => {
                const clamped = Math.max(-plotScale, Math.min(plotScale, val));
                return 50 + (clamped / plotScale) * 45;
              };

              const targetBandLeft = 50 - (0.5 / plotScale) * 45;
              const targetBandWidth = (1.0 / plotScale) * 45;

              return (
                <div className="space-y-4">
                  {/* A. KPI Summary Cards */}
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
                      {/* Mini Progress Bar */}
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

                    {/* Card 2: In Target Band */}
                    <div className="rounded-lg bg-stone-50 border border-stone-200/80 p-3 flex flex-col justify-between">
                      <div className="flex items-center justify-between text-xs text-stone-500">
                        <span className="font-semibold text-stone-700 flex items-center gap-1.5">
                          <TrendingUp className="h-4 w-4 text-[#324b9b]" />
                          Im Zielkorridor (±0.5)
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
                          {outlierCount > 0 ? `${outlierCount} mit Abweichung > 1.0 (Ausreißer)` : 'Keine kritischen Ausreißer'}
                        </p>
                      </div>
                      {/* Mini Target Band Visual */}
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
                    {/* View Switcher: Dumbbell vs Funnel */}
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
                        Konvergenz-Trichter (Gesamtverteilung)
                      </button>
                    </div>

                    {/* Filter & Sort Controls (only active in dumbbell mode) */}
                    {arrowSubMode === 'dumbbell' && (
                      <div className="flex flex-wrap items-center gap-2">
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
                          className="text-xs bg-white border border-stone-200 rounded-lg px-2.5 py-1 text-stone-700 font-medium cursor-pointer focus:outline-none focus:ring-1 focus:ring-[#324b9b]"
                        >
                          <option value="improvement">Sortierung: Größte Verbesserung</option>
                          <option value="initial_desc">Sortierung: Höchste Vorbelastung</option>
                          <option value="final_desc">Sortierung: Größter Rest-Saldo</option>
                          <option value="name">Sortierung: Name (A-Z)</option>
                        </select>
                      </div>
                    )}
                  </div>

                  {/* C. Legende & Achsen-Header */}
                  <div className="flex items-center justify-between text-[11px] text-stone-500 px-2 py-1 bg-stone-50/80 rounded-lg border border-stone-200/50">
                    <div className="flex items-center gap-4">
                      <div className="flex items-center gap-1.5">
                        <span className="w-3 h-3 rounded-full border-2 border-stone-400 bg-stone-200" />
                        <span>Ausgegrauter Punkt = Saldo <strong>Vorher</strong> (Vorquartal)</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className="w-3 h-3 rounded-full bg-emerald-500 shadow-2xs" />
                        <span>Farbiger Punkt = Neuer Saldo <strong>Nachher</strong> (Plan)</span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <ArrowRight className="h-3 w-3 text-emerald-600" />
                        <span>Pfeil = Ausgleichsbewegung zur Mitte</span>
                      </div>
                    </div>
                    <span className="font-semibold text-emerald-800 bg-emerald-100/70 px-2 py-0.5 rounded text-[10px]">
                      Grüner Korridor = Zielzone (±0.5 Dienste)
                    </span>
                  </div>

                  {/* D. SUB-MODE 1: DUMBBELL LIST (Per Person Vectors) */}
                  {arrowSubMode === 'dumbbell' && (
                    <div className="space-y-1.5 max-h-[460px] overflow-y-auto pr-1">
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

                          // Endpoint dot color
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
                              onClick={() => setSelectedStaffId(r.identifier)}
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

                                {/* Target Band ±0.5 */}
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
                                  {Math.abs(final) <= 0.5 ? '✓' : final > 0 ? `+${final.toFixed(1)}` : final.toFixed(1)}
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

                  {/* E. SUB-MODE 2: KONVERGENZ-TRICHTER (Parallel Coordinates / Macro Funnel) */}
                  {arrowSubMode === 'funnel' && (
                    <div className="relative w-full h-[360px] bg-[#faf9f6] rounded-xl border border-stone-200 p-2 overflow-hidden flex items-center justify-center">
                      <svg className="w-full h-full" viewBox="0 0 640 320">
                        <defs>
                          <linearGradient id="funnelBandGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                            <stop offset="0%" stopColor="#10b981" stopOpacity="0.12" />
                            <stop offset="100%" stopColor="#10b981" stopOpacity="0.25" />
                          </linearGradient>
                        </defs>

                        {/* Background Target Corridor (Height corresponding to ±0.5 on vertical axis) */}
                        {(() => {
                          const unitH = 120 / plotScale;
                          const targetHalfH = 0.5 * unitH;
                          const yTop = 160 - targetHalfH;
                          const yBot = 160 + targetHalfH;
                          return (
                            <polygon
                              points={`140,${yTop} 500,${yTop} 500,${yBot} 140,${yBot}`}
                              fill="url(#funnelBandGrad)"
                              stroke="#10b981"
                              strokeWidth="1"
                              strokeDasharray="4 3"
                            />
                          );
                        })()}

                        {/* Central Zero Baseline */}
                        <line x1="100" y1="160" x2="540" y2="160" stroke="#d6d3d1" strokeWidth="1.5" strokeDasharray="3 3" />
                        <text x="545" y="163" fontSize="9" fontWeight="bold" fill="#059669">
                          Netto 0.0 (Fairness)
                        </text>

                        {/* Axis 1: Left (Vorher) */}
                        <line x1="140" y1="30" x2="140" y2="290" stroke="#a8a29e" strokeWidth="2" />
                        <text x="140" y="20" fontSize="11" fontWeight="bold" fill="#44403c" textAnchor="middle">
                          VORHER (Vorquartals-Saldo)
                        </text>
                        <text x="135" y="35" fontSize="8" fill="#78716c" textAnchor="end">+ Mehrarbeit</text>
                        <text x="135" y="285" fontSize="8" fill="#78716c" textAnchor="end">- Entlastung</text>

                        {/* Axis 2: Right (Nachher) */}
                        <line x1="500" y1="30" x2="500" y2="290" stroke="#324b9b" strokeWidth="2" />
                        <text x="500" y="20" fontSize="11" fontWeight="bold" fill="#324b9b" textAnchor="middle">
                          NACHHER (Neuer Netto-Saldo)
                        </text>
                        <text x="505" y="35" fontSize="8" fill="#78716c">Überhang</text>
                        <text x="505" y="285" fontSize="8" fill="#78716c">Rückstand</text>

                        {/* Vector lines for all staff */}
                        {enriched.map(({ record: r, init, final, isImproved, isBalanced }) => {
                          const unitH = 120 / plotScale;
                          const y1 = 160 - init * unitH;
                          const y2 = 160 - final * unitH;

                          const isSelected = selectedStaffId === r.identifier;
                          const isHovered = hoveredStaffId === r.identifier;

                          const strokeColor = isBalanced
                            ? '#10b981'
                            : isImproved
                            ? '#3b82f6'
                            : '#f43f5e';

                          const strokeW = isSelected ? 3.5 : isHovered ? 3 : 1.5;
                          const strokeOp = hoveredStaffId
                            ? isHovered || isSelected ? 1.0 : 0.15
                            : isSelected ? 1.0 : isBalanced ? 0.7 : 0.55;

                          return (
                            <g
                              key={r.identifier}
                              onClick={() => setSelectedStaffId(r.identifier)}
                              onMouseEnter={() => setHoveredStaffId(r.identifier)}
                              onMouseLeave={() => setHoveredStaffId(null)}
                              className="cursor-pointer"
                            >
                              <title>
                                {`${r.name} (${r.identifier})\nVorher: ${init > 0 ? `+${init.toFixed(2)}` : init.toFixed(2)}\nPlan: ${r.plan_delta > 0 ? `+${r.plan_delta.toFixed(2)}` : r.plan_delta.toFixed(2)}\nNachher: ${final > 0 ? `+${final.toFixed(2)}` : final.toFixed(2)}`}
                              </title>

                              {/* Connecting Bezier curve */}
                              <path
                                d={`M 140 ${y1} C 260 ${y1}, 380 ${y2}, 500 ${y2}`}
                                fill="none"
                                stroke={strokeColor}
                                strokeWidth={strokeW}
                                strokeOpacity={strokeOp}
                                className="transition-all"
                              />

                              {/* Vorher Circle (Left Axis) */}
                              <circle
                                cx="140"
                                cy={y1}
                                r={isSelected ? 5 : isHovered ? 4.5 : 3}
                                fill="#ffffff"
                                stroke="#78716c"
                                strokeWidth="2"
                                opacity={strokeOp}
                              />

                              {/* Nachher Circle (Right Axis) */}
                              <circle
                                cx="500"
                                cy={y2}
                                r={isSelected ? 6 : isHovered ? 5.5 : 4}
                                fill={strokeColor}
                                stroke="#ffffff"
                                strokeWidth="1.5"
                                opacity={strokeOp}
                              />

                              {/* Label on Hover / Selected */}
                              {(isSelected || isHovered) && (
                                <text
                                  x="512"
                                  y={y2 + 4}
                                  fontSize="10"
                                  fontWeight="bold"
                                  fill="#1e293b"
                                >
                                  {r.name} ({r.identifier}): {final > 0 ? `+${final.toFixed(2)}` : final.toFixed(2)}
                                </text>
                              )}
                            </g>
                          );
                        })}
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
                            <span className={cn('font-bold font-mono px-1.5 py-0.2 rounded', h.isBalanced ? 'bg-emerald-100 text-emerald-900' : 'bg-amber-100 text-amber-900')}>
                              Nachher: {h.final > 0 ? `+${h.final.toFixed(2)}` : h.final.toFixed(2)}
                            </span>
                          </div>
                        );
                      })()}
                    </div>
                  )}
                </div>
              );
            })()}

            {/* OPTION 3: 2D-Scatterplot (Plan vs Vorquartal) */}
            {vizMode === 'scatter' && (
              <div className="space-y-3">
                <div className="flex items-center justify-between text-xs text-stone-600">
                  <span className="text-[11px] text-stone-500">
                    Grüne Diagonale <strong>y = -x</strong> = Perfekte Vorquartals-Kompensation (Netto = 0.0)
                  </span>
                  <span className="text-[11px] text-stone-500">
                    Klicke auf einen Punkt, um Details anzuzeigen.
                  </span>
                </div>

                {/* SVG 2D Scatterplot */}
                <div className="relative w-full h-[340px] bg-[#faf9f6] rounded-xl border border-stone-200 p-2 overflow-hidden flex items-center justify-center">
                  <svg className="w-full h-full" viewBox="0 0 600 300">
                    {/* Definitions */}
                    <defs>
                      <linearGradient id="corridorGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                        <stop offset="0%" stopColor="#10b981" stopOpacity="0.16" />
                        <stop offset="100%" stopColor="#10b981" stopOpacity="0.10" />
                      </linearGradient>
                    </defs>

                    {/* Coordinate axes */}
                    {/* Center is at (300, 150) */}
                    <line x1="50" y1="150" x2="550" y2="150" stroke="#d6d3d1" strokeWidth="1.5" />
                    <line x1="300" y1="20" x2="300" y2="280" stroke="#d6d3d1" strokeWidth="1.5" />

                    {/* Quadrant Helper Labels */}
                    <text x="80" y="35" fontSize="9.5" fontWeight="bold" fill="#047857" opacity="0.8">
                      ↖ Kompensation (Vorquartal - → Jetzt mehr)
                    </text>
                    <text x="330" y="275" fontSize="9.5" fontWeight="bold" fill="#047857" opacity="0.8">
                      Entlastung (Vorquartal + → Jetzt weniger) ↘
                    </text>

                    {/* Corridor polygon around diagonal y = -x (from Top-Left to Bottom-Right) */}
                    <polygon
                      points="92,20 508,244 508,280 92,56"
                      fill="url(#corridorGrad)"
                      stroke="#10b981"
                      strokeWidth="0.8"
                      strokeOpacity="0.4"
                    />
                    <line
                      x1="92"
                      y1="38"
                      x2="508"
                      y2="262"
                      stroke="#10b981"
                      strokeWidth="1.8"
                      strokeDasharray="4 3"
                    />

                    {/* Diagonal Label */}
                    <text
                      x="320"
                      y="142"
                      fontSize="9"
                      fontWeight="bold"
                      fill="#059669"
                      transform="rotate(27 300 150)"
                    >
                      Perfekte Nulllinie (Netto = 0.0)
                    </text>

                    {/* Axis Labels */}
                    <text x="545" y="165" fontSize="10" fontWeight="bold" fill="#78716c" textAnchor="end">
                      Vorquartal (+)
                    </text>
                    <text x="55" y="165" fontSize="10" fontWeight="bold" fill="#78716c" textAnchor="start">
                      Vorquartal (-)
                    </text>
                    <text x="310" y="30" fontSize="10" fontWeight="bold" fill="#78716c">
                      Plan-Soll (+)
                    </text>
                    <text x="310" y="275" fontSize="10" fontWeight="bold" fill="#78716c">
                      Plan-Soll (-)
                    </text>

                    {/* Data Points */}
                    {roleRecords.map((r) => {
                      const cx = Math.max(70, Math.min(530, 300 + r.cf_delta * 65));
                      const cy = Math.max(30, Math.min(270, 150 - r.plan_delta * 35));
                      const isSelected = selectedStaffId === r.identifier;
                      const isHovered = hoveredStaffId === r.identifier;

                      const isBalanced = Math.abs(r.net_delta) <= 0.5;
                      const isSlight = Math.abs(r.net_delta) <= 1.0;
                      const fill = isBalanced ? '#10b981' : isSlight ? '#f59e0b' : '#f43f5e';

                      return (
                        <g
                          key={r.identifier}
                          onClick={() => setSelectedStaffId(r.identifier)}
                          onMouseEnter={() => setHoveredStaffId(r.identifier)}
                          onMouseLeave={() => setHoveredStaffId(null)}
                          className="cursor-pointer"
                        >
                          <title>
                            {`${r.name} (${r.identifier})\nVorquartal: ${r.cf_delta > 0 ? `+${r.cf_delta}` : r.cf_delta}\nPlan vs. Soll: ${r.plan_delta > 0 ? `+${r.plan_delta}` : r.plan_delta}\nNetto-Gesamtsaldo: ${r.net_delta > 0 ? `+${r.net_delta}` : r.net_delta}`}
                          </title>
                          <circle
                            cx={cx}
                            cy={cy}
                            r={isSelected ? 14 : isHovered ? 12 : 9}
                            fill={fill}
                            stroke={isSelected ? '#1e293b' : '#ffffff'}
                            strokeWidth={isSelected ? 2.5 : 1.5}
                            opacity={0.92}
                            className="transition-all"
                          />
                          <text
                            x={cx}
                            y={cy + 3}
                            fontSize="8"
                            fontWeight="bold"
                            fill="#ffffff"
                            textAnchor="middle"
                            pointerEvents="none"
                          >
                            {r.identifier}
                          </text>
                        </g>
                      );
                    })}
                  </svg>

                  {/* Floating Hover Info Pill */}
                  {hoveredStaffId && (() => {
                    const h = roleRecords.find((x) => x.identifier === hoveredStaffId);
                    if (!h) return null;
                    return (
                      <div className="absolute bottom-3 left-4 bg-white/95 backdrop-blur-xs border border-stone-300 rounded-lg shadow-sm px-3 py-1.5 text-[11px] pointer-events-none flex items-center gap-2">
                        <span className="font-bold text-stone-900">{h.name} ({h.identifier}):</span>
                        <span className="text-stone-600">VorQ: {h.cf_delta > 0 ? `+${h.cf_delta.toFixed(2)}` : h.cf_delta.toFixed(2)}</span>
                        <span className="text-stone-300">|</span>
                        <span className="text-blue-700 font-semibold">Plan: {h.plan_delta > 0 ? `+${h.plan_delta.toFixed(2)}` : h.plan_delta.toFixed(2)}</span>
                        <span className="text-stone-300">→</span>
                        <span className={cn('font-bold font-mono px-1.5 py-0.2 rounded', Math.abs(h.net_delta) <= 0.5 ? 'bg-emerald-100 text-emerald-900' : 'bg-amber-100 text-amber-900')}>
                          Netto: {h.net_delta > 0 ? `+${h.net_delta.toFixed(2)}` : h.net_delta.toFixed(2)}
                        </span>
                      </div>
                    );
                  })()}
                </div>
              </div>
            )}

            {/* OPTION 4: Dichte-Streifen / Team-Korridor (Strip Plot) */}
            {vizMode === 'strip' && (
              <div className="space-y-4">
                <div className="text-[11px] text-stone-500 flex items-center justify-between">
                  <span>← Stark entlastet</span>
                  <span className="font-semibold text-emerald-800">
                    Schwarm-Verteilung des Netto-Saldos aller {roleRecords.length} Mitarbeiter
                  </span>
                  <span>Stark belastet →</span>
                </div>

                {/* Strip Container */}
                <div className="relative h-20 bg-stone-100 rounded-xl border border-stone-200/80 flex items-center px-6">
                  {/* Target Zone */}
                  <div
                    className="absolute top-0 bottom-0 bg-emerald-200/40 border-x border-emerald-400/50"
                    style={{ left: '40%', width: '20%' }}
                  />
                  <div className="absolute top-1 left-1/2 -translate-x-1/2 text-[9px] font-bold text-emerald-800 uppercase tracking-widest">
                    Zielkorridor (0.0)
                  </div>

                  {/* Horizontal Baseline */}
                  <div className="w-full h-1 bg-stone-300 rounded" />

                  {/* Data Points */}
                  {roleRecords.map((r, idx) => {
                    // Map -3 to +3 to 5%..95%
                    const clamped = Math.max(-3, Math.min(3, r.net_delta));
                    const leftPct = 50 + (clamped / 3) * 45;
                    const isSelected = selectedStaffId === r.identifier;
                    const isBalanced = Math.abs(r.net_delta) <= 0.5;

                    // Slight jitter on Y axis to prevent perfect overlap
                    const yOffset = ((idx % 3) - 1) * 14;

                    return (
                      <button
                        key={r.identifier}
                        onClick={() => setSelectedStaffId(r.identifier)}
                        style={{
                          left: `${leftPct}%`,
                          transform: `translate(-50%, calc(-50% + ${yOffset}px))`,
                        }}
                        className={cn(
                          'absolute top-1/2 px-1.5 py-0.5 rounded-full text-[10px] font-bold transition-transform cursor-pointer border shadow-2xs',
                          isSelected
                            ? 'bg-[#324b9b] text-white border-blue-900 scale-125 z-30'
                            : isBalanced
                            ? 'bg-emerald-100 text-emerald-900 border-emerald-300 hover:scale-110'
                            : 'bg-amber-100 text-amber-900 border-amber-300 hover:scale-110'
                        )}
                        title={`${r.name} (${r.identifier}): Netto ${r.net_delta > 0 ? `+${r.net_delta}` : r.net_delta}`}
                      >
                        {r.identifier}
                      </button>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 5. Detail Inspector Drawer (Shows when a staff member is selected) */}
      {selectedStaff && (
        <div className="rounded-xl border border-blue-200 bg-blue-50/40 p-5 shadow-2xs relative transition-all">
          <button
            onClick={() => setSelectedStaffId(null)}
            className="absolute top-4 right-4 text-stone-400 hover:text-stone-700 p-1 rounded-md hover:bg-stone-200/50 cursor-pointer"
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

      {/* 6. Filter & Search Controls for Detail Table */}
      <div className="bg-white rounded-xl border border-stone-200/80 shadow-2xs overflow-hidden">
        <div className="p-4 border-b border-stone-200/80 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <h3 className="text-sm font-bold text-stone-900">
              Mitarbeiter-Tabelle: {selectedRole} ({filteredRecords.length} von {roleRecords.length})
            </h3>

            {/* Status Filter Chips */}
            <div className="hidden sm:inline-flex rounded-lg border border-stone-200 bg-stone-100/70 p-0.5 text-xs font-medium">
              {[
                { id: 'ALL', label: 'Alle' },
                { id: 'balanced', label: '🟢 Im Soll (±0.5)' },
                { id: 'slight_deviation', label: '🟡 Leichte Abw.' },
                { id: 'warning', label: '🔴 Prüfen' },
              ].map((f) => (
                <button
                  key={f.id}
                  onClick={() => setStatusFilter(f.id as FilterStatus)}
                  className={cn(
                    'px-2 py-0.5 rounded transition-all cursor-pointer text-[11px]',
                    statusFilter === f.id
                      ? 'bg-white text-stone-900 font-bold shadow-2xs'
                      : 'text-stone-600 hover:text-stone-900'
                  )}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>

          {/* Search Box */}
          <div className="relative w-full sm:w-64">
            <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-stone-400" />
            <input
              type="text"
              placeholder="Mitarbeiter suchen..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-8 pr-3 py-1.5 bg-stone-50 border border-stone-200 rounded-lg text-xs text-stone-800 placeholder-stone-400 focus:outline-none focus:ring-1 focus:ring-[#324b9b] focus:border-[#324b9b]"
            />
          </div>
        </div>

        {/* The 3-Column Core Table */}
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead className="bg-[#f5f4f0] border-b border-stone-300 text-stone-700 font-bold">
              <tr>
                <th className="py-2.5 px-3 border-r border-stone-200">Mitarbeiter</th>
                <th className="py-2.5 px-3 border-r border-stone-200 text-center">Vertrag & Urlaub</th>
                <th className="py-2.5 px-3 border-r border-stone-200 text-center">Geplant (Nächte / WE)</th>
                <th className="py-2.5 px-3 border-r border-stone-200 text-right bg-blue-50/50 text-[#324b9b]">
                  ① Plan vs. Soll
                </th>
                <th className="py-2.5 px-3 border-r border-stone-200 text-right">
                  ② Vorquartal
                </th>
                <th className="py-2.5 px-3 border-r border-stone-200 text-right bg-emerald-50/50 text-emerald-900">
                  ③ Netto-Bilanz
                </th>
                <th className="py-2.5 px-3">Erläuterung & Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-200">
              {filteredRecords.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-stone-400">
                    Keine Mitarbeiter gefunden.
                  </td>
                </tr>
              ) : (
                filteredRecords.map((r) => {
                  const isSelected = selectedStaffId === r.identifier;
                  const isBalanced = r.status === 'balanced';
                  const isSlight = r.status === 'slight_deviation';

                  return (
                    <tr
                      key={r.identifier}
                      onClick={() => setSelectedStaffId(r.identifier)}
                      className={cn(
                        'cursor-pointer transition-colors',
                        isSelected
                          ? 'bg-blue-50/80 font-medium'
                          : 'hover:bg-stone-50/80'
                      )}
                    >
                      {/* Name & Initials */}
                      <td className="py-2.5 px-3 border-r border-stone-200">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-stone-900">{r.name}</span>
                          <span className="text-[10px] text-stone-500 font-mono">({r.identifier})</span>
                        </div>
                      </td>

                      {/* Contract & Vacation */}
                      <td className="py-2.5 px-3 border-r border-stone-200 text-center text-stone-600">
                        <span>{r.hours}h</span>
                        {r.vacation_days > 0 && (
                          <span className="text-[10px] text-stone-400 ml-1">
                            ({r.vacation_days} Tg. Ur.)
                          </span>
                        )}
                      </td>

                      {/* Actual Shifts */}
                      <td className="py-2.5 px-3 border-r border-stone-200 text-center text-stone-700 font-medium">
                        {r.effective_nights} N · {r.weekend_shifts} WE
                      </td>

                      {/* 1. Plan vs Soll */}
                      <td className="py-2.5 px-3 border-r border-stone-200 text-right font-mono font-medium bg-blue-50/30">
                        <span
                          className={cn(
                            r.plan_delta > 0 ? 'text-blue-800' : r.plan_delta < 0 ? 'text-blue-600' : 'text-stone-500'
                          )}
                        >
                          {r.plan_delta > 0 ? `+${r.plan_delta.toFixed(2)}` : r.plan_delta.toFixed(2)}
                        </span>
                      </td>

                      {/* 2. Carry Forward */}
                      <td className="py-2.5 px-3 border-r border-stone-200 text-right font-mono text-stone-600">
                        {r.cf_delta > 0 ? `+${r.cf_delta.toFixed(2)}` : r.cf_delta.toFixed(2)}
                      </td>

                      {/* 3. Net Balance */}
                      <td className="py-2.5 px-3 border-r border-stone-200 text-right bg-emerald-50/30">
                        <span
                          className={cn(
                            'inline-block px-2 py-0.5 rounded font-mono font-bold text-xs',
                            isBalanced
                              ? 'bg-emerald-100 text-emerald-900 border border-emerald-200'
                              : isSlight
                              ? 'bg-amber-100 text-amber-900 border border-amber-200'
                              : 'bg-rose-100 text-rose-900 border border-rose-200'
                          )}
                        >
                          {r.net_delta > 0 ? `+${r.net_delta.toFixed(2)}` : r.net_delta.toFixed(2)}
                        </span>
                      </td>

                      {/* Explanation */}
                      <td className="py-2.5 px-3 text-stone-600 text-[11px]">
                        <div className="flex items-center justify-between gap-2">
                          <span className="truncate">{r.explanation}</span>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedStaffId(r.identifier);
                            }}
                            className="text-[#324b9b] hover:underline font-semibold text-[10px] shrink-0"
                          >
                            Details
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
    </div>
  );
};
