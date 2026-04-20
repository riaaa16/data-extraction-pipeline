class DepipelineError(Exception):
    """Base exception for this project."""


class UnsupportedFileTypeError(DepipelineError):
    pass


class ExtractionError(DepipelineError):
    pass


class ScannedPDFError(ExtractionError):
    pass
