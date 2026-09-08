# TW Stock Data Hub (Parquet + Git Scraping)

每日自動抓取台灣上市與上櫃全股票、ETF 歷史資料，並以 Parquet 格式同時儲存為三大維度。

## 目錄結構
- `data/tw_stock_list.parquet`：上市櫃官方股票清單
- `data/by_ticker/`：按代號分檔（個股全歷史，回測最優）
- `data/by_date/`：按單日分檔（每日全市場，選股最優）
- `data/by_year/`：按年份分檔（年度彙整，批次統計最優）

## Checkpoint 與斷點續傳機制
- **全歷史初始化 (`--init`)**：
  - 自動偵測 `data/by_ticker/{ticker}.parquet` 是否已存在。
  - 若已存在且有內容，自動跳過該標的；中途中斷重跑時可秒級斷點續傳，避免重複下載。
- **每日增量同步 (Daily Sync)**：
  - 比對各檔個股 Parquet 內的最新日期，若已包含今日最新收盤數據（`latest_date >= today`），自動跳過抓取，大幅節省 API 請求並避免 rate limit。
- **強制更新 (`--force` / `-f`)**：
  - 忽略 Checkpoint 判定，強制重新抓取與覆蓋。
- **批次原子落盤 (`--batch-size`)**：
  - 預設每 20 檔新抓取的標的統一寫入三大維度，確保記憶體占用極低，且中斷時三維度資料保持強一致性。

## 首次初始化
1. 在 GitHub 建立此 Repository 並推送程式碼。
2. 進入 Repository 的 **Settings** -> **Actions** -> **General** -> **Workflow permissions**，勾選 **Read and write permissions**。
3. 手動觸發一次 `Weekly Update Stock List` 工作流產生股票名冊。
4. 手動觸發 `Daily Stock Parquet Sync` 工作流，並將 `init_mode` 勾選為 true。