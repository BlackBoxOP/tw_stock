import os
import argparse
import requests
import pandas as pd
import numpy as np
from datetime import datetime

OUTPUT_DIR = "data/fundamental/revenue"
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def clean_num(val):
    if val is None or pd.isna(val):
        return 0
    s = str(val).replace(',', '').strip()
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
    s = str(val).replace(',', '').strip()
    if not s or s == '--' or s == '-':
        return np.nan
    try:
        return round(float(s), 4)
    except ValueError:
        return np.nan

def parse_roc_ym(roc_ym_str):
    """將民國年月 (例如 11507) 轉為西元 YYYY-MM (例如 2026-07)"""
    s = str(roc_ym_str).strip()
    if len(s) >= 5:
        roc_year = int(s[:-2])
        month = s[-2:]
        return f"{roc_year + 1911}-{month.zfill(2)}"
    return s

def fetch_twse_revenue():
    url = "https://openapi.twse.com.tw/v1/opendata/t187ap05_L"
    print(f"[{datetime.now()}] 正在抓取 TWSE 上市最新月營收資料...")
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
            if len(values) < 14:
                continue
            ym = parse_roc_ym(values[1])
            ticker = str(values[2]).strip()
            name = str(values[3]).strip()
            industry = str(values[4]).strip()
            rev_cur = clean_num(values[5])
            rev_last_m = clean_num(values[6])
            rev_last_y = clean_num(values[7])
            mom = clean_float(values[8])
            yoy = clean_float(values[9])
            cum_cur = clean_num(values[10])
            cum_last_y = clean_num(values[11])
            cum_yoy = clean_float(values[12])
            note = str(values[13]).strip()

            rows.append({
                'YearMonth': ym,
                'Ticker': ticker,
                'Name': name,
                'Market': 'TWSE',
                'Industry': industry,
                'Revenue_Current': rev_cur,
                'Revenue_Last_Month': rev_last_m,
                'Revenue_Last_Year': rev_last_y,
                'MoM_Growth': mom,
                'YoY_Growth': yoy,
                'Cumulative_Current': cum_cur,
                'Cumulative_Last_Year': cum_last_y,
                'Cumulative_YoY_Growth': cum_yoy,
                'Note': note
            })
        print(f"TWSE 上市取得 {len(rows)} 筆營收資料。")
        return rows
    except Exception as e:
        print(f"抓取 TWSE 月營收失敗: {e}")
        return []

def fetch_tpex_revenue():
    url = "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O"
    print(f"[{datetime.now()}] 正在抓取 TPEx 上櫃最新月營收資料...")
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
            if len(values) < 14:
                continue
            ym = parse_roc_ym(values[1])
            ticker = str(values[2]).strip()
            name = str(values[3]).strip()
            industry = str(values[4]).strip()
            rev_cur = clean_num(values[5])
            rev_last_m = clean_num(values[6])
            rev_last_y = clean_num(values[7])
            mom = clean_float(values[8])
            yoy = clean_float(values[9])
            cum_cur = clean_num(values[10])
            cum_last_y = clean_num(values[11])
            cum_yoy = clean_float(values[12])
            note = str(values[13]).strip()

            rows.append({
                'YearMonth': ym,
                'Ticker': ticker,
                'Name': name,
                'Market': 'TPEx',
                'Industry': industry,
                'Revenue_Current': rev_cur,
                'Revenue_Last_Month': rev_last_m,
                'Revenue_Last_Year': rev_last_y,
                'MoM_Growth': mom,
                'YoY_Growth': yoy,
                'Cumulative_Current': cum_cur,
                'Cumulative_Last_Year': cum_last_y,
                'Cumulative_YoY_Growth': cum_yoy,
                'Note': note
            })
        print(f"TPEx 上櫃取得 {len(rows)} 筆營收資料。")
        return rows
    except Exception as e:
        print(f"抓取 TPEx 月營收失敗: {e}")
        return []

def fetch_and_save_revenue():
    twse_rows = fetch_twse_revenue()
    tpex_rows = fetch_tpex_revenue()
    all_rows = twse_rows + tpex_rows

    if not all_rows:
        print("無任何月營收資料可落盤。")
        return None

    df = pd.DataFrame(all_rows)
    
    # 依申報年月群組存檔
    saved_files = []
    for ym, group in df.groupby('YearMonth'):
        group_sorted = group.sort_values(by=['Market', 'Ticker'])
        out_file = os.path.join(OUTPUT_DIR, f"{ym}.parquet")
        group_sorted.to_parquet(out_file, engine='pyarrow', compression='snappy', index=False)
        print(f"[{datetime.now()}] 成功儲存 {len(group_sorted)} 筆 {ym} 月營收資料至 {out_file}")
        saved_files.append(out_file)

    return saved_files

if __name__ == "__main__":
    fetch_and_save_revenue()

