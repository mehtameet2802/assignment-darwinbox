from __future__ import annotations


class AppError(Exception):
    """Domain error with an HTTP status for Flask to serialize."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
