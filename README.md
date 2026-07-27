# Sale Tracker — 服飾特價追蹤與價格警示

每日自動爬取品牌特價、追蹤每件商品的價格歷史，並對「使用者關注的商品達標或降價」主動推播 Telegram。一個從**資料爬取 → 管線 → 前端 → 自動化部署**的完整全端小系統。

## 功能

| 模組     | 說明                                                                                   |
| -------- | -------------------------------------------------------------------------------------- |
| 爬蟲     | UNIQLO 台灣（官方 API 直取）、NET 台灣（靜態解析），合併正規化為 `data/all_sale.json`  |
| 價格歷史 | 每次執行為每件商品記錄當日 `salePrice` → `data/price-history.json`（偵測降價用）       |
| 關注警示 | `watchlist.json`（關鍵字＋目標價）比對；達標（≤目標價）或降價的寫入 `data/alerts.json` |
| 推播     | Telegram Bot 主動通知新警示，含**去重**（同件同價不重複轟炸）                          |
| 前端     | 單頁 React UI：品牌切換、分類/排序/搜尋、收藏（localStorage）、🔔 關注警示橫幅         |
| 部署     | 一鍵 scp 部署到雲端主機 + 每日 cron，PC 關機也照跑                                     |

## 技術棧

Python（requests / BeautifulSoup4）、React（CDN JSX，無建置）、Bash、cron、Telegram Bot API。

## 快速開始

```bash
# 1. 爬資料（含價格歷史 + 關注警示）
pip install -r requirements.txt
python run_scrapers.py

# 2. 開前端（需 HTTP server，不能 file://）
bash start.sh            # → http://localhost:8080
```

## 設定關注 + 推播

```bash
# 編輯 watchlist.json：你想追的關鍵字 + 目標價（max_price 設 null = 只要特價就提醒）
# Telegram 推播：複製範本填入你的 bot token + chat_id
cp telegram_config.example.json telegram_config.json   # 已 gitignore
```

## 每日自動跑（雲端）

```bash
export TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=...
bash deploy_sale_tracker_aws.sh   # scp 部署 + venv + 每日 cron + 推播
```

## 架構

```
run_scrapers.py   爬蟲入口 → 合併 → 呼叫 tracking
tracking.py       價格歷史 + watchlist 比對 + Telegram 推播（含去重）
scrapers/         uniqlo_scraper.py / net_scraper.py
index.html        React 前端（讀 data/*.json）
data/             all_sale.json / price-history.json / alerts.json（gitignore）
```

## 安全

祕密（Telegram token）由 `telegram_config.json` 或環境變數提供，已 gitignore，不進版控。
