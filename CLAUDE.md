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
n8n_workflow.json        ← n8n 排程 workflow（匯入 n8n 即可）
sale-tracker-plan.md     ← 完整開發計畫書（詳細 Phase 規劃）
```

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
