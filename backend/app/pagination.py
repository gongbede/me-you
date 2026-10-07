from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, or_


def encode_cursor(*values: str) -> str:
    raw = json.dumps(values, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str, expected_parts: int) -> tuple[str, ...]:
    try:
        if not cursor or len(cursor) > 512:
            raise ValueError
        padding = "=" * (-len(cursor) % 4)
        decoded: Any = json.loads(
            base64.urlsafe_b64decode(cursor + padding).decode("utf-8")
        )
        if (
            not isinstance(decoded, list)
            or len(decoded) != expected_parts
            or any(not isinstance(value, str) for value in decoded)
        ):
            raise ValueError
        return tuple(decoded)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(status_code=422, detail="Invalid pagination cursor") from None


def decode_time_uuid_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    values = decode_cursor(cursor, 2)
    try:
        occurred_at = datetime.fromisoformat(values[0])
        if occurred_at.tzinfo is None:
            raise ValueError
        return occurred_at, uuid.UUID(values[1])
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid pagination cursor") from None


def descending_time_uuid_clause(timestamp_column, id_column, cursor: str):
    occurred_at, identifier = decode_time_uuid_cursor(cursor)
    return or_(
        timestamp_column < occurred_at,
        and_(timestamp_column == occurred_at, id_column < identifier),
    )


def ascending_time_uuid_clause(timestamp_column, id_column, cursor: str):
    occurred_at, identifier = decode_time_uuid_cursor(cursor)
    return or_(
        timestamp_column > occurred_at,
        and_(timestamp_column == occurred_at, id_column > identifier),
    )


def ascending_username_uuid_clause(username_column, id_column, cursor: str):
    username, identifier_value = decode_cursor(cursor, 2)
    try:
        identifier = uuid.UUID(identifier_value)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid pagination cursor") from None
    return or_(
        username_column > username,
        and_(username_column == username, id_column > identifier),
    )


def time_uuid_cursor(timestamp: datetime, identifier: uuid.UUID) -> str:
    return encode_cursor(timestamp.isoformat(), str(identifier))


def username_uuid_cursor(username: str, identifier: uuid.UUID) -> str:
    return encode_cursor(username, str(identifier))