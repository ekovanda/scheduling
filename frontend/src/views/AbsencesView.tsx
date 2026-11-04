import React from 'react';
import { CalendarDays, AlertTriangle } from 'lucide-react';

export const AbsencesView: React.FC = () => {
  return (
    <div className="bg-white rounded-xl border border-stone-200/80 p-8 text-center shadow-2xs space-y-4">
      <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-stone-100 text-stone-500">
        <CalendarDays className="h-6 w-6 text-[#324b9b]" />
      </div>
      <div>
        <h2 className="text-lg font-bold text-stone-900">Abwesenheits- & Urlaubsplaner</h2>
        <p className="text-sm text-stone-500 max-w-md mx-auto mt-1">
          Hier entsteht die zentrale Verwaltung für Urlaube, Fortbildungen und Krankheitstage der Tierklinik Dr. Trillig mit sofortiger Prüfung auf Besetzungsengpässe.
        </p>
      </div>
      <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-50 border border-amber-200/80 text-amber-800 text-xs">
        <AlertTriangle className="h-4 w-4" />
        <span>Nächster Meilenstein nach Freigabe des Mitarbeiter-Hubs</span>
      </div>
    </div>
  );
};
