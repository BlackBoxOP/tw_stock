import os
import glob
import duckdb

# 支援本地路徑或遠端 GitHub Pages / 自訂網域 URL
USE_LOCAL = os.path.exists("data/by_ticker") and len(os.listdir("data/by_ticker")) > 0
# 自訂網域: https://stocks.blackboxop.eu.cc/data ，預設網址: https://blackboxop.github.io/tw_stock/data
BASE_URL = "data" if USE_LOCAL else "https://stocks.blackboxop.eu.cc/data"

print(f"[{'本地模式' if USE_LOCAL else '遠端模式'}] 資料來源根目錄: {BASE_URL}")

# ==========================================
# 1. 個股回測查詢 (支援 1分K 與 日線)
# ==========================================
test_ticker = "2330_TW"
if USE_LOCAL and not os.path.exists(f"{BASE_URL}/by_ticker/{test_ticker}.parquet"):
    existing_files = glob.glob(f"{BASE_URL}/by_ticker/*.parquet")
    if existing_files:
        test_ticker = os.path.splitext(os.path.basename(existing_files[0]))[0]

print(f"\n--- 1. 個股回測查詢 ({test_ticker}，自動支援 1分K/日線) ---")
ticker_url = f"{BASE_URL}/by_ticker/{test_ticker}.parquet"

# 檢查目標個股具備 Datetime (1分K) 或 Date (日線) 欄位
cols = [c[0] for c in duckdb.query(f"DESCRIBE SELECT * FROM '{ticker_url}'").fetchall()]
time_col = "Datetime" if "Datetime" in cols else "Date"

df_single = duckdb.query(f"""
    SELECT {time_col} as Timestamp, Open, High, Low, Close, Volume 
    FROM '{ticker_url}' 
    ORDER BY {time_col} DESC 
    LIMIT 5
""").df()
print(df_single)

# ==========================================
# 2. 今日選股快照 (讀取 by_date，免掃描全市場)
# ==========================================
test_date = "2026-09-08"
if USE_LOCAL and not os.path.exists(f"{BASE_URL}/by_date/{test_date}.parquet"):
    existing_dates = sorted(glob.glob(f"{BASE_URL}/by_date/*.parquet"))
    if existing_dates:
        test_date = os.path.splitext(os.path.basename(existing_dates[-1]))[0]

print(f"\n--- 2. 今日選股快照 ({test_date}，讀取 by_date) ---")
date_url = f"{BASE_URL}/by_date/{test_date}.parquet"
df_screen = duckdb.query(f"""
    SELECT Ticker, Close, Volume 
    FROM '{date_url}' 
    ORDER BY Volume DESC 
    LIMIT 5
""").df()
print(df_screen)

# ==========================================
# 3. 年度大盤批次分析 (讀取 by_year)
# ==========================================
test_year = "2026"
if USE_LOCAL and not os.path.exists(f"{BASE_URL}/by_year/{test_year}.parquet"):
    existing_years = sorted(glob.glob(f"{BASE_URL}/by_year/*.parquet"))
    if existing_years:
        test_year = os.path.splitext(os.path.basename(existing_years[-1]))[0]

print(f"\n--- 3. 年度大盤批次分析 ({test_year}，讀取 by_year) ---")
year_url = f"{BASE_URL}/by_year/{test_year}.parquet"
df_year = duckdb.query(f"""
    SELECT Date, count(DISTINCT Ticker) as active_stocks, sum(Volume) as total_volume 
    FROM '{year_url}' 
    GROUP BY Date 
    ORDER BY Date DESC 
    LIMIT 5
""").df()
print(df_year)

# ==========================================
# 4. TWSE OpenAPI 盤中 5分/5秒 統計分析 (新增)
# ==========================================
openapi_dir = f"{BASE_URL}/twse_openapi/mi_5mins"
existing_openapi = sorted(glob.glob(f"{openapi_dir}/*.parquet")) if USE_LOCAL else [f"{openapi_dir}/2026-09-08.parquet"]
if existing_openapi:
    openapi_file = existing_openapi[-1]
    openapi_date = os.path.splitext(os.path.basename(openapi_file))[0]
    print(f"\n--- 4. TWSE 官方 OpenAPI 5分/5秒盤中統計 ({openapi_date}) ---")
    df_openapi = duckdb.query(f"""
        SELECT 
            Time_Formatted as Time,
            AccTransaction,
            IntervalTransaction,
            AccTradeVolume,
            IntervalTradeVolume,
            IntervalTradeValue
        FROM '{openapi_file}'
        WHERE IntervalTradeVolume > 0
        ORDER BY IntervalTradeVolume DESC
        LIMIT 5
    """).df()
    print(df_openapi)
