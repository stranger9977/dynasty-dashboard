"""Artifact writer: each analysis produces output/<slug>/{data.parquet, chart.png, findings.md}."""
from __future__ import annotations
from pathlib import Path
import pandas as pd

OUTPUT_ROOT = Path(__file__).resolve().parent.parent / "output"


def artifact_dir(slug: str) -> Path:
    d = OUTPUT_ROOT / slug
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_data(slug: str, df: pd.DataFrame, filename: str = "data.parquet") -> Path:
    p = artifact_dir(slug) / filename
    df.to_parquet(p, index=False)
    return p


def write_findings(slug: str, markdown: str) -> Path:
    p = artifact_dir(slug) / "findings.md"
    p.write_text(markdown)
    return p


def chart_path(slug: str, filename: str = "chart.png") -> Path:
    return artifact_dir(slug) / filename
