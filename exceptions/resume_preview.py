class ResumePreviewError(ValueError):
    """Raised when a resume file cannot be converted to preview images."""


class ResumePreviewFileNotFoundError(ResumePreviewError, FileNotFoundError):
    """Raised when the stored resume file does not exist."""


class UnsupportedResumePreviewFileError(ResumePreviewError):
    """Raised when the resume file type cannot be previewed."""


class ResumePreviewDependencyError(ResumePreviewError, ImportError):
    """Raised when a required preview conversion dependency is unavailable."""


class ResumePreviewConversionError(ResumePreviewError):
    """Raised when preview image generation fails."""


__all__ = [
    "ResumePreviewConversionError",
    "ResumePreviewDependencyError",
    "ResumePreviewError",
    "ResumePreviewFileNotFoundError",
    "UnsupportedResumePreviewFileError",
]
