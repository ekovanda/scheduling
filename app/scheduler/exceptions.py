"""Custom domain exceptions for the scheduler package."""


class SchedulingError(Exception):
    """Base exception for scheduler domain errors."""


class StaffValidationError(SchedulingError):
    """Raised when staff validation fails (e.g. non-vet missing required fields or invalid hours)."""


class ColumnMappingError(SchedulingError):
    """Raised when required columns cannot be found in CSV/XLSX file."""


class FileFormatError(SchedulingError):
    """Raised when file format is invalid or unsupported."""
