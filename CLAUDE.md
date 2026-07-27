# sale-tracker

服飾特價追蹤工具。自動每日爬取 UNIQLO / NET 台灣男裝特價，顯示於統一 UI。

## 狀態（2026-06-10）

✅ **功能完整，可正常使用。** 爬蟲、資料、前端全部到位。

| 元件                          | 狀態                                      |
| ----------------------------- | ----------------------------------------- |
| UNIQLO 爬蟲                   | ✅ 可用（API 直取，無需 JS 渲染）         |
| NET 爬蟲                      | ✅ 可用                                   |
| 合併輸出 `data/all_sale.json` | ✅（323 件商品）                          |
| n8n 排程自動執行              | ✅ workflow 已建（`n8n_workflow.json`）   |
| 前端 UI（`index.html`）       | ✅ fetch `data/all_sale.json`，含更新時間 |
| 商品圖片                      | ✅ 圖片載入失敗自動顯示品牌名 fallback    |
| 收藏持久化                    | ✅ localStorage                           |
| 本地 HTTP server              | ✅ `bash start.sh`（port 8080）           |

## 技術棧

- **爬蟲**：Python + requests + BeautifulSoup4（`scrapers/`）
- **前端**：單頁 HTML + React JSX（無框架，inline style）
- **資料格式**：靜態 JSON（`data/`）
- **排程**：n8n workflow（`n8n_workflow.json`）

## 關鍵檔案

```
run_scrapers.py          ← 爬蟲入口：跑所有爬蟲，輸出 data/all_sale.json
scrapers/
  uniqlo_scraper.py      ← UNIQLO 台灣 API（d.uniqlo.com）
  net_scraper.py         ← NET 台灣
data/
  all_sale.json          ← 合併後的特價清單（前端應讀這個）
  uniqlo_sale.json       ← UNIQLO 原始輸出
  net_sale.json          ← NET 原始輸出
  scraper.log            ← 最近一次執行日誌
index.html               ← 前端（React JSX，目前用 PLACEHOLDER_ITEMS）
n8n_workflow.json        ← n8n 排程 workflow（n8n 未裝，目前不可用）
sale-tracker-plan.md     ← 完整開發計畫書（詳細 Phase 規劃）
watchlist.json           ← 【新】你關注的關鍵字+目標價（自行編輯）
tracking.py              ← 【新】價格歷史 + watchlist 警示（run_scrapers 自動呼叫）
data/price-history.json  ← 【新】每件商品逐日 salePrice（偵測降價用）
data/alerts.json         ← 【新】關注商品達標/降價警示（前端 🔔 橫幅讀這個）
```

## 關注警示（2026-06-23 新增）

編輯 `watchlist.json`（關鍵字 + 目標價），跑 `python run_scrapers.py` 後：
更新價格歷史 → 比對你的關注 → 達標（≤目標價）或降價的商品寫進 `data/alerts.json`，
前端最上方顯示 🔔 橫幅。`max_price` 設 `null` = 只要在特價就提醒。

```json
[{ "keyword": "束口褲", "max_price": 800, "note": "命中商品名/分類即觸發" }]
```

**待 Root（要完整自動推播才需要）**：① 手機/Telegram 推播需 bot token（給我就接上）；
② 每日自動跑需排程（n8n 未裝 → 用 cron / Claude schedule；本機關機時不跑）。
目前：手動跑 `python run_scrapers.py`，警示進 UI + alerts.json。

## 資料格式

```json
{
  "brand": "uniqlo",
  "category": "男裝",
  "name": "商品名稱",
  "originalPrice": 990,
  "salePrice": 590,
  "discount": 40,
  "sizes": ["S", "M", "L"],
  "colors": ["黑", "白"],
  "imageUrl": "https://...",
  "productUrl": "https://...",
  "scrapedAt": "2026-06-07T00:00:00Z"
}
```

## 快速執行

```bash
# 開前端（需透過 HTTP server，不能直接用 file://）
bash start.sh          # → http://localhost:8080
PORT=9090 bash start.sh  # 自訂 port

# 手動更新資料（爬蟲）
pip install -r requirements.txt
python run_scrapers.py   # 輸出到 data/all_sale.json
```

## 下一步

1. 確認 n8n workflow 排程是否已啟用（每日自動跑爬蟲）
2. NET 爬蟲：若網站改版需更新選擇器

## 爬蟲限制

- UNIQLO：用官方 API（`d.uniqlo.com`），穩定
- NET：靜態爬蟲，若網站改版需更新選擇器
- 建議執行頻率：每日一次（凌晨）
