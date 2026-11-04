"""Custom domain exceptions for the persistence layer."""


class PersistenceError(Exception):
    """Base exception for persistence and storage errors."""


class EntityNotFoundError(PersistenceError):
    """Raised when a requested entity does not exist in storage."""


class DuplicateEntityError(PersistenceError):
    """Raised when creating an entity that already exists."""


class InvalidStateTransitionError(PersistenceError):
    """Raised when an illegal lifecycle state transition is attempted."""
