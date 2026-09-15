"""Application exceptions, each mapped to an HTTP status by a handler in main.py."""


class AppError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, details: list | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or []


class BadRequestError(AppError):
    status_code = 400
    code = "bad_request"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "payload_too_large"


class ModelLoadError(AppError):
    """A registered artifact is missing, corrupt or unreadable."""

    status_code = 503
    code = "model_load_failed"


class InferenceError(AppError):
    """The model loaded but failed to produce a prediction."""

    status_code = 503
    code = "inference_failed"
