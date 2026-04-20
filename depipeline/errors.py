class DepipelineError(Exception):
    """Base exception for this project."""


class UnsupportedFileTypeError(DepipelineError):
    pass


class ExtractionError(DepipelineError):
    pass


class ScannedPDFError(ExtractionError):
    pass


class OllamaError(DepipelineError):
    pass


class OllamaConnectionError(OllamaError):
    pass


class OllamaModelNotFoundError(OllamaError):
    pass


class OllamaResponseError(OllamaError):
    pass


class StructuredExtractionError(DepipelineError):
    pass
