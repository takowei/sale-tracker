"""Tests for sale-tracker parsing and tracking logic.

All tests are fully offline:
- No real HTTP requests (requests.post/get mocked at module level)
- No real filesystem side-effects outside pytest's tmp_path fixture
- HTML/JSON fixtures are defined inline
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# uniqlo_scraper — pure-logic helpers
# ---------------------------------------------------------------------------


def test_build_payload_structure():
    from scrapers.uniqlo_scraper import _build_payload

    payload = _build_payload("feature-sale-men", page=3)

    assert payload["categoryCode"] == "feature-sale-men"
    assert payload["pageInfo"]["page"] == 3
    assert payload["pageInfo"]["pageSize"] == 24
    assert payload["stockFilter"] == "warehouse"
    assert payload["color"] == []


def test_build_payload_page_1():
    from scrapers.uniqlo_scraper import _build_payload

    payload = _build_payload("any-code", page=1)
    assert payload["pageInfo"]["page"] == 1


def test_parse_colors_strips_code_prefix():
    from scrapers.uniqlo_scraper import _parse_colors

    result = _parse_colors(["00 WHITE", "09 BLACK", "15 RED"])
    assert result == ["WHITE", "BLACK", "RED"]


def test_parse_colors_entry_without_space_kept_as_is():
    from scrapers.uniqlo_scraper import _parse_colors

    result = _parse_colors(["BLUE", "00 WHITE"])
    assert result == ["BLUE", "WHITE"]


def test_parse_colors_empty_list():
    from scrapers.uniqlo_scraper import _parse_colors

    assert _parse_colors([]) == []


def test_parse_product_basic_fields():
    from scrapers.uniqlo_scraper import _parse_product

    raw: dict[str, Any] = {
        "productCode": "123456",
        "name": "Ultra Light Down",
        "originPrice": 1990,
        "minPrice": 990,
        "size": ["SMA003", "SMA004", "SMA005"],
        "styleText": ["00 WHITE", "09 BLACK"],
        "mainPic": "/hmall/test/p1.jpg",
    }
    result = _parse_product(raw, "男裝特價", "2026-06-20T00:00:00Z")

    assert result["brand"] == "uniqlo"
    assert result["name"] == "Ultra Light Down"
    assert result["originalPrice"] == 1990
    assert result["salePrice"] == 990
    assert result["discount"] == 50  # (1 - 990/1990) * 100 rounded ≈ 50
    assert result["sizes"] == ["S", "M", "L"]
    assert result["colors"] == ["WHITE", "BLACK"]
    assert result["category"] == "男裝特價"
    assert result["scrapedAt"] == "2026-06-20T00:00:00Z"
    # mainPic test/ → / replacement
    assert "test" not in result["imageUrl"]
    assert result["imageUrl"].startswith("https://www.uniqlo.com")


def test_parse_product_zero_price_gives_zero_discount():
    from scrapers.uniqlo_scraper import _parse_product

    raw: dict[str, Any] = {
        "productCode": "X",
        "name": "Freebie",
        "originPrice": 0,
        "minPrice": 0,
        "size": [],
        "styleText": [],
        "mainPic": "",
    }
    result = _parse_product(raw, "test", "2026-06-20T00:00:00Z")
    assert result["discount"] == 0


def test_parse_product_url_contains_product_code():
    from scrapers.uniqlo_scraper import _parse_product

    raw: dict[str, Any] = {
        "productCode": "U0000123",
        "name": "Shirt",
        "originPrice": 790,
        "minPrice": 590,
        "size": [],
        "styleText": [],
        "mainPic": "/hmall/p.jpg",
    }
    result = _parse_product(raw, "label", "2026-06-20T00:00:00Z")
    assert "U0000123" in result["productUrl"]


def test_parse_product_unknown_size_code_passed_through():
    from scrapers.uniqlo_scraper import _parse_product

    raw: dict[str, Any] = {
        "productCode": "Y",
        "name": "Pants",
        "originPrice": 990,
        "minPrice": 790,
        "size": ["INS031", "UNKNOWN_CODE"],
        "styleText": [],
        "mainPic": "",
    }
    result = _parse_product(raw, "label", "2026-06-20T00:00:00Z")
    assert "31inch" in result["sizes"]
    assert "UNKNOWN_CODE" in result["sizes"]


# ---------------------------------------------------------------------------
# tracking.py — update_history
# ---------------------------------------------------------------------------


def test_update_history_creates_new_entry(tmp_path: Path):
    from tracking import update_history

    items = [
        {
            "productUrl": "https://example.com/p/001",
            "name": "Test Shirt",
            "brand": "uniqlo",
            "salePrice": 590,
            "discount": 30,
        }
    ]

    history_file = tmp_path / "price-history.json"

    with (
        patch("tracking.HISTORY_FILE", history_file),
        patch("tracking.DATA", tmp_path),
    ):
        history = update_history(items)

    key = "https://example.com/p/001"
    assert key in history
    assert history[key]["name"] == "Test Shirt"
    assert len(history[key]["history"]) == 1
    assert history[key]["history"][0]["salePrice"] == 590


def test_update_history_overwrites_same_day(tmp_path: Path):
    from tracking import update_history

    history_file = tmp_path / "price-history.json"

    items = [
        {
            "productUrl": "https://example.com/p/002",
            "name": "Pants",
            "brand": "uniqlo",
            "salePrice": 700,
            "discount": 20,
        }
    ]

    with (
        patch("tracking.HISTORY_FILE", history_file),
        patch("tracking.DATA", tmp_path),
    ):
        update_history(items)
        items[0]["salePrice"] = 650
        history = update_history(items)

    key = "https://example.com/p/002"
    # Same-day calls must not create duplicate entries
    assert len(history[key]["history"]) == 1
    assert history[key]["history"][0]["salePrice"] == 650


def test_update_history_appends_on_different_days(tmp_path: Path):
    from tracking import update_history

    history_file = tmp_path / "price-history.json"
    key = "https://example.com/p/003"

    # Seed a prior-day entry directly
    seed = {
        key: {
            "name": "Jacket",
            "brand": "uniqlo",
            "history": [{"date": "2026-06-19", "salePrice": 1200, "discount": 10}],
        }
    }
    history_file.write_text(json.dumps(seed), encoding="utf-8")

    items = [
        {
            "productUrl": key,
            "name": "Jacket",
            "brand": "uniqlo",
            "salePrice": 990,
            "discount": 25,
        }
    ]

    with (
        patch("tracking.HISTORY_FILE", history_file),
        patch("tracking.DATA", tmp_path),
        patch("tracking._today", return_value="2026-06-20"),
    ):
        history = update_history(items)

    assert len(history[key]["history"]) == 2
    assert history[key]["history"][-1]["salePrice"] == 990


# ---------------------------------------------------------------------------
# tracking.py — check_watchlist
# ---------------------------------------------------------------------------


def _make_item(
    name: str,
    category: str = "男裝特價",
    sale: int = 590,
    original: int = 990,
    url: str = "https://example.com/p/w",
) -> dict:
    return {
        "name": name,
        "category": category,
        "salePrice": sale,
        "originalPrice": original,
        "discount": round((1 - sale / original) * 100),
        "productUrl": url,
        "brand": "uniqlo",
        "imageUrl": "",
    }


def test_check_watchlist_match_at_target():
    from tracking import check_watchlist

    items = [_make_item("束口褲 A", sale=799)]
    watchlist = [{"keyword": "束口褲", "max_price": 800}]
    history = {}

    alerts = check_watchlist(items, history, watchlist)

    assert len(alerts) == 1
    assert alerts[0]["keyword"] == "束口褲"
    assert "達標" in alerts[0]["reasons"][0]


def test_check_watchlist_no_match_above_target():
    from tracking import check_watchlist

    items = [_make_item("束口褲 B", sale=900)]
    watchlist = [{"keyword": "束口褲", "max_price": 800}]
    history = {}

    alerts = check_watchlist(items, history, watchlist)
    assert alerts == []


def test_check_watchlist_null_max_price_always_matches():
    from tracking import check_watchlist

    items = [_make_item("T恤", sale=490)]
    watchlist = [{"keyword": "T恤", "max_price": None}]
    history = {}

    alerts = check_watchlist(items, history, watchlist)
    assert len(alerts) == 1
    assert "特價中" in alerts[0]["reasons"][0]


def test_check_watchlist_price_drop_detected():
    from tracking import check_watchlist

    key = "https://example.com/p/drop"
    items = [_make_item("外套 Drop", sale=790, url=key)]
    watchlist = [{"keyword": "外套", "max_price": None}]
    history = {
        key: {
            "name": "外套 Drop",
            "brand": "uniqlo",
            "history": [{"date": "2026-06-19", "salePrice": 990, "discount": 0}],
        }
    }

    with patch("tracking._today", return_value="2026-06-20"):
        alerts = check_watchlist(items, history, watchlist)

    reasons_flat = " ".join(alerts[0]["reasons"])
    assert "降價" in reasons_flat


def test_check_watchlist_keyword_case_insensitive():
    from tracking import check_watchlist

    items = [_make_item("Ultra Light Jacket", sale=590, category="男裝")]
    watchlist = [{"keyword": "jacket", "max_price": None}]
    history = {}

    alerts = check_watchlist(items, history, watchlist)
    assert len(alerts) == 1


def test_check_watchlist_empty_watchlist_returns_empty():
    from tracking import check_watchlist

    items = [_make_item("外套")]
    alerts = check_watchlist(items, {}, [])
    assert alerts == []


# ---------------------------------------------------------------------------
# tracking.py — notify_telegram dedup logic
# ---------------------------------------------------------------------------


def test_notify_telegram_skips_already_sent(tmp_path: Path):
    """Alerts already in SENT_FILE are not re-sent."""
    from tracking import notify_telegram

    alert = {
        "productUrl": "https://example.com/p/001",
        "salePrice": 590,
        "brand": "uniqlo",
        "name": "Test",
        "reasons": ["達標：$590"],
    }
    # Pre-populate SENT_FILE with this alert's key
    sent_key = f"{alert['productUrl']}@{alert['salePrice']}"
    sent_file = tmp_path / "alerts_sent.json"
    sent_file.write_text(json.dumps([sent_key]), encoding="utf-8")

    with (
        patch("tracking.SENT_FILE", sent_file),
        patch("tracking._load_telegram", return_value=("fake-token", "12345")),
    ):
        count = notify_telegram([alert])

    assert count == 0  # already sent → skip, no HTTP call made


def test_notify_telegram_no_op_when_unconfigured(tmp_path: Path):
    """Returns 0 without making HTTP calls when token/chat are absent."""
    from tracking import notify_telegram

    alert = {
        "productUrl": "https://example.com/p/002",
        "salePrice": 399,
        "brand": "uniqlo",
        "name": "Shorts",
        "reasons": ["達標：$399"],
    }
    sent_file = tmp_path / "alerts_sent.json"

    with (
        patch("tracking.SENT_FILE", sent_file),
        patch("tracking._load_telegram", return_value=(None, None)),
    ):
        count = notify_telegram([alert])

    assert count == 0


def test_notify_telegram_sends_fresh_alerts(tmp_path: Path):
    """Fresh alerts that are not in SENT_FILE trigger an HTTP call."""
    from tracking import notify_telegram

    alert = {
        "productUrl": "https://example.com/p/003",
        "salePrice": 299,
        "brand": "uniqlo",
        "name": "Belt",
        "reasons": ["降價：$399 → $299 (省 $100)"],
    }
    sent_file = tmp_path / "alerts_sent.json"

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.__enter__ = lambda s: s
    mock_response.__exit__ = MagicMock(return_value=False)

    with (
        patch("tracking.SENT_FILE", sent_file),
        patch("tracking._load_telegram", return_value=("tok", "999")),
        patch("urllib.request.urlopen", return_value=mock_response),
    ):
        count = notify_telegram([alert])

    assert count == 1
    # After sending, the key must be persisted to SENT_FILE
    saved = json.loads(sent_file.read_text(encoding="utf-8"))
    assert f"{alert['productUrl']}@{alert['salePrice']}" in saved


def test_notify_telegram_empty_alerts_returns_zero(tmp_path: Path):
    from tracking import notify_telegram

    sent_file = tmp_path / "alerts_sent.json"
    with (
        patch("tracking.SENT_FILE", sent_file),
        patch("tracking._load_telegram", return_value=("tok", "999")),
    ):
        count = notify_telegram([])

    assert count == 0
