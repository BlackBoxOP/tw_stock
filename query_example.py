import duckdb

# 範例：可換成你的 GitHub Pages 網址或 Cloudflare 自訂網域網址
BASE_URL = "https://username.github.io/tw-stock-data/data"

print("--- 1. 個股回測查詢 (讀取 by_ticker，網路流量極低) ---")
ticker_url = f"{BASE_URL}/by_ticker/2330_TW.parquet"
df_single = duckdb.query(f"""
    SELECT Date, Open, High, Low, Close, Volume 
    FROM '{ticker_url}' 
    ORDER BY Date DESC 
    LIMIT 5
""").df()
print(df_single)

print("\n--- 2. 今日選股快照 (讀取 by_date，免掃描全個股) ---")
date_url = f"{BASE_URL}/by_date/2026-09-08.parquet"
df_screen = duckdb.query(f"""
    SELECT Ticker, Close, Volume 
    FROM '{date_url}' 
    WHERE Volume > 5000000 
    ORDER BY Volume DESC 
    LIMIT 5
""").df()
print(df_screen)

print("\n--- 3. 年度大盤批次分析 (讀取 by_year) ---")
year_url = f"{BASE_URL}/by_year/2026.parquet"
df_year = duckdb.query(f"""
    SELECT Date, count(*) as active_stocks, sum(Volume) as total_volume 
    FROM '{year_url}' 
    GROUP BY Date 
    ORDER BY Date DESC 
    LIMIT 5
""").df()
print(df_year)

