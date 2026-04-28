from .base import OfferPilotError


class ResumeError(OfferPilotError):
    """Base exception for resume-related operations."""


class ResumeValidationError(ResumeError, ValueError):
    """Raised when resume input is invalid."""


class ResumeNotFoundError(ResumeError, LookupError):
    """Raised when a resume record cannot be found."""


class ResumeFileNotFoundError(ResumeNotFoundError, FileNotFoundError):
    """Raised when a stored resume file cannot be found."""


class EmptyResumeContentError(ResumeValidationError):
    """Raised when the provided resume content is blank."""


class ResumeParsingError(ResumeError):
    """Raised when resume content cannot be extracted."""


class UnsupportedResumeFileError(ResumeValidationError):
    """Raised when the uploaded resume file type is not supported."""


class ResumePreviewError(ResumeError):
    """Base exception for resume preview generation failures."""


class ResumePreviewFileNotFoundError(ResumePreviewError, FileNotFoundError):
    """Raised when the resume preview source file cannot be found."""


class UnsupportedResumePreviewFileError(ResumePreviewError):
    """Raised when the resume preview source type is not supported."""


class ResumePreviewDependencyError(ResumePreviewError, ImportError):
    """Raised when a preview dependency is not available."""


class ResumePreviewConversionError(ResumePreviewError):
    """Raised when a resume preview cannot be rendered."""

class NotAResumeError(ResumeError):
    """Raised when the provided document is not recognized as a resume."""


__all__ = [
    "EmptyResumeContentError",
    "ResumeError",
    "ResumeFileNotFoundError",
    "ResumeNotFoundError",
    "ResumeParsingError",
    "ResumePreviewConversionError",
    "ResumePreviewDependencyError",
    "ResumePreviewError",
    "ResumePreviewFileNotFoundError",
    "ResumeValidationError",
    "UnsupportedResumeFileError",
    "UnsupportedResumePreviewFileError",
    "NotAResumeError"
]
