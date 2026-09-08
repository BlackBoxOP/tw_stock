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

def get_ticker_latest_date(ticker_file):
    if not os.path.exists(ticker_file) or os.path.getsize(ticker_file) == 0:
        return None
    try:
        df = pd.read_parquet(ticker_file, columns=['Date'])
        if not df.empty:
            return pd.to_datetime(df['Date']).dt.date.max()
    except Exception:
        return None
    return None

def should_skip_ticker(ticker, is_init=False, force=False):
    if force:
        return False, None
    ticker_file = os.path.join(DIR_TICKER, f"{ticker.replace('.', '_')}.parquet")
    if not os.path.exists(ticker_file) or os.path.getsize(ticker_file) == 0:
        return False, None

    if is_init:
        # 全歷史模式：若檔案已存在且有內容，代表過去已完成初始化
        return True, "歷史資料已存在 (跳過初始化)"

    # 增量模式：檢查最新日期是否已經是今天 (台灣時間)
    latest_date = get_ticker_latest_date(ticker_file)
    today = datetime.now().date()
    if latest_date and latest_date >= today:
        return True, f"已包含今日最新資料 ({latest_date})"

    return False, latest_date

def flush_batch(batch_records):
    if not batch_records:
        return
    
    # 1. 維度 1：以股票代號切分 (寫入 by_ticker)
    for ticker, df in batch_records:
        ticker_file = os.path.join(DIR_TICKER, f"{ticker.replace('.', '_')}.parquet")
        append_parquet(ticker_file, df, subset_keys=['Date'])

    # 彙整本批次所有資料
    full_batch_df = pd.concat([df for _, df in batch_records], ignore_index=True)
    full_batch_df['Year'] = pd.to_datetime(full_batch_df['Date']).dt.year

    # 2. 維度 2：以單日切分 (寫入 by_date)
    for date_val, group in full_batch_df.groupby('Date'):
        date_file = os.path.join(DIR_DATE, f"{date_val}.parquet")
        append_parquet(date_file, group.drop(columns=['Year'], errors='ignore'), subset_keys=['Ticker'])

    # 3. 維度 3：以年份切分 (寫入 by_year)
    for year_val, group in full_batch_df.groupby('Year'):
        year_file = os.path.join(DIR_YEAR, f"{year_val}.parquet")
        append_parquet(year_file, group.drop(columns=['Year'], errors='ignore'), subset_keys=['Date', 'Ticker'])

def run_sync(is_init=False, force=False, limit=None, batch_size=20):
    tickers = get_target_tickers()
    if limit is not None:
        tickers = tickers[:limit]
    period = "max" if is_init else "5d"
    mode_desc = "全歷史" if is_init else "增量"
    print(f"[{datetime.now()}] 啟動同步 (模式: {mode_desc}, 強制更新: {force}, 標的數: {len(tickers)})")

    batch_records = []
    skipped_count = 0
    synced_count = 0

    for idx, ticker in enumerate(tickers, 1):
        # Checkpoint: 檢查是否已經抓取過
        skip, reason = should_skip_ticker(ticker, is_init=is_init, force=force)
        if skip:
            skipped_count += 1
            if idx % 50 == 0 or idx == len(tickers):
                print(f"[{idx}/{len(tickers)}] 進度 - 已跳過: {skipped_count}, 已同步: {synced_count}")
            continue

        try:
            stock = yf.Ticker(ticker)
            df = stock.history(period=period, interval="1d")

            if df.empty:
                continue

            df = clean_data(df, ticker)
            batch_records.append((ticker, df))
            synced_count += 1

            # 達到批次量立即寫入三維度，確保斷點續傳的一致性並釋放記憶體
            if len(batch_records) >= batch_size:
                flush_batch(batch_records)
                batch_records.clear()
                print(f"[{idx}/{len(tickers)}] 已批次落盤寫入三維度 (累計同步: {synced_count}, 累計跳過: {skipped_count})")

            # 頻率保護
            if synced_count % 10 == 0:
                time.sleep(1.0)
            else:
                time.sleep(0.3)

        except Exception as e:
            print(f"抓取 {ticker} 發生異常: {e}")

    # 處理最後未滿一個批次的剩餘資料
    if batch_records:
        flush_batch(batch_records)
        batch_records.clear()
        print(f"剩餘批次已同步完成 (共 {synced_count} 檔新資料)")

    print(f"[{datetime.now()}] 同步結束。總標的數: {len(tickers)}, 實際同步: {synced_count}, Checkpoint跳過: {skipped_count}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--init", action="store_true", help="初始化全部歷史資料")
    parser.add_argument("--force", "-f", action="store_true", help="強制重新抓取，略過 Checkpoint 判定")
    parser.add_argument("--limit", type=int, default=None, help="限制同步標的數量 (用於測試或抽樣)")
    parser.add_argument("--batch-size", type=int, default=20, help="批次寫入維度的大小 (預設 20)")
    args = parser.parse_args()
    run_sync(is_init=args.init, force=args.force, limit=args.limit, batch_size=args.batch_size)

