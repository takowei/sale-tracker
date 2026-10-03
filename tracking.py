"""Watchlist price tracking + drop alerts for sale-tracker.

Upgrade per Root's request: after scraping, watch SPECIFIC items Root cares about
(keyword + optional target price) and raise an alert when they hit the target or
drop in price. Watchlist-scoped on purpose — alerting on all 300+ items is noise;
Root watches the things he actually wants.

Pipeline (called from run_scrapers.py after the merge, or run standalone on existing
data/all_sale.json):
  1. update_history  — append today's salePrice per product to data/price-history.json
  2. check_watchlist — match items to watchlist.json, flag at/below target + drops
  3. write data/alerts.json  (frontend shows these; also printed)

Delivery: writes alerts.json (UI reads it). True push (Telegram/phone) needs a
channel credential from Root — see deliver_note(). Logic works with zero external deps.
"""

from __future__ import annotations

import html
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DATA = Path(__file__).parent / "data"
WATCHLIST_FILE = Path(__file__).parent / "watchlist.json"
HISTORY_FILE = DATA / "price-history.json"
ALERTS_FILE = DATA / "alerts.json"
SENT_FILE = DATA / "alerts_sent.json"  # dedup state so we don't re-spam same item/price
TG_CONFIG = (
    Path(__file__).parent / "telegram_config.json"
)  # gitignored; {bot_token, chat_id}


def _key(item: dict) -> str:
    return item.get("productUrl") or f"{item.get('brand')}::{item.get('name')}"


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_watchlist() -> list[dict]:
    if not WATCHLIST_FILE.exists():
        return []
    try:
        wl = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
        return [w for w in wl if isinstance(w, dict) and w.get("keyword")]
    except (json.JSONDecodeError, OSError):
        return []


def update_history(items: list[dict]) -> dict:
    """Append today's salePrice for each item; one entry per product per day."""
    history: dict = {}
    if HISTORY_FILE.exists():
        try:
            history = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            history = {}
    today = _today()
    for it in items:
        k = _key(it)
        rec = history.setdefault(
            k, {"name": it.get("name"), "brand": it.get("brand"), "history": []}
        )
        rec["name"] = it.get("name")
        h = rec["history"]
        point = {
            "date": today,
            "salePrice": it.get("salePrice"),
            "discount": it.get("discount"),
        }
        if h and h[-1]["date"] == today:
            h[-1] = point  # overwrite same-day
        else:
            h.append(point)
    HISTORY_FILE.write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return history


def _prev_price(rec: dict, today: str) -> int | None:
    """Last recorded salePrice on a date before today."""
    for p in reversed(rec.get("history", [])):
        if p["date"] != today and isinstance(p.get("salePrice"), (int, float)):
            return p["salePrice"]
    return None


def check_watchlist(
    items: list[dict], history: dict, watchlist: list[dict]
) -> list[dict]:
    """Return alerts for watched items: at/below target price, and/or just dropped."""
    today = _today()
    alerts: list[dict] = []
    for it in items:
        name = (it.get("name") or "") + " " + (it.get("category") or "")
        sale = it.get("salePrice")
        for w in watchlist:
            kw = w["keyword"]
            if kw.lower() not in name.lower():
                continue
            max_price = w.get("max_price")
            reasons: list[str] = []
            at_target = isinstance(sale, (int, float)) and (
                max_price is None or sale <= max_price
            )
            if at_target:
                reasons.append(
                    f"達標：${sale}"
                    + (
                        f" ≤ 目標 ${max_price}"
                        if max_price is not None
                        else "（特價中）"
                    )
                )
            prev = _prev_price(history.get(_key(it), {}), today)
            if prev is not None and isinstance(sale, (int, float)) and sale < prev:
                reasons.append(f"降價：${prev} → ${sale} (省 ${prev - sale})")
            if reasons:
                alerts.append(
                    {
                        "keyword": kw,
                        "name": it.get("name"),
                        "brand": it.get("brand"),
                        "salePrice": sale,
                        "originalPrice": it.get("originalPrice"),
                        "discount": it.get("discount"),
                        "productUrl": it.get("productUrl"),
                        "imageUrl": it.get("imageUrl"),
                        "sizes": it.get("sizes") or [],
                        "reasons": reasons,
                        "date": today,
                    }
                )
    return alerts


