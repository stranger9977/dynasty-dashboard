"""Pydantic models for extracted guide data."""
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict


Position = Literal["WR", "RB", "TE", "QB"]


class GuidePlayer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guide_year: int = Field(ge=2022, le=2026)
    name: str = Field(min_length=2, max_length=80)
    position: Position
    original_tier_label: str = Field(min_length=1, max_length=80)
    # None allowed: e.g. 2022's "Z-Prospect Ranked" players who appear in the
    # secondary cheatsheet without a primary tier rank.
    original_tier_rank: int | None = Field(default=None, ge=1, le=20)
    overall_rank: int | None = Field(default=None, ge=1, le=500)
    # Empty allowed: TEs/QBs in some guides appear only in the rankings
    # cheatsheet without a profile that lists their college.
    college: str = Field(default="", max_length=80)
    blurb: str = Field(default="", max_length=500)
    source_page: int = Field(ge=1, le=500)
    source_quote: str = Field(min_length=1, max_length=120)


class GuideMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    guide_year: int = Field(ge=2022, le=2026)
    version: str
    methodology_text: str
    features_mentioned: list[str]
    tier_definitions: dict[str, str]
