import React from 'react';
import { Server, Check } from 'lucide-react';

export const AboutView: React.FC = () => {
  return (
    <div className="max-w-3xl space-y-6">
      {/* Title */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">
          Über das Dienstplan-System
        </h1>
        <p className="text-sm text-slate-500 mt-0.5">
          Architektur, aktuelle Versionshinweise und technische Meilensteine.
        </p>
      </div>

      {/* Version Card */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-2xs space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-indigo-50 text-indigo-600">
              <Server className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900">Version 1.8.0 (Modernisierung)</h2>
              <p className="text-xs text-slate-500">FastAPI Backend + React Single-Page-App</p>
            </div>
          </div>
          <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            Aktuellste Version
          </span>
        </div>

        <div className="border-t border-slate-100 pt-4 space-y-3">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Neuerungen in diesem Release
          </h3>
          <ul className="space-y-2 text-sm text-slate-700">
            <li className="flex items-start gap-2">
              <Check className="h-4 w-4 text-emerald-500 mt-0.5 shrink-0" />
              <span>
                <strong>Single Source of Truth</strong>: Zentrale Mitarbeiter- und Abwesenheitsverwaltung ersetzt manuelle Excel-Uploads.
              </span>
            </li>
            <li className="flex items-start gap-2">
              <Check className="h-4 w-4 text-emerald-500 mt-0.5 shrink-0" />
              <span>
                <strong>Moderne React Oberfläche</strong>: Ultraschnelle Ladezeiten, Tastaturfreundliche Dialoge und responsive Tabellen.
              </span>
            </li>
            <li className="flex items-start gap-2">
              <Check className="h-4 w-4 text-emerald-500 mt-0.5 shrink-0" />
              <span>
                <strong>Vereinfachte Fairness-Signale</strong>: Klare Zielerfüllungs- und Belastungswerte anstelle komplexer statistischer Indizes.
              </span>
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
};
