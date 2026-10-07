from typing import Literal

from pydantic import BaseModel


class SearchResult(BaseModel):
    id: str
    resource_type: Literal["institution", "course"]
    name: str
    code: str | None
    institution_id: str | None


class SearchResponse(BaseModel):
    query: str
    items: list[SearchResult]
    offset: int
    limit: int
    has_more: bool
    next_cursor: str | None = None
