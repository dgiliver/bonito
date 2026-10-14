"""Tests for the pre-registered strategy-search runner's gates (one-shot decision)."""

import importlib.util
from datetime import date
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "search", Path("scripts/experiments/2026-10-14_momentum_rotation_search.py")
)
search = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(search)


def snaps(quarters: list[date], n: int = 101) -> dict:
    return {q.isoformat(): {"tickers": [f"S{i}" for i in range(n)]} for q in quarters}


ALL = search.quarter_starts(date(2015, 1, 1), date(2026, 10, 13))


def test_quarter_starts_cover_every_quarter():
    assert ALL[0] == date(2015, 1, 1) and ALL[-1] == date(2026, 10, 1)
    assert len(ALL) == 48
    assert search.quarter_starts(date(2015, 2, 15), date(2015, 10, 1)) == [
        date(2015, 4, 1),
        date(2015, 7, 1),
        date(2015, 10, 1),
    ]


def test_full_range_passes():
    assert search.check_membership(snaps(ALL)) == []


@pytest.mark.parametrize(
    "drop, expect",
    [
        ([date(2018, 4, 1)], "2018-04-01"),  # interior hole
        (ALL[-3:], "2026-04-01"),  # truncated tail
        (ALL[:2], "2015-01-01"),  # truncated head
    ],
)
def test_any_missing_quarter_fails(drop, expect):
    problems = search.check_membership(snaps([q for q in ALL if q not in drop]))
    assert any(expect in p for p in problems)


def test_implausible_member_count_fails():
    s = snaps(ALL)
    s[ALL[5].isoformat()]["tickers"] = s[ALL[5].isoformat()]["tickers"][:60]
    assert any("outside" in p for p in search.check_membership(s))


def test_run_refuses_when_report_exists(tmp_path, monkeypatch):
    out = tmp_path / "report.json"
    out.write_text("{}")
    monkeypatch.setattr(search, "OUT", out)
    monkeypatch.setattr("sys.argv", ["x", "--run"])
    with pytest.raises(SystemExit) as e:
        search.main()
    assert "ONE-SHOT" in str(e.value)
