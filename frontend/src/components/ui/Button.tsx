import React from 'react';
import { cn } from '../../lib/utils';

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
}

export const Button: React.FC<ButtonProps> = ({
  variant = 'primary',
  size = 'md',
  className,
  children,
  ...props
}) => {
  const base =
    'inline-flex items-center justify-center font-medium rounded-lg transition-all focus:outline-none focus:ring-2 focus:ring-offset-1 disabled:opacity-50 disabled:pointer-events-none cursor-pointer';

  const variants = {
    primary: 'bg-[#324b9b] text-white hover:bg-[#273a78] focus:ring-[#324b9b]/50 shadow-xs hover:shadow-sm',
    secondary: 'bg-stone-800 text-white hover:bg-stone-900 focus:ring-stone-600 shadow-xs',
    outline: 'border border-stone-300 bg-white text-stone-700 hover:bg-stone-50 hover:border-stone-400 focus:ring-[#324b9b]/40 shadow-2xs',
    ghost: 'text-stone-600 hover:bg-stone-100/80 hover:text-stone-900 focus:ring-stone-400',
    danger: 'bg-rose-600 text-white hover:bg-rose-700 focus:ring-rose-500 shadow-xs',
  };

  const sizes = {
    sm: 'text-xs px-2.5 py-1.5 gap-1.5',
    md: 'text-sm px-3.5 py-2 gap-2',
    lg: 'text-base px-4 py-2.5 gap-2.5',
  };

  return (
    <button
      className={cn(base, variants[variant], sizes[size], className)}
      {...props}
    >
      {children}
    </button>
  );
};
