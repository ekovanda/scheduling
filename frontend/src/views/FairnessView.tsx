import React from 'react';
import { CheckCircle2, TrendingUp, ShieldAlert, Award } from 'lucide-react';

export const FairnessView: React.FC = () => {
  return (
    <div className="space-y-6">
      {/* Title */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">
          Fairness & Belastungs-Scorecard
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Verständliche Kennzahlen zur Gleichverteilung der Nacht- und Wochenenddienste für die Klinikleitung.
        </p>
      </div>

      {/* 3 High-Signal Indicators */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {/* Signal 1: Target Adherence */}
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-2xs space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              1. Zielerfüllung Nachtdienste
            </span>
            <TrendingUp className="h-4 w-4 text-indigo-600" />
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold text-slate-900">96%</span>
            <span className="text-xs text-emerald-600 font-semibold">Exzellent</span>
          </div>
          <p className="text-xs text-slate-500 leading-relaxed">
            Abweichung der zugeteilten Nachtdienste vom statistischen Soll aller Vollzeit- und Teilzeitkräfte.
          </p>
          <div className="w-full bg-slate-100 rounded-full h-2">
            <div className="bg-emerald-500 h-2 rounded-full w-[96%]" />
          </div>
        </div>

        {/* Signal 2: Weekend Balance */}
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-2xs space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              2. Wochenend-Verteilung
            </span>
            <Award className="h-4 w-4 text-emerald-600" />
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold text-slate-900">± 1 Dienst</span>
            <span className="text-xs text-emerald-600 font-semibold">Max. Spreizung</span>
          </div>
          <p className="text-xs text-slate-500 leading-relaxed">
            Maximale Differenz der Wochenenddienste zwischen Mitarbeitern mit vergleichbarem Beschäftigungsgrad.
          </p>
          <div className="w-full bg-slate-100 rounded-full h-2">
            <div className="bg-indigo-600 h-2 rounded-full w-[88%]" />
          </div>
        </div>

        {/* Signal 3: Rest & Compliance Traffic Light */}
        <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-2xs space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
              3. Ruhezeit- & Schutzregeln
            </span>
            <ShieldAlert className="h-4 w-4 text-sky-600" />
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold text-emerald-600">0</span>
            <span className="text-xs text-slate-500">Konflikte</span>
          </div>
          <div className="space-y-1.5 pt-1 text-xs">
            <div className="flex items-center gap-1.5 text-slate-700">
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
              <span>11h gesetzliche Ruhezeit eingehalten</span>
            </div>
            <div className="flex items-center gap-1.5 text-slate-700">
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />
              <span>Maximal 4 Nachtdienste in Folge</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
