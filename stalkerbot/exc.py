class HTTPException(Exception):
    def __init__(self, status_code: int, message: str, *args, **kwargs):
        self.status_code = status_code
        self.message = message
        super().__init__(*args, **kwargs)

    def __repr__(self):
        return f"{self.__class__} - {self.status_code} - {self.message}"


class RateLimitExceededException(Exception):
    def __init__(self, status_code: int, message: str, *args, **kwargs):
        self.status_code = status_code
        self.message = message
        super().__init__(*args, **kwargs)

    def __repr__(self):
        return f"{self.__class__} - {self.status_code} - {self.message}"


class MaxRetriesExceededException(Exception):
    pass


class ParsingError(Exception):
    pass
