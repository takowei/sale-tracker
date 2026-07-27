#!/usr/bin/env bash
# cron_loop.sh — execution unit for sale-tracker's daily scrape.
#
# n8n (which was meant to own this schedule per n8n_workflow.json) is not
# installed on the deploy target, so this replaces it with the same
# sleep-loop pattern pricedrop's cron container uses: run once, sleep,
# repeat forever. Logs go straight to `docker compose logs scraper`.
#
# SCRAPE_INTERVAL_SECONDS defaults to 86400 (daily). Override in .env for
# testing (e.g. a short interval to see a second run without waiting a day).
set -euo pipefail

INTERVAL="${SCRAPE_INTERVAL_SECONDS:-86400}"

echo "[cron_loop] starting — scraping every ${INTERVAL}s"

while true; do
    echo "[cron_loop] $(date -u '+%Y-%m-%dT%H:%M:%SZ') running run_scrapers.py..."
    if ! python3 run_scrapers.py; then
        echo "[cron_loop] run_scrapers.py exited non-zero — will retry next interval" >&2
    fi
    sleep "$INTERVAL"
done
