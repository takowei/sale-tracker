#!/usr/bin/env bash
# deploy_sale_tracker_aws.sh — one-command setup of the clothing sale-tracker on
# the always-on AWS Tokyo box, so it scrapes daily and pushes Telegram alerts even
# when your PC is off (Option A).
#
# Run ONCE from your local machine (WSL):
#     export TELEGRAM_BOT_TOKEN='123456:ABC...'      # your bot (reuse 300forfree's is fine)
#     export TELEGRAM_CHAT_ID='your_chat_id'
#     bash deploy_sale_tracker_aws.sh
#
# The token flows local-env → box only; it is never printed, committed, or seen by
# the agent. Ships code via scp tarball (no git remote needed). Idempotent: re-run
# anytime (cron install + venv are safe to repeat). Edit watchlist.json to your real
# wants BEFORE running (or edit ~/sale-tracker/watchlist.json on the box later).
#
# Requires: sol-grid-trader.pem (same key as the trading box) in this dir or SSH_KEY env.
# shellcheck disable=SC2029,SC2087

set -euo pipefail
cd "$(dirname "$0")"

AWS_HOST="ubuntu@57.182.243.118"
SSH_KEY="${SSH_KEY:-sol-grid-trader.pem}"
REMOTE_DIR="/home/ubuntu/sale-tracker"
SCHEDULE="${SCHEDULE:-0 23 * * *}"  # 23:00 UTC = 07:00 Asia/Taipei, daily
SSH_OPTS=(-i "$SSH_KEY" -o StrictHostKeyChecking=no)

if [ ! -f "$SSH_KEY" ]; then
    echo "ERROR: SSH key '$SSH_KEY' not found. Put sol-grid-trader.pem here or set SSH_KEY." >&2
    exit 1
fi

echo "=== sale-tracker AWS deploy — $(date -u) ==="

echo "[1/6] Pack project (excluding junk)..."
TARBALL="$(mktemp /tmp/sale-tracker.XXXXXX.tgz)"
tar --exclude='./.git' --exclude='./data' --exclude='./.pylibs' \
    --exclude='./__pycache__' --exclude='./scrapers/__pycache__' \
    --exclude='./.ruff_cache' --exclude='./telegram_config.json' \
    -czf "$TARBALL" -C . .

echo "[2/6] Ship code to box:$REMOTE_DIR ..."
ssh "${SSH_OPTS[@]}" "$AWS_HOST" "mkdir -p $REMOTE_DIR"
scp "${SSH_OPTS[@]}" "$TARBALL" "$AWS_HOST:$REMOTE_DIR/_deploy.tgz"
ssh "${SSH_OPTS[@]}" "$AWS_HOST" "cd $REMOTE_DIR && tar -xzf _deploy.tgz && rm -f _deploy.tgz"
rm -f "$TARBALL"

echo "[3/6] Write Telegram config on box (token from your local env; not logged)..."
if [ -n "${TELEGRAM_BOT_TOKEN:-}" ] && [ -n "${TELEGRAM_CHAT_ID:-}" ]; then
    TMP_CFG="$(mktemp /tmp/tgcfg.XXXXXX.json)"
    chmod 600 "$TMP_CFG"
    printf '{"bot_token":"%s","chat_id":"%s"}\n' \
        "$TELEGRAM_BOT_TOKEN" "$TELEGRAM_CHAT_ID" > "$TMP_CFG"
    scp "${SSH_OPTS[@]}" "$TMP_CFG" "$AWS_HOST:$REMOTE_DIR/telegram_config.json"
    rm -f "$TMP_CFG"
    echo "  telegram_config.json written on box."
else
    echo "  ⚠️ TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set in env — skipping."
    echo "     Alerts will compute but NOT push until you create"
    echo "     $REMOTE_DIR/telegram_config.json on the box (or re-run with the env vars)."
fi

echo "[4/6] Set up Python venv + scraper deps on box..."
ssh "${SSH_OPTS[@]}" "$AWS_HOST" "
    set -e
    cd $REMOTE_DIR
    python3 -m venv venv 2>/dev/null || true
    ./venv/bin/python -m pip install --quiet --upgrade pip
    ./venv/bin/python -m pip install --quiet requests beautifulsoup4 lxml
    echo '  deps installed.'
"

echo "[5/6] Install daily cron ($SCHEDULE UTC)..."
ssh "${SSH_OPTS[@]}" "$AWS_HOST" "
    set -e
    LINE='$SCHEDULE cd $REMOTE_DIR && ./venv/bin/python run_scrapers.py >> $REMOTE_DIR/data/cron.log 2>&1'
    ( crontab -l 2>/dev/null | grep -v 'sale-tracker/run_scrapers.py' ; echo \"\$LINE\" ) | crontab -
    echo '  cron set:'; crontab -l | grep sale-tracker || true
"

echo "[6/6] Verify one run now..."
ssh "${SSH_OPTS[@]}" "$AWS_HOST" "
    cd $REMOTE_DIR
    ./venv/bin/python run_scrapers.py 2>&1 | tail -15
    echo '--- alerts.json head ---'
    head -c 400 data/alerts.json 2>/dev/null || echo '(no alerts.json)'
"

echo ""
echo "=== Done. Box scrapes daily at '$SCHEDULE' UTC and pushes Telegram on new alerts. ==="
echo "  • Edit watchlist on box: ssh ... ; nano $REMOTE_DIR/watchlist.json   (then it applies next run)"
echo "  • Re-run this script anytime to update code."
