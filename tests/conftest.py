import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from storage import StorageManager


@pytest.fixture
def tmp_db(monkeypatch, tmp_path):
    """提供一个临时 StorageManager，测试结束自动清理。"""
    monkeypatch.setattr(
        StorageManager,
        "get_real_executable_path",
        lambda self: str(tmp_path),
    )
    sm = StorageManager()
    yield sm
    try:
        sm.conn.close()
    except Exception:
        pass
