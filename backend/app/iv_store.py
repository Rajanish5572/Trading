"""
Tiny local append-only store for daily ATM IV, so the analytics tab can show
an IV percentile.

Important limitation, flagged here rather than hidden: Arrow's API does not
expose historical IV. A proper IV percentile needs ~1 year of daily IV
samples. This store starts empty and grows by one sample per underlying per
calendar day as the app is used -- the percentile will only become
statistically meaningful after months of runtime, or after you backfill it
yourself (see backfill() below) from an external historical IV source.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

_STORE_PATH = Path(__file__).resolve().parent.parent / "data" / "iv_history.json"


def _load() -> dict[str, list[dict]]:
    if not _STORE_PATH.exists():
        return {}
    try:
        return json.loads(_STORE_PATH.read_text())
    except Exception:
        return {}


def _save(data: dict[str, list[dict]]) -> None:
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _STORE_PATH.write_text(json.dumps(data, indent=2))


def record_and_get_percentile(underlying: str, current_iv: float) -> dict:
    data = _load()
    history = data.setdefault(underlying, [])
    today = date.today().isoformat()

    if not history or history[-1]["date"] != today:
        history.append({"date": today, "iv": current_iv})
        _save(data)

    samples = [h["iv"] for h in history]
    percentile = round(100 * sum(1 for v in samples if v <= current_iv) / len(samples), 1)
    return {
        "current_iv": current_iv,
        "percentile": percentile,
        "sample_count": len(samples),
        "reliable": len(samples) >= 60,  # rule of thumb: ~3 months before this means much
    }


def backfill(underlying: str, samples: list[dict]) -> None:
    """samples: [{"date": "2025-01-01", "iv": 14.2}, ...] from an external source."""
    data = _load()
    existing = {h["date"] for h in data.get(underlying, [])}
    data.setdefault(underlying, []).extend(s for s in samples if s["date"] not in existing)
    data[underlying].sort(key=lambda h: h["date"])
    _save(data)
