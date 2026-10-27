import asyncio

from backend import db
from backend.routers import settings


def _run(monkeypatch, rows, **kwargs):
    calls = []

    def fake_exec(sql, params=None, **_):
        calls.append((sql, params))
        return rows

    monkeypatch.setattr(settings, "_load_pricing_settings", lambda: {"use_account_prices": True})
    monkeypatch.setattr(db, "execute_query", fake_exec)
    monkeypatch.setattr("backend.workspace_filter.get_configured_workspace_ids", lambda: [])
    return asyncio.run(settings.get_account_price_multiplier(**kwargs)), calls


def test_multiplier_is_weighted_by_requested_range_and_workspaces(monkeypatch):
    out, calls = _run(
        monkeypatch,
        [{"multiplier": 0.8, "sku_count": 3, "priced_sku_count": 5,
          "weighted_list_spend": 100, "weighted_account_spend": 80}],
        start_date="2026-09-01", end_date="2026-09-30", workspace_ids="111,222",
    )
    [(sql, params)] = calls
    assert params == {"start_date": "2026-09-01", "end_date": "2026-09-30"}
    assert "BETWEEN :start_date AND :end_date" in sql
    assert "IN ('111', '222')" in sql and "{workspace_filter}" not in sql
    # SKUs without a negotiated rate count at list rather than being dropped.
    assert "COALESCE(ap.account_price, lp.pricing.default)" in sql
    assert out["available"] is True
    assert out["discount_percent"] == 20.0
    assert out["sku_count"] == 3 and out["priced_sku_count"] == 5


def test_no_negotiated_rates_is_reported_unavailable(monkeypatch):
    out, _ = _run(monkeypatch, [{"multiplier": 1.0, "sku_count": 0}])
    assert out["available"] is False
    assert out["multiplier"] == 1.0
    assert "No negotiated rates" in out["message"]


def test_disabled_mode_skips_query(monkeypatch):
    monkeypatch.setattr(settings, "_load_pricing_settings", lambda: {"use_account_prices": False})
    monkeypatch.setattr(db, "execute_query", lambda *a, **k: (_ for _ in ()).throw(AssertionError("queried")))
    out = asyncio.run(settings.get_account_price_multiplier())
    assert out == {"multiplier": 1.0, "available": False, "sku_count": 0, "discount_percent": 0}
