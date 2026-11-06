/**
 * Unified clinical color coding for staff roles and departments.
 *
 * Ensures planning staff can instantly spot clusters of absences and shift patterns
 * across the staff overview, absences calendar, and schedule matrix.
 */

export interface StaffColorScheme {
  // Avatar / Initials circle in tables and lists
  avatar: string;
  // Continuous strip in calendar views
  calendarStrip: string;
  // Standalone badge / pill
  badge: string;
  // Small indicator dot
  dot: string;
  // Border accent
  border: string;
  // Human-readable German label for role/department
  label: string;
}

export function getStaffColorScheme(
  beruf?: string | null,
  abteilung?: string | null
): StaffColorScheme {
  const b = (beruf || '').trim().toLowerCase();
  const a = (abteilung || '').trim().toLowerCase();

  // 1. Veterinarians (Fully fledged relief vets)
  if (b === 'vet' || b === 'tierarzt') {
    return {
      avatar: 'bg-indigo-50 text-indigo-700 border-indigo-200/80',
      calendarStrip: 'bg-indigo-100/90 text-indigo-950 border-indigo-300',
      badge: 'bg-indigo-50 text-indigo-700 border-indigo-200',
      dot: 'bg-indigo-500',
      border: 'border-indigo-300',
      label: 'Tierarzt (Vet)',
    };
  }

  // 2. Interns (Veterinary interns in training)
  if (b === 'intern') {
    return {
      avatar: 'bg-sky-50 text-sky-700 border-sky-200/80',
      calendarStrip: 'bg-sky-100/90 text-sky-950 border-sky-300',
      badge: 'bg-sky-50 text-sky-700 border-sky-200',
      dot: 'bg-sky-500',
      border: 'border-sky-300',
      label: 'Intern',
    };
  }

  // 3. Azubis (Veterinary nurse trainees)
  if (b === 'azubi') {
    return {
      avatar: 'bg-amber-50 text-amber-700 border-amber-200/80',
      calendarStrip: 'bg-amber-100/90 text-amber-950 border-amber-300',
      badge: 'bg-amber-50 text-amber-700 border-amber-200',
      dot: 'bg-amber-500',
      border: 'border-amber-300',
      label: 'Azubi',
    };
  }

  // 4. TFAs by Department
  if (a === 'op') {
    return {
      avatar: 'bg-emerald-50 text-emerald-700 border-emerald-200/80',
      calendarStrip: 'bg-emerald-100/90 text-emerald-950 border-emerald-300',
      badge: 'bg-emerald-50 text-emerald-700 border-emerald-200',
      dot: 'bg-emerald-500',
      border: 'border-emerald-300',
      label: 'TFA (OP)',
    };
  }

  if (a === 'station') {
    return {
      avatar: 'bg-purple-50 text-purple-700 border-purple-200/80',
      calendarStrip: 'bg-purple-100/90 text-purple-950 border-purple-300',
      badge: 'bg-purple-50 text-purple-700 border-purple-200',
      dot: 'bg-purple-500',
      border: 'border-purple-300',
      label: 'TFA (Station)',
    };
  }

  // Default / General TFA (Sprechstunde, Praxis, Sonstiges)
  return {
    avatar: 'bg-blue-50 text-blue-700 border-blue-200/80',
    calendarStrip: 'bg-blue-100/90 text-blue-950 border-blue-300',
    badge: 'bg-blue-50 text-blue-700 border-blue-200',
    dot: 'bg-blue-500',
    border: 'border-blue-300',
    label: 'TFA (Allgemein)',
  };
}

export function getAbteilungDisplay(
  abteilung?: string | null,
  beruf?: string | null
): {
  label: string;
  badge: string;
} {
  const b = (beruf || '').trim().toLowerCase();
  if (b === 'vet' || b === 'tierarzt') {
    return {
      label: 'Klinik (Vet)',
      badge: 'bg-indigo-50/60 text-indigo-600 border-indigo-200/60',
    };
  }
  if (b === 'intern') {
    return {
      label: 'Klinik (Intern)',
      badge: 'bg-sky-50/60 text-sky-600 border-sky-200/60',
    };
  }

  const a = (abteilung || '').trim().toLowerCase();
  switch (a) {
    case 'op':
      return {
        label: 'OP',
        badge: 'bg-emerald-50 text-emerald-700 border-emerald-200/80',
      };
    case 'station':
      return {
        label: 'Station',
        badge: 'bg-purple-50 text-purple-700 border-purple-200/80',
      };
    case 'sprechstunde':
      return {
        label: 'Sprechstunde',
        badge: 'bg-teal-50 text-teal-700 border-teal-200/80',
      };
    default:
      return {
        label: 'Allgemein',
        badge: 'bg-stone-50 text-stone-600 border-stone-200/80',
      };
  }
}
