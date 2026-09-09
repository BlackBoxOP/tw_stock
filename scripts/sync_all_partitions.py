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
        try:
            df_list = pd.read_parquet(STOCK_LIST_PATH)
            return df_list['YF_Ticker'].tolist()
        except Exception:
            pass
    return ['0050.TW', '2330.TW', '2317.TW', '2454.TW', '6488.TWO']

def detect_existing_freq(ticker_file):
    """檢查現有檔案結構是 1 分線還是日線"""
    if os.path.exists(ticker_file) and os.path.getsize(ticker_file) > 0:
        try:
            sample = pd.read_parquet(ticker_file, columns=['Datetime'])
            if not sample.empty and 'Datetime' in sample.columns:
                return '1m'
        except Exception:
            return '1d'
    return None

def clean_1m_data(df, ticker):
    df = df.reset_index()
    df['Ticker'] = ticker
    if 'Datetime' in df.columns:
        df['Datetime'] = pd.to_datetime(df['Datetime'], utc=True).dt.tz_convert('Asia/Taipei')
        df['Date'] = df['Datetime'].dt.date
    cols = ['Datetime', 'Date', 'Ticker', 'Open', 'High', 'Low', 'Close', 'Volume']
    avail_cols = [c for c in cols if c in df.columns]
    return df[avail_cols]

def clean_1d_data(df, ticker):
    df = df.reset_index()
    df['Ticker'] = ticker
    date_col = 'Date' if 'Date' in df.columns else ('Datetime' if 'Datetime' in df.columns else None)
    if date_col:
        df['Date'] = pd.to_datetime(df[date_col]).dt.date
    cols = ['Date', 'Ticker', 'Open', 'High', 'Low', 'Close', 'Volume']
    avail_cols = [c for c in cols if c in df.columns]
    return df[avail_cols]

def append_parquet(file_path, new_df, subset_keys):
    if os.path.exists(file_path) and os.path.getsize(file_path) > 0:
        try:
            existing_df = pd.read_parquet(file_path)
            # 若既有為純日線 (無 Datetime)，而新資料為 1 分線 (含 Datetime)，直接升級為 1 分線結構
            if 'Datetime' in new_df.columns and 'Datetime' not in existing_df.columns:
                combined = new_df
            else:
                combined = pd.concat([existing_df, new_df], ignore_index=True)
                valid_keys = [k for k in subset_keys if k in combined.columns]
                if valid_keys:
                    combined = combined.drop_duplicates(subset=valid_keys, keep='last')
                    combined.sort_values(by=valid_keys, inplace=True)
        except Exception:
            combined = new_df
    else:
        combined = new_df
    combined.to_parquet(file_path, engine='pyarrow', compression='snappy', index=False)

def get_ticker_latest_timestamp(ticker_file, freq='1d'):
    if not os.path.exists(ticker_file) or os.path.getsize(ticker_file) == 0:
        return None
    try:
        if freq == '1m':
            df = pd.read_parquet(ticker_file, columns=['Datetime'])
            if not df.empty and 'Datetime' in df.columns:
                return pd.to_datetime(df['Datetime']).max()
        df = pd.read_parquet(ticker_file, columns=['Date'])
        if not df.empty and 'Date' in df.columns:
            return pd.to_datetime(df['Date']).dt.date.max()
    except Exception:
        return None
    return None

def should_skip_ticker(ticker, is_init=False, force=False):
    if force:
        return False, None, None
    ticker_file = os.path.join(DIR_TICKER, f"{ticker.replace('.', '_')}.parquet")
    if not os.path.exists(ticker_file) or os.path.getsize(ticker_file) == 0:
        return False, None, None

    freq = detect_existing_freq(ticker_file) or '1d'

    if freq == '1m':
        if is_init:
            return True, freq, "1分K歷史資料已存在 (跳過初始化)"
        today = datetime.now().date()
        latest_ts = get_ticker_latest_timestamp(ticker_file, freq='1m')
        if latest_ts is not None:
            latest_date = latest_ts.date() if hasattr(latest_ts, 'date') else latest_ts
            if latest_date >= today and datetime.now().hour >= 14:
                return True, freq, f"1分K已包含今日最新收盤資料 ({latest_ts})"
        return False, freq, latest_ts
    else:
        if is_init:
            return True, freq, "日線歷史資料已存在 (跳過初始化)"
        today = datetime.now().date()
        latest_ts = get_ticker_latest_timestamp(ticker_file, freq='1d')
        if latest_ts is not None:
            latest_date = latest_ts.date() if hasattr(latest_ts, 'date') else latest_ts
            if latest_date >= today and datetime.now().hour >= 14:
                return True, freq, f"日線已包含今日最新資料 ({latest_date})"
        return False, freq, latest_ts

def fetch_ticker_data(stock, ticker, is_init=False):
    """
    核心抓取邏輯：優先嘗試 1 分線資料 (period='7d', interval='1m')，
    若無資料 (empty 或異常) 則回退至日線 (interval='1d')
    """
    # 1. 優先嘗試 1 分線
    period_1m = "7d"
    try:
        df_1m = stock.history(period=period_1m, interval="1m")
        if not df_1m.empty:
            return clean_1m_data(df_1m, ticker), '1m'
    except Exception:
        pass

    # 2. 無 1 分線時回退至日線
    period_1d = "max" if is_init else "5d"
    try:
        df_1d = stock.history(period=period_1d, interval="1d")
        if not df_1d.empty:
            return clean_1d_data(df_1d, ticker), '1d'
    except Exception:
        pass

    return None, None

