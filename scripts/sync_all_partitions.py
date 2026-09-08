import os
import time
import argparse
import pandas as pd
import yfinance as yf
from datetime import datetime

DIR_TICKER = "data/by_ticker"
DIR_DATE = "data/by_date"
DIR_YEAR = "data/by_year"
STOCK_LIST_PATH = "data/tw_stock_list.parquet"

for d in [DIR_TICKER, DIR_DATE, DIR_YEAR]:
    os.makedirs(d, exist_ok=True)

def get_target_tickers():
    if os.path.exists(STOCK_LIST_PATH):
        df_list = pd.read_parquet(STOCK_LIST_PATH)
        return df_list['YF_Ticker'].tolist()
    # 找不到名單時的預設權值股 fallback
    return ['2330.TW', '2317.TW', '2454.TW', '0050.TW', '6488.TWO']

def clean_data(df, ticker):
    df = df.reset_index()
    df['Ticker'] = ticker
    df['Date'] = pd.to_datetime(df['Date']).dt.date
    cols = ['Date', 'Ticker', 'Open', 'High', 'Low', 'Close', 'Volume']
    available_cols = [c for c in cols if c in df.columns]
    return df[available_cols]

def append_parquet(file_path, new_df, subset_keys):
    if os.path.exists(file_path):
        existing_df = pd.read_parquet(file_path)
        combined = pd.concat([existing_df, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset=subset_keys, keep='last')
        combined.sort_values(by=subset_keys, inplace=True)
    else:
        combined = new_df
    combined.to_parquet(file_path, engine='pyarrow', compression='snappy', index=False)

def run_sync(is_init=False):
    tickers = get_target_tickers()
    period = "max" if is_init else "5d"
    print(f"[{datetime.now()}] 啟動同步 (模式: {'全歷史' if is_init else '增量'}, 標的數: {len(tickers)})")
    
    all_new_records = []

    for idx, ticker in enumerate(tickers, 1):
        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period=period, interval="1d")
            
            if df.empty:
                continue

            df = clean_data(df, ticker)
            
            # 維度 1：以股票代號切分
            ticker_file = os.path.join(DIR_TICKER, f"{ticker.replace('.', '_')}.parquet")
            append_parquet(ticker_file, df, subset_keys=['Date'])
            
            all_new_records.append(df)
            
            # 頻率保護：每 10 檔印一次日誌，稍微休眠
            if idx % 10 == 0:
                print(f"進度: {idx}/{len(tickers)}...")
                time.sleep(1.0)
            else:
                time.sleep(0.3)
                
        except Exception as e:
            print(f"抓取 {ticker} 發生異常: {e}")

    if not all_new_records:
        print("未取得任何新數據，結束。")
        return

    full_batch_df = pd.concat(all_new_records, ignore_index=True)
    full_batch_df['Year'] = pd.to_datetime(full_batch_df['Date']).dt.year

    # 維度 2：以單日切分
    print("正在更新 by_date...")
    for date_val, group in full_batch_df.groupby('Date'):
        date_file = os.path.join(DIR_DATE, f"{date_val}.parquet")
        append_parquet(date_file, group.drop(columns=['Year'], errors='ignore'), subset_keys=['Ticker'])

    # 維度 3：以年份切分
    print("正在更新 by_year...")
    for year_val, group in full_batch_df.groupby('Year'):
        year_file = os.path.join(DIR_YEAR, f"{year_val}.parquet")
        append_parquet(year_file, group.drop(columns=['Year'], errors='ignore'), subset_keys=['Date', 'Ticker'])

    print(f"[{datetime.now()}] 全部維度同步完成。")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--init", action="store_true", help="初始化全部歷史資料")
    args = parser.parse_args()
    run_sync(is_init=args.init)

