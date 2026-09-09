import os
import argparse
import requests
import pandas as pd
import numpy as np
from datetime import datetime

OUTPUT_DIR = "data/market_indices"
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

def fetch_and_save_market_indices(date_str=None):
    url = "https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX"
    print(f"[{datetime.now()}] 正在抓取 TWSE 大盤與類股指數報表...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            print(f"TWSE 回傳 HTTP {resp.status_code}")
            return None
        data = resp.json()
        if not isinstance(data, list) or len(data) == 0:
            return None

        # 從首列提取官方民國日期
        first_row_vals = list(data[0].values())
        raw_date = str(first_row_vals[0]).strip()
        if date_str is None:
            if len(raw_date) >= 6:
                roc_year = int(raw_date[:-4])
                month = raw_date[-4:-2]
                day = raw_date[-2:]
                date_str = f"{roc_year + 1911}-{month}-{day}"
            else:
                date_str = datetime.now().strftime("%Y-%m-%d")

        rows = []
        for d in data:
            vals = list(d.values())
            if len(vals) < 6:
                continue
            index_name = str(vals[1]).strip()
            close_idx = clean_float(vals[2])
            direction = str(vals[3]).strip()
            pts = clean_float(vals[4])
            pct = clean_float(vals[5])
            if direction == '-' and not pd.isna(pts) and pts > 0:
                pts = -pts

            rows.append({
                'Date': date_str,
                'Index_Name': index_name,
                'Close_Index': close_idx,
                'Change_Points': pts,
                'Change_Percent': pct
            })

        df = pd.DataFrame(rows)
        out_file = os.path.join(OUTPUT_DIR, f"{date_str}.parquet")
        df.to_parquet(out_file, engine='pyarrow', compression='snappy', index=False)
        print(f"[{datetime.now()}] 成功儲存 {len(df)} 筆大盤與產業指數至 {out_file}")
        return out_file
    except Exception as e:
        print(f"抓取大盤指數失敗: {e}")
        return None

if __name__ == "__main__":
    fetch_and_save_market_indices()

