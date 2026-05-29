import pandas as pd
import views.draft_wizard as dw


def test_available_removes_taken_by_name(monkeypatch):
    rookies = pd.DataFrame([
        {"name": "Jeremiyah Love", "position": "RB", "sleeper_id": "1"},
        {"name": "Carnell Tate", "position": "WR", "sleeper_id": "2"},
    ])
    monkeypatch.setattr(
        "ingestion.sleeper.get_draft_picks",
        lambda draft_id: [{"player_id": "999", "metadata": {"first_name": "Jeremiyah", "last_name": "Love"}}],
    )
    out = dw._available_after_live_picks(rookies, "draftX")
    assert list(out["name"]) == ["Carnell Tate"]


def test_available_removes_taken_by_sleeper_id(monkeypatch):
    rookies = pd.DataFrame([
        {"name": "A", "position": "RB", "sleeper_id": "1"},
        {"name": "B", "position": "WR", "sleeper_id": "2"},
    ])
    monkeypatch.setattr("ingestion.sleeper.get_draft_picks",
                        lambda draft_id: [{"player_id": "2", "metadata": {}}])
    out = dw._available_after_live_picks(rookies, "draftX")
    assert list(out["name"]) == ["A"]
