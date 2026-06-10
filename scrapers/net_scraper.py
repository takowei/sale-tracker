"""NET Taiwan sale scraper.

Strategy:
1. Load the main promotion hub page (promotion/658) to discover all
   men's promotion IDs (category == 2 in the embedded promotions dict).
2. For each promotion ID, fetch its page and extract the embedded
   `promotionProducts` JSON array.
3. Each entry in that array already contains original price (fake_price),
   promotion price (promotion_price), sizes, colours, and image URL.
   Products where promotion_price == fake_price are not on sale and are
   skipped.
"""

import json
import logging
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

HUB_URL = "https://www.net-fashion.net/promotion/658"
PROMOTION_BASE = "https://www.net-fashion.net/promotion/"
MEN_CATEGORY_ID = 2

HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"),
    "Accept-Language": "zh-TW,zh;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

REQUEST_INTERVAL = 0.75  # seconds between requests


def _get_soup(url: str) -> BeautifulSoup | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except requests.RequestException as exc:
        logger.warning("Request failed for %s: %s", url, exc)
        return None


def _extract_promotions_map(soup: BeautifulSoup) -> dict[int, list[dict]]:
    """Return the promotions dict embedded in the page's Vue script."""
    for script in soup.find_all("script"):
        text = script.string or ""
        if "promotions:" not in text:
            continue
        m = re.search(r"promotions:\s*(\{.*?\})\s*,\s*\n\s*\w+:", text, re.DOTALL)
        if not m:
            continue
        try:
            raw: dict[str, list] = json.loads(m.group(1))
            return {int(k): v for k, v in raw.items() if k.isdigit()}
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning("Failed to parse promotions map: %s", exc)
    return {}


def _extract_promotion_name(soup: BeautifulSoup) -> str:
    """Extract the promotion name from the getPromotionData definition block.

    The target script looks like:
        var getPromotionData = function(key) { var data = { id: '...', name: "...", ... }
    We only match the script that *defines* the function, not scripts that call it.
    """
    for script in soup.find_all("script"):
        text = script.string or ""
        if "var getPromotionData" not in text:
            continue
        m = re.search(r"name:\s*\"([^\"]+)\"", text)
        if m:
            try:
                return json.loads(f'"{m.group(1)}"')
            except json.JSONDecodeError:
                return m.group(1)
    return "男裝特價"


def _extract_products(soup: BeautifulSoup) -> list[dict]:
    """Extract promotionProducts JSON array embedded in the page script."""
    for script in soup.find_all("script"):
        text = script.string or ""
        if "promotionProducts" not in text:
            continue
        idx = text.find("promotionProducts: [")
        if idx == -1:
            continue
        idx += len("promotionProducts: ")
        try:
            decoder = json.JSONDecoder()
            products, _ = decoder.raw_decode(text, idx)
            return products
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse promotionProducts: %s", exc)
    return []


def _is_on_sale(product: dict) -> bool:
    """Return True when promotion_price is strictly lower than fake_price."""
    try:
        original = float(product.get("fake_price", 0))
        promo = float(product.get("promotion_price", original))
        return promo < original
    except (TypeError, ValueError):
        return False


def _parse_product(
    raw: dict[str, Any],
    category_label: str,
    scraped_at: str,
    promotion_url: str,
) -> dict[str, Any]:
    original_price = int(float(raw.get("fake_price", 0)))
    sale_price = int(float(raw.get("promotion_price", original_price)))
    discount = (
        round((1 - sale_price / original_price) * 100) if original_price > 0 else 0
    )

    sizes_raw = raw.get("sizes", [])
    # Collect unique sizes in order of appearance
    seen_sizes: list[str] = []
    for s in sizes_raw:
        size_val = s.get("size", "")
        if size_val and size_val not in seen_sizes:
            seen_sizes.append(size_val)

    # Collect unique colours in order of appearance
    seen_colors: list[str] = []
    for s in sizes_raw:
        color_raw = s.get("color", "")
        # colour field is like "003米白" – strip leading digits
        color_name = re.sub(r"^\d+", "", color_raw).strip()
        if color_name and color_name not in seen_colors:
            seen_colors.append(color_name)

    image_url = raw.get("image400", {}).get("file_name", "")

    return {
        "brand": "net",
        "id": str(raw.get("parent_id", "")),
        "category": category_label,
        "name": raw.get("name", ""),
        "originalPrice": original_price,
        "salePrice": sale_price,
        "discount": discount,
        "sizes": seen_sizes,
        "colors": seen_colors,
        "imageUrl": image_url,
        "productUrl": promotion_url,
        "scrapedAt": scraped_at,
    }


def _scrape_promotion(promotion_id: int, scraped_at: str) -> list[dict[str, Any]]:
    url = f"{PROMOTION_BASE}{promotion_id}"
    soup = _get_soup(url)
    if soup is None:
        return []

    category_label = _extract_promotion_name(soup)
    raw_products = _extract_products(soup)

    results = []
    # De-duplicate by parent_id (each parent_id = one product group / colour variant)
    seen_parents: set[str] = set()
    for raw in raw_products:
        parent_id = str(raw.get("parent_id", ""))
        if parent_id in seen_parents:
            continue
        seen_parents.add(parent_id)
        if not _is_on_sale(raw):
            continue
        results.append(_parse_product(raw, category_label, scraped_at, url))

    logger.info(
        "[net] promotion %d (%s): %d on-sale items",
        promotion_id,
        category_label,
        len(results),
    )
    return results


def scrape(output_path: Path) -> list[dict[str, Any]]:
    """Discover men's promotions and scrape all sale products."""
    scraped_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    hub_soup = _get_soup(HUB_URL)
    if hub_soup is None:
        logger.error("[net] Failed to load hub page %s", HUB_URL)
        return []

    promotions_map = _extract_promotions_map(hub_soup)
    men_promotions = promotions_map.get(MEN_CATEGORY_ID, [])
    logger.info("[net] Found %d men's promotions", len(men_promotions))

    all_products: list[dict[str, Any]] = []
    for entry in men_promotions:
        promo_id = int(entry["id"])
        products = _scrape_promotion(promo_id, scraped_at)
        all_products.extend(products)
        time.sleep(REQUEST_INTERVAL)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(all_products, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("[net] wrote %d products to %s", len(all_products), output_path)
    return all_products
