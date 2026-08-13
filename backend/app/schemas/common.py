from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class PageMeta(BaseModel):
    page: int
    page_size: int
    total: int
