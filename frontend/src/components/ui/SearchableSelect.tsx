import React, { useState, useRef, useEffect, useMemo } from 'react';
import { Search, ChevronDown, X, Check } from 'lucide-react';
import { cn } from '../../lib/utils';
import { getStaffColorScheme } from '../../lib/colors';
import type { StaffMember } from '../../types/api';

interface SearchableSelectProps {
  staffList: StaffMember[];
  value: string;
  onChange: (id: string) => void;
  placeholder?: string;
  required?: boolean;
  className?: string;
}

export const SearchableSelect: React.FC<SearchableSelectProps> = ({
  staffList,
  value,
  onChange,
  placeholder = 'Mitarbeiter auswählen...',
  required = false,
  className,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [highlightedIndex, setHighlightedIndex] = useState(0);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const selectedStaff = useMemo(
    () => staffList.find((s) => s.id === value || s.identifier.toLowerCase() === value.toLowerCase()),
    [staffList, value]
  );

  // Filter staff by name, identifier, or beruf
  const filteredStaff = useMemo(() => {
    if (!searchTerm.trim()) return staffList;
    const term = searchTerm.toLowerCase();
    return staffList.filter(
      (s) =>
        s.name.toLowerCase().includes(term) ||
        s.identifier.toLowerCase().includes(term) ||
        (s.beruf && s.beruf.toLowerCase().includes(term))
    );
  }, [staffList, searchTerm]);


  // Handle click outside to close dropdown
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
        setSearchTerm('');
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelect = (staffId: string) => {
    onChange(staffId);
    setIsOpen(false);
    setSearchTerm('');
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!isOpen) {
      if (e.key === 'ArrowDown' || e.key === 'Enter' || e.key === ' ') {
        setIsOpen(true);
        e.preventDefault();
      }
      return;
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setHighlightedIndex((prev) => (prev < filteredStaff.length - 1 ? prev + 1 : prev));
        break;
      case 'ArrowUp':
        e.preventDefault();
        setHighlightedIndex((prev) => (prev > 0 ? prev - 1 : 0));
        break;
      case 'Enter':
        e.preventDefault();
        if (filteredStaff[highlightedIndex]) {
          handleSelect(filteredStaff[highlightedIndex].id);
        }
        break;
      case 'Escape':
        e.preventDefault();
        setIsOpen(false);
        setSearchTerm('');
        break;
    }
  };

  return (
    <div ref={containerRef} className={cn('relative w-full', className)}>
      {/* Input / Trigger */}
      <div
        onClick={() => {
          setIsOpen(true);
          inputRef.current?.focus();
        }}
        className={cn(
          'flex items-center justify-between w-full px-3 py-2 text-sm bg-stone-50/70 border rounded-lg transition-all cursor-pointer',
          isOpen
            ? 'border-[#324b9b] ring-2 ring-[#324b9b]/20 bg-white'
            : 'border-stone-200 hover:border-stone-300'
        )}
      >
        <div className="flex items-center gap-2 flex-1 min-w-0">
          <Search className="h-4 w-4 text-stone-400 shrink-0" />
          {isOpen ? (
            <input
              ref={inputRef}
              type="text"
              value={searchTerm}
              onChange={(e) => {
                setSearchTerm(e.target.value);
                setHighlightedIndex(0);
              }}
              onKeyDown={handleKeyDown}
              placeholder={selectedStaff ? `${selectedStaff.name} (${selectedStaff.identifier})` : placeholder}
              className="w-full bg-transparent border-none p-0 text-sm text-stone-900 focus:outline-none focus:ring-0 placeholder:text-stone-400"
              autoFocus
            />
          ) : selectedStaff ? (
            <div className="flex items-center gap-2 truncate">
              <div
                className={cn(
                  'h-5 w-5 rounded-full border text-[10px] font-bold flex items-center justify-center shrink-0',
                  getStaffColorScheme(selectedStaff.beruf, selectedStaff.abteilung).avatar
                )}
              >
                {selectedStaff.name
                  .split(' ')
                  .map((n) => n[0])
                  .slice(0, 2)
                  .join('')}
              </div>
              <span className="font-semibold text-stone-900 truncate">{selectedStaff.name}</span>
              <span className="font-mono text-xs text-stone-500 font-bold">
                ({selectedStaff.identifier})
              </span>
              <span className="text-[11px] px-1.5 py-0.2 rounded bg-stone-100 text-stone-600 border border-stone-200 ml-1">
                {selectedStaff.beruf}
              </span>
            </div>
          ) : (
            <span className="text-stone-400 select-none">{placeholder}</span>
          )}
        </div>

        <div className="flex items-center gap-1 ml-2 shrink-0">
          {selectedStaff && !isOpen && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onChange('');
                setSearchTerm('');
              }}
              className="p-0.5 text-stone-400 hover:text-stone-600 rounded-full hover:bg-stone-200/50"
              title="Auswahl aufheben"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}
          <ChevronDown
            className={cn('h-4 w-4 text-stone-400 transition-transform duration-200', isOpen && 'rotate-180')}
          />
        </div>
      </div>

      {/* Hidden input for HTML form validation */}
      {required && (
        <input
          tabIndex={-1}
          autoComplete="off"
          style={{ opacity: 0, width: 0, height: 0, position: 'absolute' }}
          value={value}
          onChange={() => {}}
          required={required}
        />
      )}

      {/* Dropdown Options */}
      {isOpen && (
        <div className="absolute z-50 left-0 right-0 mt-1 max-h-60 overflow-y-auto bg-white border border-stone-200 rounded-lg shadow-lg py-1 text-sm divide-y divide-stone-50 animate-in fade-in-50 zoom-in-95 duration-100">
          {filteredStaff.length === 0 ? (
            <div className="px-3 py-3 text-center text-xs text-stone-500">
              Kein Mitarbeiter für „{searchTerm}“ gefunden.
            </div>
          ) : (
            filteredStaff.map((staff, idx) => {
              const isSelected = staff.id === value;
              const isHighlighted = idx === highlightedIndex;
              const colors = getStaffColorScheme(staff.beruf, staff.abteilung);

              return (
                <div
                  key={staff.id}
                  onMouseEnter={() => setHighlightedIndex(idx)}
                  onClick={() => handleSelect(staff.id)}
                  className={cn(
                    'flex items-center justify-between px-3 py-2 cursor-pointer transition-colors',
                    isHighlighted ? 'bg-amber-50/60' : 'hover:bg-stone-50',
                    isSelected && 'bg-blue-50/60'
                  )}
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <div
                      className={cn(
                        'h-6 w-6 rounded-full border text-[10px] font-bold flex items-center justify-center shrink-0',
                        colors.avatar
                      )}
                    >
                      {staff.name
                        .split(' ')
                        .map((n) => n[0])
                        .slice(0, 2)
                        .join('')}
                    </div>
                    <div className="flex items-center gap-1.5 truncate">
                      <span className="font-semibold text-stone-900 truncate text-xs sm:text-sm">
                        {staff.name}
                      </span>
                      <span className="font-mono text-xs text-stone-500 font-bold">
                        ({staff.identifier})
                      </span>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 shrink-0 ml-2">
                    <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-stone-100 text-stone-700 border border-stone-200">
                      {staff.beruf}
                    </span>
                    {isSelected && <Check className="h-4 w-4 text-[#324b9b]" />}
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}

      {required && (
        <input
          type="text"
          className="sr-only"
          tabIndex={-1}
          required={required}
          value={value}
          onChange={() => {}}
          onInvalid={(e) => {
            (e.target as HTMLInputElement).setCustomValidity('Bitte wählen Sie einen Mitarbeiter aus.');
          }}
          onInput={(e) => {
            (e.target as HTMLInputElement).setCustomValidity('');
          }}
          aria-hidden="true"
        />
      )}
    </div>
  );
};
