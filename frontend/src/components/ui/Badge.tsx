import React from 'react';
import { cn } from '../../lib/utils';
import type { Beruf, AbsenceType } from '../../types/api';

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info' | 'neutral';
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
  switch (role) {
    case 'Vet':
    case 'Tierarzt':
      return <Badge variant="default">Tierarzt (Vet)</Badge>;
    case 'TFA':
      return <Badge variant="success">TFA</Badge>;
    case 'Azubi':
      return <Badge variant="warning">Azubi</Badge>;
    case 'Intern':
      return <Badge variant="info">Intern</Badge>;
    default:
      return <Badge variant="neutral">{role}</Badge>;
  }
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
