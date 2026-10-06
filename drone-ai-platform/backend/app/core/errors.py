class AppError(Exception):
    def __init__(self, status_code: int, detail: str, *, code: str = "request_error") -> None:
        self.status_code = status_code
        self.detail = detail
        self.code = code
        super().__init__(detail)
