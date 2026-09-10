import os
import re
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
    s = re.sub(r'<[^>]+>', '', str(val)).replace(',', '').strip()
    if not s or s == '--' or s == '-':
        return np.nan
    try:
        return round(float(s), 4)
    except ValueError:
        return np.nan

def get_latest_official_date():
    """透過 TWSE MI_INDEX 查詢官方最新已結算交易日 (格式 YYYY-MM-DD)"""
    try:
        r = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX", headers=HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and len(data) > 0:
                raw_date = list(data[0].values())[0]
                if len(raw_date) >= 6:
                    roc_year = int(raw_date[:-4])
                    month = raw_date[-4:-2]
                    day = raw_date[-2:]
                    return f"{roc_year + 1911}-{month}-{day}"
    except Exception:
        pass
    return datetime.now().strftime("%Y-%m-%d")

def fetch_and_save_market_indices(date_str=None, overwrite=True):
    """
    抓取 TWSE 大盤與類股指數報表，嚴格比對回傳日期
    端點: https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={YYYYMMDD}&type=IND&response=json
    """
    if date_str is None:
        date_str = get_latest_official_date()

    out_file = os.path.join(OUTPUT_DIR, f"{date_str}.parquet")
    if os.path.exists(out_file) and not overwrite:
        print(f"[{date_str}] 大盤指數檔案已存在，略過。")
        return out_file

    yyyymmdd = date_str.replace('-', '')
    url = f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={yyyymmdd}&type=IND&response=json"
    print(f"[{datetime.now()}] 正在抓取 TWSE 大盤與產業指數 ({date_str})...")

    rows = []
    try:
        resp = requests.get(url, headers=HEADERS, timeout=25)
        if resp.status_code == 200:
            res_json = resp.json()
            actual_date_raw = str(res_json.get('date', '')).strip()

            if actual_date_raw and actual_date_raw == yyyymmdd and 'tables' in res_json:
                for t in res_json['tables']:
                    for d in t.get('data', []):
                        if len(d) < 5:
                            continue
                        name = str(d[0]).strip()
                        close_idx = clean_float(d[1])
                        direction_str = str(d[2])
                        pts = clean_float(d[3])
                        pct = clean_float(d[4])
                        if '-' in direction_str and not pd.isna(pts) and pts > 0:
                            pts = -pts

                        rows.append({
                            'Date': date_str,
                            'Index_Name': name,
                            'Close_Index': close_idx,
                            'Change_Points': pts,
                            'Change_Percent': pct
                        })
            elif actual_date_raw and actual_date_raw != yyyymmdd:
                print(f"TWSE 日期不符：請求 {yyyymmdd} 但回傳 {actual_date_raw}，略過以防誤標。")
                return None
    except Exception as e:
        print(f"自 TWSE Web 端點查詢指數異常: {e}")

    # 若 Web 端點未取到，且目標日期恰好等於 OpenAPI 當前官方日期，嘗試 OpenAPI
    if not rows and date_str == get_latest_official_date():
        print(f"嘗試自 TWSE OpenAPI 抓取 {date_str} 指數資料...")
        try:
            r = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX", headers=HEADERS, timeout=20)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and len(data) > 0:
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
        except Exception as e:
            print(f"自 TWSE OpenAPI 抓取失敗: {e}")

    if not rows:
        print(f"[{date_str}] 無大盤與產業指數資料可落盤。")
        return None

    df = pd.DataFrame(rows)
    df.to_parquet(out_file, engine='pyarrow', compression='snappy', index=False)
    print(f"[{datetime.now()}] 成功儲存 {len(df)} 筆大盤與產業指數至 {out_file}")
    return out_file

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="抓取每日大盤與類股指數報表 (嚴格日期校驗)")
    parser.add_argument("--date", type=str, default=None, help="交易日期 (格式: YYYY-MM-DD)")
    args = parser.parse_args()
    fetch_and_save_market_indices(args.date)
