import React from 'react';
import { Server, Check, Phone, Mail, ShieldAlert } from 'lucide-react';

export const AboutView: React.FC = () => {
  return (
    <div className="max-w-3xl space-y-6">
      {/* Title */}
      <div>
        <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-stone-900">
          Hilfe & Dokumentation
        </h1>
        <p className="text-sm text-stone-500 mt-0.5">
          Anleitungen zur Dienstplanung, Schichtregeln und Support der Tierklinik Dr. Trillig.
        </p>
      </div>

      {/* Quick Start Guide */}
      <div className="bg-white rounded-xl border border-stone-200/80 p-6 shadow-2xs space-y-4">
        <h2 className="text-base font-bold text-stone-900 flex items-center gap-2">
          <span>In 3 Schritten zum Quartalsdienstplan</span>
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-1">
          <div className="p-3.5 rounded-lg bg-stone-50 border border-stone-200/60 space-y-1.5">
            <span className="text-xs font-bold text-[#324b9b] uppercase">1. Personal prüfen</span>
            <p className="text-xs text-stone-600 leading-relaxed">
              Im Tab <strong>Mitarbeiter</strong> Wochenstunden und Nachtdienst-Zulassung aktualisieren.
            </p>
          </div>
          <div className="p-3.5 rounded-lg bg-stone-50 border border-stone-200/60 space-y-1.5">
            <span className="text-xs font-bold text-[#324b9b] uppercase">2. Abwesenheiten</span>
            <p className="text-xs text-stone-600 leading-relaxed">
              Urlaube und Fortbildungen eintragen, um Unterbesetzungen vorzubeugen.
            </p>
          </div>
          <div className="p-3.5 rounded-lg bg-stone-50 border border-stone-200/60 space-y-1.5">
            <span className="text-xs font-bold text-[#324b9b] uppercase">3. Löser starten</span>
            <p className="text-xs text-stone-600 leading-relaxed">
              Im Tab <strong>Dienstplan</strong> die automatische CP-SAT Optimierung starten und Excel exportieren.
            </p>
          </div>
        </div>
      </div>

      {/* Core Shift Rules & Safety */}
      <div className="bg-white rounded-xl border border-stone-200/80 p-6 shadow-2xs space-y-4">
        <h2 className="text-base font-bold text-stone-900 flex items-center gap-2">
          <ShieldAlert className="h-4 w-4 text-amber-600" />
          <span>Wichtigste Ruhezeit- & Schutzregeln</span>
        </h2>
        <ul className="space-y-2 text-sm text-stone-700">
          <li className="flex items-start gap-2">
            <Check className="h-4 w-4 text-emerald-600 mt-0.5 shrink-0" />
            <span>
              <strong>11 Stunden Ruhezeit</strong>: Nach jedem Nachtdienst müssen gesetzlich mindestens 11h Ruhepause eingehalten werden.
            </span>
          </li>
          <li className="flex items-start gap-2">
            <Check className="h-4 w-4 text-emerald-600 mt-0.5 shrink-0" />
            <span>
              <strong>Nachtdienst-Besetzung</strong>: Mindestens eine erfahrene Fachkraft (alleine tauglich) muss jede Schicht leiten.
            </span>
          </li>
          <li className="flex items-start gap-2">
            <Check className="h-4 w-4 text-emerald-600 mt-0.5 shrink-0" />
            <span>
              <strong>Wochenend-Ausgleich</strong>: Dienste an Samstagen und Sonntagen werden quartalsübergreifend fair ausgeglichen.
            </span>
          </li>
        </ul>
      </div>

      {/* Support & Release Box */}
      <div className="bg-[#faf9f6] rounded-xl border border-stone-200/80 p-6 shadow-2xs flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-stone-500">
            <Server className="h-3.5 w-3.5 text-[#324b9b]" />
            <span>Systemversion 1.8.0 &middot; Tierklinik Dr. Trillig</span>
          </div>
          <p className="text-xs text-stone-500">
            Fragen oder technischer Support zur Dienstplan-Optimierung:
          </p>
        </div>
        <div className="flex items-center gap-3 text-xs font-medium text-stone-700">
          <span className="flex items-center gap-1">
            <Phone className="h-3.5 w-3.5 text-stone-400" />
            Klinikleitung
          </span>
          <span className="flex items-center gap-1">
            <Mail className="h-3.5 w-3.5 text-stone-400" />
            Support
          </span>
        </div>
      </div>
    </div>
  );
};
