# tests/test_seed.py
import pandas as pd
from ingestion import seed

def test_ensure_copies_missing(tmp_path, monkeypatch):
    data = tmp_path / "data"; seed_dir = data / "seed"
    seed_dir.mkdir(parents=True)
    (seed_dir / "merged.parquet").write_bytes(b"x")  # sentinel
    monkeypatch.setattr(seed, "DATA_DIR", data)
    monkeypatch.setattr(seed, "SEED_DIR", seed_dir)
    monkeypatch.setattr(seed, "SEED_FILES", ["merged.parquet"])
    seed.ensure_data_from_seed()
    assert (data / "merged.parquet").exists()

def test_does_not_overwrite_existing(tmp_path, monkeypatch):
    data = tmp_path / "data"; seed_dir = data / "seed"
    seed_dir.mkdir(parents=True)
    (seed_dir / "merged.parquet").write_bytes(b"SEED")
    (data / "merged.parquet").write_bytes(b"LIVE")
    monkeypatch.setattr(seed, "DATA_DIR", data)
    monkeypatch.setattr(seed, "SEED_DIR", seed_dir)
    monkeypatch.setattr(seed, "SEED_FILES", ["merged.parquet"])
    seed.ensure_data_from_seed()
    assert (data / "merged.parquet").read_bytes() == b"LIVE"  # unchanged

def test_projections_in_seed_files():
    from ingestion.seed import SEED_FILES
    assert "projections.parquet" in SEED_FILES
