class ConsultationWorkflowError(Exception):
    """Raised when the consultation workflow fails."""


class OCRParsingError(ConsultationWorkflowError):
    """Raised when OCR parsing or normalization fails."""


class DepartmentConsultationError(ConsultationWorkflowError):
    """Raised when department-level consultation fails."""


__all__ = [
    "ConsultationWorkflowError",
    "OCRParsingError",
    "DepartmentConsultationError",
]
