"""Entry point: run all scrapers and merge output into data/all_sale.json."""

import json
import logging
import sys
import time
from pathlib import Path

# Allow running from project root without installing the package
sys.path.insert(0, str(Path(__file__).parent))

from scrapers import net_scraper, uniqlo_scraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"


def run_scraper(name: str, scraper_module, output_path: Path) -> tuple[list, float]:
    logger.info("=== Starting %s scraper ===", name)
    t0 = time.monotonic()
    products = scraper_module.scrape(output_path)
    elapsed = time.monotonic() - t0
    logger.info("=== %s done: %d items in %.1fs ===", name, len(products), elapsed)
    return products, elapsed


def main() -> None:
    total_start = time.monotonic()

    uniqlo_products, uniqlo_secs = run_scraper(
        "UNIQLO", uniqlo_scraper, DATA_DIR / "uniqlo_sale.json"
    )
    net_products, net_secs = run_scraper("NET", net_scraper, DATA_DIR / "net_sale.json")

    all_products = uniqlo_products + net_products
    all_path = DATA_DIR / "all_sale.json"
    all_path.write_text(
        json.dumps(all_products, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    total_secs = time.monotonic() - total_start
    print("\n" + "=" * 50)
    print("執行摘要")
    print("=" * 50)
    print(f"UNIQLO : {len(uniqlo_products):>4} 件  ({uniqlo_secs:.1f}s)")
    print(f"NET    : {len(net_products):>4} 件  ({net_secs:.1f}s)")
    print(f"合計   : {len(all_products):>4} 件  ({total_secs:.1f}s)")
    print(f"輸出   : {all_path}")
    print("=" * 50)


if __name__ == "__main__":
    main()
