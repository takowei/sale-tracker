"""UNIQLO Taiwan sale scraper.

Fetches sale products from two categories:
- feature-sale-men  (男裝特價)
- feature-sale-men-ut  (UT 印花T恤特價)
"""

import json
import logging
import math
import time
from datetime import timezone, datetime
from pathlib import Path
from typing import Any

import requests

logger = logging.getLogger(__name__)

API_URL = "https://d.uniqlo.com/tw/p/search/products/by-category"

HEADERS = {
    "accept": "application/json",
    "accept-language": "zh-TW,zh;q=0.9",
    "content-type": "application/json; charset=utf-8",
    "langcode": "zh_TW",
    "origin": "https://www.uniqlo.com",
    "referer": "https://www.uniqlo.com/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/149.0.0.0 Safari/537.36"
    ),
    "sec-ch-ua": '"Google Chrome";v="149", "Chromium";v="149", "Not)A;Brand";v="24"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "same-site",
}

SIZE_MAP: dict[str, str] = {
    "SMA002": "XS",
    "SMA003": "S",
    "SMA004": "M",
    "SMA005": "L",
    "SMA006": "XL",
    "SMA007": "XXL",
    "SMA008": "3XL",
    "SMA009": "4XL",
    "INS028": "28inch",
    "INS029": "29inch",
    "INS031": "31inch",
    "INS032": "32inch",
    "INS033": "33inch",
    "INS034": "34inch",
}

CATEGORIES: list[tuple[str, str]] = [
    ("feature-sale-men", "男裝特價"),
    ("feature-sale-men-ut", "UT 印花T恤特價"),
]

PAGE_SIZE = 24
REQUEST_INTERVAL = 0.75  # seconds between requests


def _build_payload(category_code: str, page: int) -> dict[str, Any]:
    return {
        "pageInfo": {"page": page, "pageSize": PAGE_SIZE},
        "belongTo": "pc",
        "rank": "overall",
        "priceRange": {"low": 0, "high": 0},
        "categoryCode": category_code,
        "color": [],
        "description": "",
        "exist": [],
        "identity": [],
        "size": [],
        "stockFilter": "warehouse",
        "searchFlag": False,
    }


def _parse_colors(style_text: list[str]) -> list[str]:
    """Strip leading colour-code tokens (e.g. '00 WHITE' → 'WHITE')."""
    result = []
    for entry in style_text:
        if " " in entry:
            result.append(entry.split(" ", 1)[1])
        else:
            result.append(entry)
    return result


def _parse_product(
    raw: dict[str, Any], category_label: str, scraped_at: str
) -> dict[str, Any]:
    product_code = raw.get("productCode", raw.get("code", ""))
    original_price = int(raw.get("originPrice", 0))
    sale_price = int(raw.get("minPrice", raw.get("originPrice", 0)))
    discount = (
        round((1 - sale_price / original_price) * 100) if original_price > 0 else 0
    )

    sizes = [SIZE_MAP.get(s, s) for s in raw.get("size", [])]
    colors = _parse_colors(raw.get("styleText", []))

    main_pic = raw.get("mainPic", "").replace("/hmall/test/", "/hmall/")
    image_url = f"https://www.uniqlo.com{main_pic}" if main_pic else ""
    product_url = f"https://www.uniqlo.com/tw/zh_TW/product-detail.html?productCode={product_code}"

    return {
        "brand": "uniqlo",
        "category": category_label,
        "name": raw.get("name", ""),
        "originalPrice": original_price,
        "salePrice": sale_price,
        "discount": discount,
        "sizes": sizes,
        "colors": colors,
        "imageUrl": image_url,
        "productUrl": product_url,
        "scrapedAt": scraped_at,
    }


def _fetch_page(category_code: str, page: int) -> tuple[list[dict], int]:
    """Return (product_list, total_count) for one page. Returns ([], 0) on error."""
    payload = _build_payload(category_code, page)
    try:
        resp = requests.post(API_URL, headers=HEADERS, json=payload, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Request failed for %s page %d: %s", category_code, page, exc)
        return [], 0

    try:
        data = resp.json()
        resp_body = data["resp"][0]
        total = int(resp_body.get("productSum", 0))
        products = resp_body.get("productList", [])
        return products, total
    except (KeyError, IndexError, ValueError) as exc:
        logger.warning("Parse error for %s page %d: %s", category_code, page, exc)
        return [], 0


def scrape_category(category_code: str, category_label: str) -> list[dict[str, Any]]:
    """Scrape all pages for one category and return normalised product dicts."""
    scraped_at = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    results: list[dict[str, Any]] = []

    # First page also reveals total count
    raw_products, total = _fetch_page(category_code, page=1)
    if total == 0 and not raw_products:
        logger.warning("No products found for category %s", category_code)
        return results

    for raw in raw_products:
        results.append(_parse_product(raw, category_label, scraped_at))

    total_pages = math.ceil(total / PAGE_SIZE)
    logger.info(
        "[uniqlo] %s: %d products, %d pages", category_label, total, total_pages
    )

    for page in range(2, total_pages + 1):
        time.sleep(REQUEST_INTERVAL)
        raw_products, _ = _fetch_page(category_code, page)
        for raw in raw_products:
            results.append(_parse_product(raw, category_label, scraped_at))
        logger.info(
            "[uniqlo] %s: fetched page %d/%d", category_label, page, total_pages
        )

    return results


def scrape(output_path: Path) -> list[dict[str, Any]]:
    """Run scraper for all configured categories and write JSON to *output_path*."""
    all_products: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    for code, label in CATEGORIES:
        products = scrape_category(code, label)
        logger.info("[uniqlo] %s: collected %d items", label, len(products))
        for p in products:
            if p["productUrl"] not in seen_urls:
                seen_urls.add(p["productUrl"])
                all_products.append(p)
        time.sleep(REQUEST_INTERVAL)

    logger.info("[uniqlo] after dedup: %d unique products", len(all_products))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(all_products, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info("[uniqlo] wrote %d products to %s", len(all_products), output_path)
    return all_products
