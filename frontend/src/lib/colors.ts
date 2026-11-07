/**
 * Unified clinical color coding for staff roles.
 *
 * Distinct color palettes for the 4 core clinical roles:
 * - Tierarzt (Vet): Red / Rose (prominent medical lead)
 * - Intern: Teal
 * - TFA: Blue
 * - Azubi: Amber
 *
 * Planners can immediately distinguish roles at a glance without confusing
 * department sub-variations or monochromatic blue tints.
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
  // Human-readable German label for role
  label: string;
}

export function getStaffColorScheme(
  beruf?: string | null,
  _abteilung?: string | null
): StaffColorScheme {
  const b = (beruf || '').trim().toLowerCase();

  // 1. Veterinarians (Red / Rose - high visibility for clinical leads)
  if (b === 'vet' || b === 'tierarzt') {
    return {
      avatar: 'bg-rose-50 text-rose-700 border-rose-200/80',
      calendarStrip: 'bg-rose-100 text-rose-950 border-rose-300',
      badge: 'bg-rose-50 text-rose-700 border-rose-200',
      dot: 'bg-rose-500',
      border: 'border-rose-300',
      label: 'Tierarzt (Vet)',
    };
  }

  // 2. Interns (Teal)
  if (b === 'intern') {
    return {
      avatar: 'bg-teal-50 text-teal-700 border-teal-200/80',
      calendarStrip: 'bg-teal-100 text-teal-900 border-teal-300',
      badge: 'bg-teal-50 text-teal-700 border-teal-200',
      dot: 'bg-teal-500',
      border: 'border-teal-300',
      label: 'Intern',
    };
  }

  // 3. Azubis (Amber)
  if (b === 'azubi') {
    return {
      avatar: 'bg-amber-50 text-amber-800 border-amber-200/80',
      calendarStrip: 'bg-amber-100 text-amber-950 border-amber-300',
      badge: 'bg-amber-50 text-amber-800 border-amber-200',
      dot: 'bg-amber-500',
      border: 'border-amber-300',
      label: 'Azubi',
    };
  }

  // 4. Default / TFA (Blue)
  return {
    avatar: 'bg-blue-50 text-blue-700 border-blue-200/80',
    calendarStrip: 'bg-blue-100 text-blue-900 border-blue-300',
    badge: 'bg-blue-50 text-blue-700 border-blue-200',
    dot: 'bg-blue-500',
    border: 'border-blue-300',
    label: 'TFA',
  };
}

export function getAbteilungDisplay(
  abteilung?: string | null,
  _beruf?: string | null
): {
  label: string;
  badge: string;
  isNone: boolean;
} {
  const a = (abteilung || '').trim().toLowerCase();
  switch (a) {
    case 'op':
      return {
        label: 'OP',
        badge: 'bg-stone-100 text-stone-700 border-stone-200',
        isNone: false,
      };
    case 'station':
      return {
        label: 'Station',
        badge: 'bg-stone-100 text-stone-700 border-stone-200',
        isNone: false,
      };
    default:
      return {
        label: '—',
        badge: '',
        isNone: true,
      };
  }
}
