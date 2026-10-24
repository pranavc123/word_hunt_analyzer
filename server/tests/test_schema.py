import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from whcore.schema import AllWordsRecord, BoardRecord, dump_record, json_schema, parse_record

FIX = Path(__file__).resolve().parents[2] / "fixtures/schema"


@pytest.mark.parametrize(
    "name,cls", [("board_example.json", BoardRecord), ("all_words_example.json", AllWordsRecord)]
)
def test_round_trip(name, cls):
    raw = json.loads((FIX / name).read_text())
    rec = parse_record(raw)
    assert isinstance(rec, cls)
    again = parse_record(dump_record(rec))
    assert again == rec
    assert json.loads(dump_record(rec))["schema"] == "v1"


def test_rejects_bad_records():
    raw = json.loads((FIX / "board_example.json").read_text())
    for patch in ({"kind": "nope"}, {"schema": "v2"}, {"status": "won"}, {"extra": 1}):
        with pytest.raises(ValidationError):
            parse_record({**raw, **patch})
    bad = json.loads(json.dumps(raw))
    bad["attempts"][0]["tiles_seen"] = [16]
    with pytest.raises(ValidationError):
        parse_record(bad)


def test_exported_schema_matches():
    exported = json.loads((FIX / "v1.json").read_text())
    assert exported == json.loads(json.dumps(json_schema(), sort_keys=True))
    assert set(exported["discriminator"]["mapping"]) == {"board", "all_words"}
