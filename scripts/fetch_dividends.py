import os
import re
import requests
import pandas as pd
import numpy as np
from datetime import datetime

OUTPUT_DIR = "data/dividends"
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def clean_float(val):
    if val is None or pd.isna(val):
        return np.nan
    s = re.sub(r'<[^>]+>', '', str(val)).replace(',', '').strip()
    if not s or s == '--' or s == '-' or s == 'N/A' or '待公佈' in s or '洽' in s:
        return np.nan
    try:
        return round(float(s), 4)
    except ValueError:
        return np.nan

def parse_roc_date(roc_str):
    """將 '115年09月14日' 或 '1150914' 轉換為 '2026-09-14'"""
    s = str(roc_str).strip()
    m = re.search(r'(\d+)[年/-](\d+)[月/-](\d+)', s)
    if m:
        roc_y, mm, dd = int(m.group(1)), m.group(2).zfill(2), m.group(3).zfill(2)
        return f"{roc_y + 1911}-{mm}-{dd}"
    if len(s) == 7:
        return f"{int(s[:3]) + 1911}-{s[3:5]}-{s[5:7]}"
    return s

def fetch_upcoming_dividends():
    """抓取除權除息預告表 (TWT48U)"""
    url = "https://www.twse.com.tw/rwd/zh/exRight/TWT48U?response=json"
    print(f"[{datetime.now()}] 正在抓取除權除息預告表 (TWT48U)...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            print(f"TWSE TWT48U 回傳 HTTP {resp.status_code}")
            return None
        data = resp.json()
        if data.get('stat') != 'OK' or not data.get('data'):
            print("目前無最新除權除息預告資料。")
            return None

        rows = []
        for d in data['data']:
            if len(d) < 8:
                continue
            ex_date = parse_roc_date(d[0])
            ticker = str(d[1]).strip()
            name = str(d[2]).strip()
            ex_type = str(d[3]).strip()
            stock_dividend = clean_float(d[4])
            cash_capital_rate = clean_float(d[5])
            cash_capital_price = clean_float(d[6])
            cash_dividend = clean_float(d[7])
            latest_nav = clean_float(d[11]) if len(d) > 11 else np.nan
            latest_eps = clean_float(d[12]) if len(d) > 12 else np.nan

            rows.append({
                'Ex_Date': ex_date,
                'Ticker': ticker,
                'Name': name,
                'Ex_Type': ex_type,
                'Cash_Dividend': cash_dividend,
                'Stock_Dividend_Rate': stock_dividend,
                'Capital_Increase_Rate': cash_capital_rate,
                'Capital_Increase_Price': cash_capital_price,
                'Latest_NAV': latest_nav,
                'Latest_EPS': latest_eps,
            })

        df = pd.DataFrame(rows)
        out_file = os.path.join(OUTPUT_DIR, "upcoming.parquet")
        df.to_parquet(out_file, engine='pyarrow', compression='snappy', index=False)
        print(f"[{datetime.now()}] 成功儲存 {len(df)} 筆即將除權除息預告至 {out_file}")
        return out_file
    except Exception as e:
        print(f"抓取除權除息預告失敗: {e}")
        return None

def fetch_ex_right_results():
    """抓取除權除息計算結果表 (TWT49U)"""
    url = "https://www.twse.com.tw/rwd/zh/exRight/TWT49U?response=json"
    print(f"[{datetime.now()}] 正在抓取除權除息計算結果表 (TWT49U)...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return None
        data = resp.json()
        if data.get('stat') != 'OK' or not data.get('data'):
            return None

        rows = []
        for d in data['data']:
            if len(d) < 11:
                continue
            date_str = parse_roc_date(d[0])
            ticker = str(d[1]).strip()
            name = str(d[2]).strip()
            pre_close = clean_float(d[3])
            ex_ref_price = clean_float(d[4])
            right_dividend_val = clean_float(d[5])
            ex_type = str(d[6]).strip()
            limit_up = clean_float(d[7])
            limit_down = clean_float(d[8])
            open_base = clean_float(d[9])

            rows.append({
                'Date': date_str,
                'Ticker': ticker,
                'Name': name,
                'Ex_Type': ex_type,
                'Pre_Close': pre_close,
                'Ex_Ref_Price': ex_ref_price,
                'Value': right_dividend_val,
                'Limit_Up': limit_up,
                'Limit_Down': limit_down,
                'Open_Base': open_base,
            })

        df = pd.DataFrame(rows)
        out_file = os.path.join(OUTPUT_DIR, "recent_results.parquet")
        df.to_parquet(out_file, engine='pyarrow', compression='snappy', index=False)
        print(f"[{datetime.now()}] 成功儲存 {len(df)} 筆除權除息計算結果至 {out_file}")
        return out_file
    except Exception as e:
        print(f"抓取除權除息結果失敗: {e}")
        return None

if __name__ == "__main__":
    fetch_upcoming_dividends()
    fetch_ex_right_results()