def flush_batch(batch_records):
    if not batch_records:
        return

    # 1. 維度 1：以股票代號切分 (寫入 by_ticker)
    for ticker, df, freq in batch_records:
        ticker_file = os.path.join(DIR_TICKER, f"{ticker.replace('.', '_')}.parquet")
        keys = ['Datetime'] if freq == '1m' and 'Datetime' in df.columns else ['Date']
        append_parquet(ticker_file, df, subset_keys=keys)

    # 彙整本批次所有資料
    full_batch_df = pd.concat([df for _, df, _ in batch_records], ignore_index=True)
    if 'Date' not in full_batch_df.columns and 'Datetime' in full_batch_df.columns:
        full_batch_df['Date'] = pd.to_datetime(full_batch_df['Datetime']).dt.date
    full_batch_df['Year'] = pd.to_datetime(full_batch_df['Date']).dt.year

    # 2. 維度 2：以單日切分 (寫入 by_date) - 儲存當日高解析度分時 (或日線)
    for date_val, group in full_batch_df.groupby('Date'):
        date_file = os.path.join(DIR_DATE, f"{date_val}.parquet")
        has_dt = 'Datetime' in group.columns and group['Datetime'].notna().any()
        keys = ['Datetime', 'Ticker'] if has_dt else ['Ticker']
        append_parquet(date_file, group.drop(columns=['Year'], errors='ignore'), subset_keys=keys)

    # 3. 維度 3：以年份切分 (寫入 by_year) - 維持日線維度避免超過 GitHub 100MB 單檔限制
    for year_val, group in full_batch_df.groupby('Year'):
        year_file = os.path.join(DIR_YEAR, f"{year_val}.parquet")
        if 'Datetime' in group.columns and group['Datetime'].notna().any():
            m_group = group[group['Datetime'].notna()]
            d_group = group[group['Datetime'].isna()]
            agg_dict = {
                'Open': 'first',
                'High': 'max',
                'Low': 'min',
                'Close': 'last',
                'Volume': 'sum'
            }
            m_daily = m_group.groupby(['Date', 'Ticker']).agg(agg_dict).reset_index()
            parts = [m_daily]
            if not d_group.empty:
                cols = ['Date', 'Ticker', 'Open', 'High', 'Low', 'Close', 'Volume']
                avail = [c for c in cols if c in d_group.columns]
                parts.append(d_group[avail])
            daily_summary = pd.concat(parts, ignore_index=True)
            append_parquet(year_file, daily_summary, subset_keys=['Date', 'Ticker'])
        else:
            cols = ['Date', 'Ticker', 'Open', 'High', 'Low', 'Close', 'Volume']
            avail_cols = [c for c in cols if c in group.columns]
            append_parquet(year_file, group[avail_cols], subset_keys=['Date', 'Ticker'])

def run_sync(is_init=False, force=False, limit=None, batch_size=20):
    tickers = get_target_tickers()
    if limit is not None:
        tickers = tickers[:limit]

    mode_desc = "全歷史" if is_init else "增量"
    print(f"[{datetime.now()}] 啟動同步 (模式: {mode_desc}, 強制更新: {force}, 標的數: {len(tickers)})")

    batch_records = []
    skipped_count = 0
    synced_1m = 0
    synced_1d = 0

    for idx, ticker in enumerate(tickers, 1):
        skip, existing_freq, reason = should_skip_ticker(ticker, is_init=is_init, force=force)
        if skip:
            skipped_count += 1
            if idx % 50 == 0 or idx == len(tickers):
                print(f"[{idx}/{len(tickers)}] 進度 - 跳過: {skipped_count}, 1分K: {synced_1m}, 日線: {synced_1d}")
            continue

        try:
            stock = yf.Ticker(ticker)
            df, freq = fetch_ticker_data(stock, ticker, is_init=is_init)

            if df is None or df.empty:
                continue

            batch_records.append((ticker, df, freq))
            if freq == '1m':
                synced_1m += 1
            else:
                synced_1d += 1

            if len(batch_records) >= batch_size:
                flush_batch(batch_records)
                batch_records.clear()
                print(f"[{idx}/{len(tickers)}] 批次落盤寫入三維度 (累計 1分K: {synced_1m}, 日線: {synced_1d}, 跳過: {skipped_count})")

            # 頻率保護
            if (synced_1m + synced_1d) % 10 == 0:
                time.sleep(1.0)
            else:
                time.sleep(0.3)

        except Exception as e:
            print(f"抓取 {ticker} 發生異常: {e}")

    # 處理最後剩餘批次
    if batch_records:
        flush_batch(batch_records)
        batch_records.clear()
        print(f"剩餘批次同步完成 (本輪新增 1分K: {synced_1m}, 日線: {synced_1d})")

    print(f"[{datetime.now()}] 同步結束。總標的數: {len(tickers)}, 1分K同步: {synced_1m}, 日線同步: {synced_1d}, 跳過: {skipped_count}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="台股三維度同步腳本 (優先 1 分線，無則回退至日線)")
    parser.add_argument("--init", action="store_true", help="初始化全部歷史資料")
    parser.add_argument("--force", "-f", action="store_true", help="強制重新抓取，略過 Checkpoint 判定")
    parser.add_argument("--limit", type=int, default=None, help="限制同步標的數量 (用於測試或抽樣)")
    parser.add_argument("--batch-size", type=int, default=20, help="批次寫入維度的大小 (預設 20)")
    args = parser.parse_args()
    run_sync(is_init=args.init, force=args.force, limit=args.limit, batch_size=args.batch_size)
