import React from 'react';
import { cn } from '../../lib/utils';
import type { Beruf } from '../../types/api';

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
    default: 'bg-indigo-50 text-indigo-700 border-indigo-200',
    success: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    warning: 'bg-amber-50 text-amber-700 border-amber-200',
    danger: 'bg-rose-50 text-rose-700 border-rose-200',
    info: 'bg-sky-50 text-sky-700 border-sky-200',
    neutral: 'bg-slate-100 text-slate-700 border-slate-200',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium border',
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
    case 'Tierarzt':
      return <Badge variant="default">Tierarzt</Badge>;
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
