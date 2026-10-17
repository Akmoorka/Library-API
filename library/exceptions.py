class ApplicationError(Exception):
    status_code = 400
    default_code = "error"

    def __init__(self, message, *, code=None, extra=None):
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        self.extra = extra or {}


class NotFoundError(ApplicationError):
    status_code = 404
    default_code = "not_found"


class PermissionDeniedError(ApplicationError):
    status_code = 403
    default_code = "permission_denied"


class BusinessValidationError(ApplicationError):
    status_code = 400
    default_code = "validation_error"
