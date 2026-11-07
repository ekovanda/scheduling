import React from 'react';
import { User, Users } from 'lucide-react';
import { cn } from '../../lib/utils';
import type { Beruf, AbsenceType } from '../../types/api';
import { getAbteilungDisplay } from '../../lib/colors';

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'neutral' | 'indigo';
  children: React.ReactNode;
}

export const Badge: React.FC<BadgeProps> = ({
  variant = 'default',
  className,
  children,
  ...props
}) => {
  const variantStyles = {
    default: 'bg-blue-50/80 text-[#324b9b] border-blue-200/80',
    indigo: 'bg-indigo-50 text-indigo-700 border-indigo-200/80',
    success: 'bg-emerald-50 text-emerald-800 border-emerald-200/80',
    warning: 'bg-amber-50 text-amber-800 border-amber-200/80',
    danger: 'bg-rose-50 text-rose-800 border-rose-200/80',
    info: 'bg-sky-50 text-sky-800 border-sky-200/80',
    neutral: 'bg-stone-100 text-stone-700 border-stone-200',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium border shadow-2xs',
        variantStyles[variant],
        className
      )}
      {...props}
    >
      {children}
    </span>
  );
};

export const RoleBadge: React.FC<{ role: Beruf }> = ({ role }) => {
  const r = (role || '').trim().toLowerCase();
  switch (r) {
    case 'vet':
    case 'tierarzt':
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-50 text-rose-700 border border-rose-200/80 shadow-2xs">
          Tierarzt (Vet)
        </span>
      );
    case 'intern':
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-teal-50 text-teal-700 border border-teal-200/80 shadow-2xs">
          Intern
        </span>
      );
    case 'tfa':
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200/80 shadow-2xs">
          TFA
        </span>
      );
    case 'azubi':
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-50 text-amber-800 border border-amber-200/80 shadow-2xs">
          Azubi
        </span>
      );
    default:
      return <Badge variant="neutral">{role}</Badge>;
  }
};

export const AbteilungBadge: React.FC<{
  abteilung?: string | null;
  beruf?: string | null;
}> = ({ abteilung, beruf }) => {
  const display = getAbteilungDisplay(abteilung, beruf);
  if (display.isNone) {
    return <span className="text-stone-300 text-xs font-medium pl-1">—</span>;
  }
  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-0.5 rounded-md text-[11px] font-medium border shadow-2xs',
        display.badge
      )}
    >
      {display.label}
    </span>
  );
};

export const NachtdienstBadge: React.FC<{
  nd_possible: boolean;
  nd_alone: boolean;
}> = ({ nd_possible, nd_alone }) => {
  if (!nd_possible) {
    return (
      <span className="text-stone-300 text-xs font-medium pl-1" title="Kein Nachtdienst">
        —
      </span>
    );
  }
  if (nd_alone) {
    return (
      <span
        className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-purple-50 text-purple-900 border border-purple-200/80 shadow-2xs"
        title="Alleine tauglich (1 Person)"
      >
        <User className="h-3 w-3 text-purple-700" />
        Alleine
      </span>
    );
  }
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-blue-50 text-[#324b9b] border border-blue-200/80 shadow-2xs"
      title="Nur zu zweit / Begleitung (2 Personen)"
    >
      <Users className="h-3 w-3 text-[#324b9b]" />
      Zu zweit
    </span>
  );
};

export const AbsenceBadge: React.FC<{ type: AbsenceType }> = ({ type }) => {
  switch (type) {
    case 'Vacation':
      return <Badge variant="success">Urlaub</Badge>;
    case 'Training':
      return <Badge variant="info">Fortbildung</Badge>;
    case 'SickLeave':
      return <Badge variant="danger">Krank</Badge>;
    case 'SpecialLeave':
      return <Badge variant="warning">Sonderurlaub</Badge>;
    default:
      return <Badge variant="neutral">{type}</Badge>;
  }
};
