import os
import argparse
import requests
import pandas as pd
import numpy as np
from datetime import datetime

OUTPUT_DIR = "data/fundamental/eps"
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def clean_float(val):
    if val is None or pd.isna(val):
        return np.nan
    s = str(val).replace(',', '').strip()
    if not s or s == '--' or s == '-':
        return np.nan
    try:
        return round(float(s), 4)
    except ValueError:
        return np.nan

def clean_num(val):
    if val is None or pd.isna(val):
        return 0
    s = str(val).replace(',', '').strip()
    if not s or s == '--' or s == '-':
        return 0
    try:
        return int(float(s))
    except ValueError:
        return 0

def fetch_twse_eps():
    url = "https://openapi.twse.com.tw/v1/opendata/t187ap14_L"
    print(f"[{datetime.now()}] 正在抓取 TWSE 上市季報損益與 EPS...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=25)
        if resp.status_code != 200:
            print(f"TWSE 回傳 HTTP {resp.status_code}")
            return []
        data = resp.json()
        if not isinstance(data, list) or len(data) == 0:
            return []

        rows = []
        for d in data:
            values = list(d.values())
            if len(values) < 12:
                continue
            roc_year = int(str(values[1]).strip())
            year = roc_year + 1911
            quarter = int(str(values[2]).strip())
            ticker = str(values[3]).strip()
            name = str(values[4]).strip()
            industry = str(values[5]).strip()
            eps = clean_float(values[6])
            op_rev = clean_num(values[8])
            op_profit = clean_num(values[9])
            non_op = clean_num(values[10])
            net_income = clean_num(values[11])

            rows.append({
                'Year': year,
                'Quarter': quarter,
                'Period': f"{year}_Q{quarter}",
                'Ticker': ticker,
                'Name': name,
                'Market': 'TWSE',
                'Industry': industry,
                'EPS': eps,
                'Operating_Revenue': op_rev,
                'Operating_Profit': op_profit,
                'Non_Operating_Income': non_op,
                'Net_Income': net_income
            })
        print(f"TWSE 上市取得 {len(rows)} 筆季報 EPS 資料。")
        return rows
    except Exception as e:
        print(f"抓取 TWSE EPS 失敗: {e}")
        return []

def fetch_tpex_eps():
    url = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap14_O"
    print(f"[{datetime.now()}] 正在抓取 TPEx 上櫃季報損益與 EPS...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=25)
        if resp.status_code != 200:
            print(f"TPEx 回傳 HTTP {resp.status_code}")
            return []
        data = resp.json()
        if not isinstance(data, list) or len(data) == 0:
            return []

        rows = []
        for d in data:
            values = list(d.values())
            if len(values) < 12:
                continue
            roc_year = int(str(values[1]).strip())
            year = roc_year + 1911
            quarter = int(str(values[2]).strip())
            ticker = str(values[3]).strip()
            name = str(values[4]).strip()
            industry = str(values[5]).strip()
            eps = clean_float(values[6])
            op_rev = clean_num(values[8])
            op_profit = clean_num(values[9])
            non_op = clean_num(values[10])
            net_income = clean_num(values[11])

            rows.append({
                'Year': year,
                'Quarter': quarter,
                'Period': f"{year}_Q{quarter}",
                'Ticker': ticker,
                'Name': name,
                'Market': 'TPEx',
                'Industry': industry,
                'EPS': eps,
                'Operating_Revenue': op_rev,
                'Operating_Profit': op_profit,
                'Non_Operating_Income': non_op,
                'Net_Income': net_income
            })
        print(f"TPEx 上櫃取得 {len(rows)} 筆季報 EPS 資料。")
        return rows
    except Exception as e:
        print(f"抓取 TPEx EPS 失敗: {e}")
        return []

def fetch_and_save_eps():
    twse_rows = fetch_twse_eps()
    tpex_rows = fetch_tpex_eps()
    all_rows = twse_rows + tpex_rows

    if not all_rows:
        print("無任何季報 EPS 資料可落盤。")
        return None

    df = pd.DataFrame(all_rows)
    saved_files = []
    for period, group in df.groupby('Period'):
        group_sorted = group.sort_values(by=['Market', 'Ticker'])
        out_file = os.path.join(OUTPUT_DIR, f"{period}.parquet")
        group_sorted.to_parquet(out_file, engine='pyarrow', compression='snappy', index=False)
        print(f"[{datetime.now()}] 成功儲存 {len(group_sorted)} 筆 {period} 財報 EPS 資料至 {out_file}")
        saved_files.append(out_file)

    return saved_files

if __name__ == "__main__":
    fetch_and_save_eps()

