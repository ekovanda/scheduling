import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Checks whether a given birthday string (format "MM-DD") matches today's date.
 * Robust against leading zeros (e.g. "04-05" vs "4-5").
 */
export function isBirthdayToday(birthday?: string | null, targetDate = new Date()): boolean {
  if (!birthday) return false;
  const parts = birthday.trim().split('-');
  if (parts.length !== 2) return false;
  const bMonth = parseInt(parts[0], 10);
  const bDay = parseInt(parts[1], 10);
  return targetDate.getMonth() + 1 === bMonth && targetDate.getDate() === bDay;
}

/**
 * Determines whether a given shift type string represents a night shift.
 * Matches CP-SAT codes (N_Mo-Di, N_So-Mo, etc.) as well as labels ("Nachtdienst", "night").
 */
export function isNightShift(type?: string | null): boolean {
  if (!type) return false;
  const s = type.toLowerCase().trim();
  return s.startsWith('n_') || s.includes('nacht') || s === 'night';
}


