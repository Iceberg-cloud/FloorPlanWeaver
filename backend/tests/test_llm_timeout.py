import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.llm_client import clamp_llm_timeout


def test_clamp_llm_timeout_respects_hard_cap(monkeypatch):
    from app.core import config as cfg

    monkeypatch.setattr(cfg.settings, "llm_hard_timeout_seconds", 120)
    assert clamp_llm_timeout(180) == 120
    assert clamp_llm_timeout(60) == 60
    assert clamp_llm_timeout(None) == 120


def test_urlopen_accepts_single_timeout():
    from urllib import request

    req = request.Request("http://127.0.0.1:9", method="GET")
    try:
        request.urlopen(req, timeout=5)
    except Exception as exc:
        assert "tuple" not in str(exc).lower()
        assert type(exc).__name__ in ("URLError", "HTTPError", "ConnectionRefusedError", "RemoteDisconnected", "TimeoutError")
