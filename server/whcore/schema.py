"""Event schema v1 (PLAN §4). Swift models in ios/WHCapture must match this file."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

SCHEMA_VERSION = "v1"

ReleaseState = Literal["valid_new", "already_found", "not_a_word"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Attempt(_Model):
    seq: int
    t_start_ms: int
    t_end_ms: int
    tiles_seen: list[Annotated[int, Field(ge=0, le=15)]]
    release_state: ReleaseState
    banner_words_after: int | None = None
    confidence: float


class Diagnostics(_Model):
    fps_processed: float
    frames_dropped: int
    mem_peak_mb: float


class BoardRecord(_Model):
    schema_: Literal["v1"] = Field(default="v1", alias="schema")
    kind: Literal["board"] = "board"
    board_id: UUID
    session_id: UUID
    seq: int
    device: str
    app_version: str
    calibration_version: str
    opened_at: datetime
    view_ms: int
    status: Literal["played", "skipped"]
    board_image: str
    end_banner_image: str | None = None
    end_list_image: str | None = None
    attempts: list[Attempt]
    diagnostics: Diagnostics


class AllWordsRecord(_Model):
    schema_: Literal["v1"] = Field(default="v1", alias="schema")
    kind: Literal["all_words"] = "all_words"
    record_id: UUID
    session_id: UUID
    captured_at: datetime
    frames: list[str]
    shifts_px: list[int]
    gap_flags: list[bool]
    bounced_at_end: bool


Record = Annotated[BoardRecord | AllWordsRecord, Field(discriminator="kind")]
RecordAdapter: TypeAdapter[BoardRecord | AllWordsRecord] = TypeAdapter(Record)


def parse_record(data: str | bytes | dict) -> BoardRecord | AllWordsRecord:
    if isinstance(data, dict):
        return RecordAdapter.validate_python(data)
    return RecordAdapter.validate_json(data)


def dump_record(rec: BoardRecord | AllWordsRecord) -> str:
    return rec.model_dump_json(by_alias=True, exclude_none=True)


def json_schema() -> dict:
    s = RecordAdapter.json_schema(by_alias=True)
    s["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    s["title"] = f"WordHuntRecord {SCHEMA_VERSION}"
    return s
