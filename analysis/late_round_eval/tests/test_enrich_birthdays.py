import json
import pandas as pd
import pytest

from analysis.late_round_eval.extraction.enrich_birthdays import (
    lookup_sleeper_birthday,
    enrich_with_birthdays,
)


SLEEPER_FIXTURE = {
    "1234": {"full_name": "Ladd McConkey", "position": "WR", "birth_date": "2001-11-02"},
    "5678": {"full_name": "Bijan Robinson", "position": "RB", "birth_date": "2002-01-30"},
    "9999": {"full_name": "Ja'Marr Chase", "position": "WR", "birth_date": "2000-03-01"},
}


def test_lookup_sleeper_birthday_exact():
    assert lookup_sleeper_birthday("Ladd McConkey", "WR", SLEEPER_FIXTURE) == "2001-11-02"


def test_lookup_sleeper_birthday_apostrophe():
    # Match Jamar Chase (no apostrophe) to Ja'Marr Chase
    assert lookup_sleeper_birthday("Jamar Chase", "WR", SLEEPER_FIXTURE) == "2000-03-01"


def test_lookup_sleeper_birthday_missing():
    assert lookup_sleeper_birthday("Fake Person", "WR", SLEEPER_FIXTURE) is None


def test_enrich_with_birthdays_flags_conflict():
    rows = pd.DataFrame([
        {"name": "Ladd McConkey", "position": "WR", "guide_year": 2024},
    ])
    sleeper = SLEEPER_FIXTURE
    nfl_birthdays = pd.DataFrame([
        {"name": "Ladd McConkey", "position": "WR", "birth_date": "1999-01-01"},  # conflict
    ])
    enriched = enrich_with_birthdays(rows, sleeper, nfl_birthdays)
    assert enriched.loc[0, "birthday_conflict"] is True
    # When conflict, birthday is set to None
    assert pd.isna(enriched.loc[0, "birthday"])


def test_enrich_with_birthdays_agreement():
    rows = pd.DataFrame([
        {"name": "Ladd McConkey", "position": "WR", "guide_year": 2024},
    ])
    nfl_birthdays = pd.DataFrame([
        {"name": "Ladd McConkey", "position": "WR", "birth_date": "2001-11-02"},
    ])
    enriched = enrich_with_birthdays(rows, SLEEPER_FIXTURE, nfl_birthdays)
    assert enriched.loc[0, "birthday"] == "2001-11-02"
    assert enriched.loc[0, "birthday_conflict"] is False