def _load_telegram() -> tuple[str | None, str | None]:
    """Bot token + chat_id from env (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID) or
    telegram_config.json. Returns (None, None) if unconfigured → push is skipped."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if token and chat:
        return token, chat
    if TG_CONFIG.exists():
        try:
            cfg = json.loads(TG_CONFIG.read_text(encoding="utf-8"))
            return cfg.get("bot_token"), str(cfg.get("chat_id") or "") or None
        except (json.JSONDecodeError, OSError):
            pass
    return None, None


def _alert_key(a: dict) -> str:
    """Dedup key: product + its current sale price → re-notify only on a new drop."""
    return f"{a.get('productUrl')}@{a.get('salePrice')}"


def _load_sent() -> set[str]:
    if SENT_FILE.exists():
        try:
            return set(json.loads(SENT_FILE.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            return set()
    return set()


MAX_PUSH_PER_RUN = 30  # 超過的留到下一輪（未標記已送），避免一次洗版


def _telegram_call(token: str, method: str, payload: dict) -> bool:
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(payload).encode()
    with urllib.request.urlopen(url, data=data, timeout=15) as r:
        return r.status == 200


def _alert_caption(a: dict, idx: int, total: int) -> str:
    """一圖一則的說明文字（HTML）：序號、特價、原價、品牌＋名稱連結、尺寸、觸發原因。"""
    orig = a.get("originalPrice")
    price = f"<b>${a.get('salePrice')}</b>" + (f" <s>{orig}</s>" if orig else "")
    name = html.escape(a.get("name") or "")
    link = f'<a href="{html.escape(a.get("productUrl") or "")}">{name}</a>'
    sizes = "/".join(a.get("sizes") or []) or "-"
    reasons = html.escape("｜".join(a.get("reasons", [])))
    brand = (a.get("brand") or "").upper()
    return f"{idx}/{total}  {price} {brand}\n{link}\n{sizes}\n{reasons}"


def _send_alert(token: str, chat: str, caption: str, image_url: str | None) -> bool:
    """有圖發 sendPhoto，圖片打不開就退回純文字，確保每筆都送得出去。"""
    if image_url:
        try:
            return _telegram_call(
                token,
                "sendPhoto",
                {
                    "chat_id": chat,
                    "photo": image_url,
                    "caption": caption,
                    "parse_mode": "HTML",
                },
            )
        except Exception:  # noqa: BLE001 — 壞圖退回純文字
            pass
    return _telegram_call(
        token,
        "sendMessage",
        {
            "chat_id": chat,
            "text": caption,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true",
        },
    )


def notify_telegram(alerts: list[dict], pause: float = 1.2) -> int:
    """Push NEW alerts (not previously sent at this price) to Telegram, one photo per
    message. Returns sent count. No-op (returns 0) when unconfigured or nothing new."""
    token, chat = _load_telegram()
    sent = _load_sent()
    fresh_by_key = {_alert_key(a): a for a in alerts if _alert_key(a) not in sent}
    if not fresh_by_key:
        return 0
    if not (token and chat):
        return 0  # unconfigured: leave fresh unsent so they fire once token is added
    batch = list(fresh_by_key.items())[:MAX_PUSH_PER_RUN]
    delivered: set[str] = set()
    for idx, (key, a) in enumerate(batch, 1):
        try:
            if _send_alert(
                token, chat, _alert_caption(a, idx, len(batch)), a.get("imageUrl")
            ):
                delivered.add(key)
        except Exception as exc:  # noqa: BLE001 — best-effort notifier
            print(f"  ⚠️ Telegram 發送失敗：{exc}")
        if idx < len(batch):
            time.sleep(pause)
    if delivered:
        SENT_FILE.write_text(
            json.dumps(sorted(sent | delivered), ensure_ascii=False), encoding="utf-8"
        )
    return len(delivered)


def process(items: list[dict]) -> list[dict]:
    """Full pipeline: history + watchlist alerts + write alerts.json + Telegram push."""
    watchlist = load_watchlist()
    history = update_history(items)
    alerts = check_watchlist(items, history, watchlist) if watchlist else []
    ALERTS_FILE.write_text(
        json.dumps(
            {"updatedAt": datetime.now(timezone.utc).isoformat(), "alerts": alerts},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    if not watchlist:
        print(
            "\n⚠️ watchlist.json 是空的或不存在——加入你關注的關鍵字+目標價才會有警示。"
        )
        return alerts

    print(f"\n🔔 {len(alerts)} 筆關注警示 → data/alerts.json（前端 🔔 橫幅顯示）。")
    for a in alerts[:20]:
        print(f"  • [{a['brand']}] {a['name']}  | " + " | ".join(a["reasons"]))
    token, _ = _load_telegram()
    if token:
        n = notify_telegram(alerts)
        print(
            f"  → Telegram 推送 {n} 筆新警示。"
            if n
            else "  → 無新警示需推送（已去重）。"
        )
    else:
        print(
            "  → Telegram 未設定：填 telegram_config.json（bot_token + chat_id）即自動推播。"
        )
    return alerts


def main() -> None:
    all_path = DATA / "all_sale.json"
    if not all_path.exists():
        print("data/all_sale.json 不存在，先跑 run_scrapers.py")
        return
    items = json.loads(all_path.read_text(encoding="utf-8"))
    process(items)


if __name__ == "__main__":
    main()
