"""Tests for app.tools.fs_scan."""
from pathlib import Path

import pytest

from app.tools.fs_scan import scan_uploads


def test_scan_uploads_empty_dir(tmp_path: Path) -> None:
    assert scan_uploads(tmp_path) == []


def test_scan_uploads_lists_files(tmp_path: Path) -> None:
    (tmp_path / "a.pdf").write_text("x")
    (tmp_path / "sub" / "b.pdf").mkdir(parents=True)
    (tmp_path / "sub" / "b.pdf").write_text("y")
    paths = scan_uploads(tmp_path)
    assert len(paths) == 2
    assert any("a.pdf" in p for p in paths)
    assert any("b.pdf" in p for p in paths)
