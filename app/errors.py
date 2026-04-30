class AppError(Exception):
    """Base application exception."""


class ConfigurationError(AppError):
    """Raised when runtime configuration is invalid."""


class IngestionError(AppError):
    """Raised for ingestion pipeline failures."""


class RetrievalError(AppError):
    """Raised when retrieval cannot be completed."""


class GenerationError(AppError):
    """Raised when LLM generation cannot be completed."""
