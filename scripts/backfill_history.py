"""
台股歷史多維度數據回補引擎 (Backfill Engine)
支援回補三大法人買賣超 (T86)、融資融券 (MI_MARGN)、評價面 (BWIBBU_d) 與大盤指數 (MI_INDEX)
"""
import os
import re
import time
import argparse
import glob
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

INSTITUTIONAL_DIR = "data/institutional"
MARGIN_DIR = "data/margin"
VALUATION_DIR = "data/valuation"
INDICES_DIR = "data/market_indices"

os.makedirs(INSTITUTIONAL_DIR, exist_ok=True)
os.makedirs(MARGIN_DIR, exist_ok=True)
os.makedirs(VALUATION_DIR, exist_ok=True)
os.makedirs(INDICES_DIR, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def clean_num(val):
    if val is None or pd.isna(val):
        return 0
    s = re.sub(r'<[^>]+>', '', str(val)).replace(',', '').strip()
    if not s or s == '--' or s == '-':
        return 0
    try:
        return int(s)
    except ValueError:
        try:
            return int(float(s))
        except ValueError:
            return 0

def clean_float(val):
    if val is None or pd.isna(val):
        return np.nan
    s = re.sub(r'<[^>]+>', '', str(val)).replace(',', '').strip()
    if not s or s == '--' or s == '-':
        return np.nan
    try:
        return round(float(s), 4)
    except ValueError:
        return np.nan

def backfill_institutional(date_str):
    out_file = os.path.join(INSTITUTIONAL_DIR, f"{date_str}.parquet")
    if os.path.exists(out_file):
        return True

    yyyymmdd = date_str.replace('-', '')
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={yyyymmdd}&selectType=ALL"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return False
        res_json = resp.json()
        if res_json.get('stat') != 'OK' or not res_json.get('data'):
            return False

        rows = []
        for d in res_json['data']:
            if len(d) < 19:
                continue
            rows.append({
                'Date': date_str,
                'Ticker': str(d[0]).strip(),
                'Name': str(d[1]).strip(),
                'Market': 'TWSE',
                'Foreign_Buy': clean_num(d[2]),
                'Foreign_Sell': clean_num(d[3]),
                'Foreign_Net': clean_num(d[4]),
                'Foreign_Dealer_Net': clean_num(d[7]),
                'Trust_Buy': clean_num(d[8]),
                'Trust_Sell': clean_num(d[9]),
                'Trust_Net': clean_num(d[10]),
                'Dealer_Self_Net': clean_num(d[14]),
                'Dealer_Hedge_Net': clean_num(d[17]),
                'Dealer_Net': clean_num(d[11]),
                'Total_Net': clean_num(d[18]),
            })

        df = pd.DataFrame(rows)
        df.sort_values(by='Ticker', inplace=True)
        df.to_parquet(out_file, engine='pyarrow', compression='snappy', index=False)
        print(f"  [三大法人] {date_str} 儲存 {len(df)} 筆")
        return True
    except Exception as e:
        print(f"  [三大法人] {date_str} 抓取失敗: {e}")
        return False

def backfill_margin(date_str):
    out_file = os.path.join(MARGIN_DIR, f"{date_str}.parquet")
    if os.path.exists(out_file):
        return True

    yyyymmdd = date_str.replace('-', '')
    url = f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?response=json&date={yyyymmdd}&selectType=ALL"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return False
        res_json = resp.json()
        if res_json.get('stat') != 'OK' or 'tables' not in res_json or len(res_json['tables']) < 2:
            return False

        raw_rows = res_json['tables'][1].get('data', [])
        rows = []
        for d in raw_rows:
            if len(d) < 15:
                continue
            ticker = str(d[0]).strip()
            name = str(d[1]).strip()
            if not ticker or len(ticker) < 2:
                continue

            m_buy = clean_num(d[2])
            m_sell = clean_num(d[3])
            m_cash_repay = clean_num(d[4])
            m_prev_bal = clean_num(d[5])
            m_bal = clean_num(d[6])
            m_limit = clean_num(d[7])
            m_util = round(m_bal / m_limit * 100, 2) if m_limit > 0 else 0.0

            s_buy = clean_num(d[8])
            s_sell = clean_num(d[9])
            s_stock_repay = clean_num(d[10])
            s_prev_bal = clean_num(d[11])
            s_bal = clean_num(d[12])
            s_limit = clean_num(d[13])
            s_util = round(s_bal / s_limit * 100, 2) if s_limit > 0 else 0.0

            offset = clean_num(d[14])

            rows.append({
                'Date': date_str,
                'Ticker': ticker,
                'Name': name,
                'Market': 'TWSE',
                'Margin_Buy': m_buy,
                'Margin_Sell': m_sell,
                'Margin_Cash_Repay': m_cash_repay,
                'Margin_Prev_Balance': m_prev_bal,
                'Margin_Balance': m_bal,
                'Margin_Limit': m_limit,
                'Margin_Utilization_Rate': m_util,
                'Short_Buy': s_buy,
                'Short_Sell': s_sell,
                'Short_Stock_Repay': s_stock_repay,
                'Short_Prev_Balance': s_prev_bal,
                'Short_Balance': s_bal,
                'Short_Limit': s_limit,
                'Short_Utilization_Rate': s_util,
                'Offsetting': offset,
            })

        df = pd.DataFrame(rows)
        df.sort_values(by='Ticker', inplace=True)
        df.to_parquet(out_file, engine='pyarrow', compression='snappy', index=False)
        print(f"  [融資融券] {date_str} 儲存 {len(df)} 筆")
        return True
    except Exception as e:
        print(f"  [融資融券] {date_str} 抓取失敗: {e}")
        return False

def backfill_valuation(date_str):
    out_file = os.path.join(VALUATION_DIR, f"{date_str}.parquet")
    if os.path.exists(out_file):
        return True

    yyyymmdd = date_str.replace('-', '')
    url = f"https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d?response=json&date={yyyymmdd}&selectType=ALL"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return False
        res_json = resp.json()
        if res_json.get('stat') != 'OK' or not res_json.get('data'):
            return False

        rows = []
        for d in res_json['data']:
            if len(d) < 8:
                continue
            ticker = str(d[0]).strip()
            name = str(d[1]).strip()
            close_price = clean_float(d[2])
            dy = clean_float(d[3])
            pe = clean_float(d[5])
            pb = clean_float(d[6])
            quarter = str(d[7]).strip()

            rows.append({
                'Date': date_str,
                'Ticker': ticker,
                'Name': name,
                'Market': 'TWSE',
                'Close_Price': close_price,
                'PE_Ratio': pe,
                'PB_Ratio': pb,
                'Dividend_Yield': dy,
                'Fiscal_Quarter': quarter
            })

        df = pd.DataFrame(rows)
        df.sort_values(by='Ticker', inplace=True)
        df.to_parquet(out_file, engine='pyarrow', compression='snappy', index=False)
        print(f"  [評價面] {date_str} 儲存 {len(df)} 筆")
        return True
    except Exception as e:
        print(f"  [評價面] {date_str} 抓取失敗: {e}")
        return False

def get_trading_days(start_date=None, end_date=None, days_limit=None):
    """自 data/by_date 或日曆取得有效交易日"""
    by_date_files = sorted(glob.glob("data/by_date/*.parquet"))
    all_dates = [os.path.splitext(os.path.basename(f))[0] for f in by_date_files]

    if not all_dates:
        # 若無本地檔案，以工作日推算
        cur = datetime.now()
        all_dates = []
        for i in range(120):
            d = cur - timedelta(days=i)
            if d.weekday() < 5:
                all_dates.append(d.strftime("%Y-%m-%d"))
        all_dates.sort()

    if start_date:
        all_dates = [d for d in all_dates if d >= start_date]
    if end_date:
        all_dates = [d for d in all_dates if d <= end_date]

    if days_limit and len(all_dates) > days_limit:
        all_dates = all_dates[-days_limit:]

    return all_dates

def run_backfill(days=10, start=None, end=None, delay=1.2):
    trading_days = get_trading_days(start_date=start, end_date=end, days_limit=days)
    print(f"[{datetime.now()}] 準備回補 {len(trading_days)} 個交易日之多維度歷史資料 (三大法人、融資融券、本益比殖利率)...")
    print(f"涵蓋日期區間: {trading_days[0]} ~ {trading_days[-1]}\n")

    for i, dt in enumerate(reversed(trading_days), 1):
        print(f"[{i}/{len(trading_days)}] 處理交易日 {dt}...")
        
        # 檢查是否都已存在
        inst_exists = os.path.exists(os.path.join(INSTITUTIONAL_DIR, f"{dt}.parquet"))
        margin_exists = os.path.exists(os.path.join(MARGIN_DIR, f"{dt}.parquet"))
        val_exists = os.path.exists(os.path.join(VALUATION_DIR, f"{dt}.parquet"))

        if inst_exists and margin_exists and val_exists:
            print(f"  {dt} 所有維度 Parquet 已齊全，自動跳過。")
            continue

        if not inst_exists:
            backfill_institutional(dt)
            time.sleep(delay)

        if not margin_exists:
            backfill_margin(dt)
            time.sleep(delay)

        if not val_exists:
            backfill_valuation(dt)
            time.sleep(delay)

    print(f"\n[{datetime.now()}] 歷史數據回補流程執行完畢！")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="台股歷史多維度數據回補腳本")
    parser.add_argument("--days", type=int, default=10, help="回補最近 N 個交易日 (預設: 10)")
    parser.add_argument("--start", type=str, default=None, help="起始日期 (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None, help="結束日期 (YYYY-MM-DD)")
    parser.add_argument("--delay", type=float, default=1.0, help="每次網路請求間隔秒數 (預設: 1.0秒，防止 TWSE 限流)")
    args = parser.parse_args()

    run_backfill(days=args.days, start=args.start, end=args.end, delay=args.delay)

