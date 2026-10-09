class ProviderError(Exception):
    """A failure with a message that is safe to show directly in the UI."""

    def __init__(self, code: str, message: str, retryable: bool = False, status: int = 502):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.status = status

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message}
