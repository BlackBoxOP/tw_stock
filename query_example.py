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
# 4. TWSE OpenAPI 盤中 5分/5秒 統計分析
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

# ==========================================
# 5. 籌碼面：三大法人買賣超排行 (外資+投信同步買超前5名)
# ==========================================
inst_dir = f"{BASE_URL}/institutional"
existing_inst = sorted(glob.glob(f"{inst_dir}/*.parquet")) if USE_LOCAL else [f"{inst_dir}/2026-09-08.parquet"]
if existing_inst:
    inst_file = existing_inst[-1]
    inst_date = os.path.splitext(os.path.basename(inst_file))[0]
    print(f"\n--- 5. 三大法人買賣超排行 ({inst_date}，外資+投信同買) ---")
    df_inst = duckdb.query(f"""
        SELECT 
            Ticker, Name, Market,
            Foreign_Net / 1000 AS Foreign_K_Shares,
            Trust_Net / 1000 AS Trust_K_Shares,
            Dealer_Net / 1000 AS Dealer_K_Shares,
            Total_Net / 1000 AS Total_K_Shares
        FROM '{inst_file}'
        WHERE Foreign_Net > 0 AND Trust_Net > 0
        ORDER BY Total_Net DESC
        LIMIT 5
    """).df()
    print(df_inst)

# ==========================================
# 6. 券商分點主力查詢 (Fubon DJ 嘉實資訊)
# ==========================================
broker_dir = f"{BASE_URL}/chips/broker_trading"
existing_broker = sorted(glob.glob(f"{broker_dir}/*.parquet")) if USE_LOCAL else [f"{broker_dir}/2026-09-08.parquet"]
if existing_broker:
    broker_file = existing_broker[-1]
    print(f"\n--- 6. 券商分點主力進出 (台積電 2330 買超前3大分點) ---")
    df_broker = duckdb.query(f"""
        SELECT 
            Date, Ticker, Name, Side, Rank,
            Broker_Name, Net_Qty, Share_Pct, Total_Buy, Avg_Buy_Cost
        FROM '{broker_file}'
        WHERE Ticker = '2330' AND Side = 'buy'
        ORDER BY Rank ASC
        LIMIT 3
    """).df()
    print(df_broker)

# ==========================================
# 7. 全維度跨表量化選股 (DuckDB 多表 JOIN)
# 技術面 + 籌碼面(三大法人+融資) + 評價面(本益比/殖利率) + 基本面(營收YoY+季報EPS)
# ==========================================
rev_dir = f"{BASE_URL}/fundamental/revenue"
eps_dir = f"{BASE_URL}/fundamental/eps"
margin_dir = f"{BASE_URL}/margin"
val_dir = f"{BASE_URL}/valuation"

existing_rev = sorted(glob.glob(f"{rev_dir}/*.parquet"))
existing_eps = sorted(glob.glob(f"{eps_dir}/*.parquet"))
existing_margin = sorted(glob.glob(f"{margin_dir}/*.parquet"))
existing_val = sorted(glob.glob(f"{val_dir}/*.parquet"))

if existing_inst and existing_margin and existing_val and existing_rev and existing_eps:
    print(f"\n--- 7. 全維度跨表量化選股 (籌碼 + 評價 + 營收成長 + 季報 EPS) ---")
    df_quant = duckdb.query(f"""
        SELECT 
            i.Ticker,
            i.Name,
            i.Market,
            i.Foreign_Net / 1000 AS Foreign_K,
            i.Trust_Net / 1000 AS Trust_K,
            (m.Margin_Balance - m.Margin_Prev_Balance) AS Margin_Change,
            v.PE_Ratio,
            v.Dividend_Yield,
            r.YoY_Growth AS Rev_YoY_Pct,
            e.EPS
        FROM '{existing_inst[-1]}' i
        LEFT JOIN '{existing_margin[-1]}' m ON i.Ticker = m.Ticker
        LEFT JOIN '{existing_val[-1]}' v ON i.Ticker = v.Ticker
        LEFT JOIN '{existing_rev[-1]}' r ON i.Ticker = r.Ticker
        LEFT JOIN '{existing_eps[-1]}' e ON i.Ticker = e.Ticker
        WHERE i.Foreign_Net > 0 
          AND i.Trust_Net > 0
          AND r.YoY_Growth > 10.0
          AND e.EPS > 1.0
        ORDER BY i.Foreign_Net DESC
        LIMIT 5
    """).df()
    print(df_quant)

