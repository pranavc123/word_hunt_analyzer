"""SQLite tables (PLAN §5). JSON columns hold lists/dicts; times are UTC."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel


class Session(SQLModel, table=True):
    __tablename__ = "sessions"
    id: str = Field(primary_key=True)
    started_at: datetime
    ended_at: datetime | None = None
    device: str = ""
    app_version: str = ""
    calibration_id: str = ""
    board_count: int = 0


class Calibration(SQLModel, table=True):
    __tablename__ = "calibrations"
    id: str = Field(primary_key=True)  # e.g. iphone-1206x2622@1
    device_model: str = ""
    width: int
    height: int
    tile_centers: list = Field(default_factory=list, sa_column=Column(JSON))
    roi_banner: list = Field(default_factory=list, sa_column=Column(JSON))
    roi_timer: list = Field(default_factory=list, sa_column=Column(JSON))
    color_thresholds: dict = Field(default_factory=dict, sa_column=Column(JSON))
    version: str = ""


class Board(SQLModel, table=True):
    __tablename__ = "boards"
    id: str = Field(primary_key=True)  # board_id from the phone
    session_id: str = Field(foreign_key="sessions.id", index=True)
    seq: int
    opened_at: datetime
    view_ms: int
    status: str  # played | skipped
    letters: str | None = None
    letters_conf: list | None = Field(default=None, sa_column=Column(JSON))
    letters_confirmed: bool = False
    board_hash: str | None = None
    image_path: str | None = None
    end_banner_path: str | None = None
    end_list_path: str | None = None
    final_score: int | None = None  # end-screen SCORE
    final_word_count: int | None = None  # end-screen WORDS
    extracted_score: int | None = None  # Σ points of the resolved words
    reconciled: bool = False
    review_status: str = "pending"  # pending | needs_letter_fix | needs_review | verified | skipped
    end_visible_words: list | None = Field(default=None, sa_column=Column(JSON))
    all_words_status: str = "none"  # pending | complete | partial | none
    all_words_id: str | None = None
    masked_counts_by_length: dict | None = Field(default=None, sa_column=Column(JSON))
    all_words_complete_down_to: int | None = None
    record: dict = Field(default_factory=dict, sa_column=Column(JSON))  # the uploaded record
    received_at: datetime | None = None
    processed_at: datetime | None = None
    error: str | None = None


class AllWordsCapture(SQLModel, table=True):
    __tablename__ = "all_words_captures"
    id: str = Field(primary_key=True)  # record_id from the phone
    session_id: str = Field(index=True)
    captured_at: datetime
    status: str = "pending"  # pending | complete | partial
    board_id: str | None = Field(default=None, foreign_key="boards.id")
    match_state: str = "unmatched"  # matched | unmatched | ambiguous
    rows: list | None = Field(default=None, sa_column=Column(JSON))
    counts_by_length: dict | None = Field(default=None, sa_column=Column(JSON))
    revealed: list | None = Field(default=None, sa_column=Column(JSON))
    frames_path: str | None = None
    record: dict = Field(default_factory=dict, sa_column=Column(JSON))
    received_at: datetime | None = None
    processed_at: datetime | None = None


class AttemptRow(SQLModel, table=True):
    __tablename__ = "attempts"
    id: int | None = Field(default=None, primary_key=True)
    board_id: str = Field(foreign_key="boards.id", index=True)
    seq: int
    t_start_ms: int
    t_end_ms: int
    tiles_seen: list = Field(default_factory=list, sa_column=Column(JSON))
    path: list | None = Field(default=None, sa_column=Column(JSON))  # resolved path
    word: str | None = None
    result: str  # valid_new | already_found | not_a_word
    points: int = 0
    confidence: float = 1.0


class BoardWord(SQLModel, table=True):
    __tablename__ = "board_words"
    board_id: str = Field(foreign_key="boards.id", primary_key=True)
    word: str = Field(primary_key=True)
    best_path: list = Field(default_factory=list, sa_column=Column(JSON))
    points: int
    found: bool = False
    found_at_ms: int | None = None
    in_enable: bool = False
    in_base: bool = True
    features: dict | None = Field(default=None, sa_column=Column(JSON))


class BoardFeatures(SQLModel, table=True):
    __tablename__ = "board_features"
    board_id: str = Field(foreign_key="boards.id", primary_key=True)
    max_points: int = 0
    word_count: int = 0
    count_5plus: int = 0
    top10_points: int = 0
    suffix_slots: int = 0
    vowel_count: int = 0
    rare_letters: int = 0
    predicted_score: float | None = None


class Word(SQLModel, table=True):
    __tablename__ = "words"
    word: str = Field(primary_key=True)
    in_base: bool = False
    in_enable: bool = False
    in_reference: dict | None = Field(default=None, sa_column=Column(JSON))
    status: str = "unverified"  # confirmed | rejected | unverified | conflict
    accept_count: int = 0
    reject_count: int = 0
    slot_evidence: int = 0
    first_seen_board: str | None = None
    zipf_freq: float | None = None


class DictionaryVersion(SQLModel, table=True):
    __tablename__ = "dictionary_versions"
    id: int | None = Field(default=None, primary_key=True)
    name: str
    sha256: str = Field(index=True)
    uploaded_at: datetime
    word_count: int


class Insight(SQLModel, table=True):
    __tablename__ = "insights"
    id: int | None = Field(default=None, primary_key=True)
    computed_at: datetime
    kind: str
    payload: dict = Field(default_factory=dict, sa_column=Column(JSON))
    sample_size: int = 0
