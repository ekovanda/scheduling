import React from 'react';
import { Calendar, Play, Download, Sparkles } from 'lucide-react';
import { Button } from '../components/ui/Button';

export const MatrixView: React.FC = () => {
  return (
    <div className="space-y-6">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 bg-white p-4 rounded-xl border border-slate-200 shadow-2xs">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl font-bold text-stone-900">Dienstplan (2026-Q2)</h1>
            <span className="px-2 py-0.5 rounded text-xs font-semibold bg-blue-50 text-[#324b9b] border border-blue-200">
              ENTWURF (DRAFT)
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-0.5">
            Synchroner OR-Tools CP-SAT Löser mit Live-Regelprüfung für Nacht- und Wochenenddienste.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm">
            <Download className="h-4 w-4 mr-1.5" />
            Excel Export (.xlsx)
          </Button>
          <Button variant="primary" size="sm">
            <Play className="h-4 w-4 mr-1.5 fill-current" />
            Plan berechnen (CP-SAT)
          </Button>
        </div>
      </div>

      {/* Hero Preview Card */}
      <div className="bg-white rounded-xl border border-slate-200 p-8 text-center shadow-2xs space-y-4">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-indigo-50 text-indigo-600">
          <Calendar className="h-6 w-6" />
        </div>
        <div>
          <h2 className="text-lg font-bold text-slate-900">Interaktive Dienstplan-Matrix</h2>
          <p className="text-sm text-slate-500 max-w-lg mx-auto mt-1">
            Wird im nächsten Schritt aktiviert: Vollständige Monats- & Quartalsansichten mit Klick-zum-Tauschen Drawer und automatischer Ruhezeitenprüfung.
          </p>
        </div>
        <div className="inline-flex items-center gap-1.5 text-xs text-indigo-600 font-medium">
          <Sparkles className="h-4 w-4" />
          <span>Vorbereitet für synchrone FastAPI-Integration</span>
        </div>
      </div>
    </div>
  );
};

