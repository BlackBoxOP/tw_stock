# TW Stock Data Hub (Parquet + Git Scraping)

每日自動抓取台灣上市與上櫃全股票、ETF 歷史資料，並以 Parquet 格式同時儲存為三大維度。

## 目錄結構
- `data/tw_stock_list.parquet`：上市櫃官方股票清單
- `data/by_ticker/`：按代號分檔（個股全歷史，回測最優）
- `data/by_date/`：按單日分檔（每日全市場，選股最優）
- `data/by_year/`：按年份分檔（年度彙整，批次統計最優）

## 首次初始化
1. 在 GitHub 建立此 Repository 並推送程式碼。
2. 進入 Repository 的 **Settings** -> **Actions** -> **General** -> **Workflow permissions**，勾選 **Read and write permissions**。
3. 手動觸發一次 `Weekly Update Stock List` 工作流產生股票名冊。
4. 手動觸發 `Daily Stock Parquet Sync` 工作流，並將 `init_mode` 勾選為 true。