# ==========================================
# 8. 集保戶股權分散表 (TDCC 千張大戶與散戶比例)
# ==========================================
tdcc_dir = f"{BASE_URL}/chips/tdcc"
existing_tdcc = sorted(glob.glob(f"{tdcc_dir}/*.parquet")) if USE_LOCAL else [f"{tdcc_dir}/2026-09-04.parquet"]
if existing_tdcc:
    tdcc_file = existing_tdcc[-1]
    tdcc_date = os.path.splitext(os.path.basename(tdcc_file))[0]
    print(f"\n--- 8. 集保大戶持股比例 ({tdcc_date}，指標權值股) ---")
    df_tdcc = duckdb.query(f"""
        SELECT 
            Ticker, Total_Holders,
            Under_10K_Pct AS Retail_Under_10K_Pct,
            Over_400K_Pct AS Large_Over_400K_Pct,
            Over_1000K_Pct AS Giant_Over_1000K_Pct,
            Over_1000K_Holders AS Giant_Holders_Count
        FROM '{tdcc_file}'
        WHERE Ticker IN ('2330', '2317', '2454', '0050')
        ORDER BY Over_1000K_Pct DESC
    """).df()
    print(df_tdcc)

# ==========================================
# 9. 除權除息預告與現金股利 (Dividends)
# ==========================================
div_file = f"{BASE_URL}/dividends/upcoming.parquet"
if os.path.exists(div_file) or not USE_LOCAL:
    print(f"\n--- 9. 即將除權除息預告表 (現金股利排行前5名) ---")
    df_div = duckdb.query(f"""
        SELECT 
            Ex_Date, Ticker, Name, Ex_Type, Cash_Dividend, Latest_NAV
        FROM '{div_file}'
        WHERE Cash_Dividend > 0
        ORDER BY Cash_Dividend DESC
        LIMIT 5
    """).df()
    print(df_div)

# ==========================================
# 10. 期交所三大法人期貨部位 (TAIFEX 外資/投信台指期未平倉)
# ==========================================
taifex_dir = f"{BASE_URL}/taifex/institutional"
existing_taifex = sorted(glob.glob(f"{taifex_dir}/*.parquet")) if USE_LOCAL else []
if existing_taifex:
    taifex_file = existing_taifex[-1]
    taifex_date = os.path.splitext(os.path.basename(taifex_file))[0]
    print(f"\n--- 10. 期貨三大法人大額交易與未平倉 ({taifex_date}，臺股期貨與小台) ---")
    df_taifex = duckdb.query(f"""
        SELECT 
            Commodity, Institution, Net_Volume,
            OI_Long_Volume, OI_Short_Volume, OI_Net_Volume
        FROM '{taifex_file}'
        WHERE Commodity IN ('臺股期貨', '小型臺指期貨')
        ORDER BY Commodity, Institution
    """).df()
    print(df_taifex)

# ==========================================
# 11. 借券賣出管制餘額 (TWSE SBL 外資空頭避險指標)
# ==========================================
sbl_dir = f"{BASE_URL}/margin/sbl"
existing_sbl = sorted(glob.glob(f"{sbl_dir}/*.parquet")) if USE_LOCAL else []
if existing_sbl:
    sbl_file = existing_sbl[-1]
    sbl_date = os.path.splitext(os.path.basename(sbl_file))[0]
    print(f"\n--- 11. 借券賣出與信用總量管制 ({sbl_date}，長榮/廣達/聯發科/台積電) ---")
    df_sbl = duckdb.query(f"""
        SELECT 
            Ticker, Name, Margin_Short_Balance,
            SBL_Daily_Sell / 1000 AS SBL_Sell_K,
            SBL_Daily_Return / 1000 AS SBL_Return_K,
            SBL_Net_Change / 1000 AS SBL_Net_Change_K,
            SBL_Balance / 1000 AS SBL_Balance_K
        FROM '{sbl_file}'
        WHERE Ticker IN ('2330', '2317', '2454', '2382', '2603')
        ORDER BY SBL_Balance DESC
    """).df()
    print(df_sbl)

