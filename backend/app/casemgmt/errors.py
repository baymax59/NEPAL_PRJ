"""Case Management errors. The API turns each into its HTTP status (docs/case-management/04 §11)."""


class CaseManagementError(Exception):
    status = 400

    def __init__(self, message: str, **extra):
        super().__init__(message)
        self.extra = extra  # extra fields for the response, e.g. current_head; `exists` is for the audit log only


class NotVisible(CaseManagementError):
    """404, the same whether the thing is missing or the user may not see it."""

    status = 404

    def __init__(self, *, exists: bool = False):
        super().__init__("Not found", exists=exists)


class Forbidden(CaseManagementError):
    """403: visible, but not allowed."""

    status = 403


class Conflict(CaseManagementError):
    """409: someone else changed it first; nothing was overwritten."""

    status = 409


class Invalid(CaseManagementError):
    """422: the request can't be carried out as asked."""

    status = 422


class Gone(CaseManagementError):
    """410: it existed but can't be used any more (e.g. a download link already used)."""

    status = 410


class TooLarge(CaseManagementError):
    """413: the uploaded file is over the size limit."""

    status = 413


class Unsupported(CaseManagementError):
    """415: the file's content doesn't match its name, or the type isn't accepted."""

    status = 415
