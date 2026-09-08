import os
import glob
import duckdb

# 範例：若本地存在資料庫則自動使用本地路徑測試，否則可切換為 GitHub Pages 或 Cloudflare 遠端 URL
USE_LOCAL = os.path.exists("data/by_ticker") and len(os.listdir("data/by_ticker")) > 0
BASE_URL = "data" if USE_LOCAL else "https://username.github.io/tw-stock-data/data"

print(f"[{'本地模式' if USE_LOCAL else '遠端模式'}] 資料來源根目錄: {BASE_URL}")

# 1. 個股回測查詢 (預設 2330_TW，若不存在則取第一檔已下載的個股)
test_ticker = "2330_TW"
if USE_LOCAL and not os.path.exists(f"{BASE_URL}/by_ticker/{test_ticker}.parquet"):
    existing_files = glob.glob(f"{BASE_URL}/by_ticker/*.parquet")
    if existing_files:
        test_ticker = os.path.splitext(os.path.basename(existing_files[0]))[0]

print(f"\n--- 1. 個股回測查詢 ({test_ticker}，讀取 by_ticker，網路流量極低) ---")
ticker_url = f"{BASE_URL}/by_ticker/{test_ticker}.parquet"
df_single = duckdb.query(f"""
    SELECT Date, Open, High, Low, Close, Volume 
    FROM '{ticker_url}' 
    ORDER BY Date DESC 
    LIMIT 5
""").df()
print(df_single)

# 2. 今日選股快照
test_date = "2026-09-08"
if USE_LOCAL and not os.path.exists(f"{BASE_URL}/by_date/{test_date}.parquet"):
    existing_dates = sorted(glob.glob(f"{BASE_URL}/by_date/*.parquet"))
    if existing_dates:
        test_date = os.path.splitext(os.path.basename(existing_dates[-1]))[0]

print(f"\n--- 2. 今日選股快照 ({test_date}，讀取 by_date，免掃描全個股) ---")
date_url = f"{BASE_URL}/by_date/{test_date}.parquet"
df_screen = duckdb.query(f"""
    SELECT Ticker, Close, Volume 
    FROM '{date_url}' 
    ORDER BY Volume DESC 
    LIMIT 5
""").df()
print(df_screen)

# 3. 年度大盤批次分析
test_year = "2026"
if USE_LOCAL and not os.path.exists(f"{BASE_URL}/by_year/{test_year}.parquet"):
    existing_years = sorted(glob.glob(f"{BASE_URL}/by_year/*.parquet"))
    if existing_years:
        test_year = os.path.splitext(os.path.basename(existing_years[-1]))[0]

print(f"\n--- 3. 年度大盤批次分析 ({test_year}，讀取 by_year) ---")
year_url = f"{BASE_URL}/by_year/{test_year}.parquet"
df_year = duckdb.query(f"""
    SELECT Date, count(*) as active_stocks, sum(Volume) as total_volume 
    FROM '{year_url}' 
    GROUP BY Date 
    ORDER BY Date DESC 
    LIMIT 5
""").df()
print(df_year)
