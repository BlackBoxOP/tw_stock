import os
import re
import argparse
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

OUTPUT_DIR = "data/institutional"
os.makedirs(OUTPUT_DIR, exist_ok=True)

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

def get_latest_official_date():
    """向 TWSE MI_INDEX 查詢目前最新官方收盤交易日 (避免誤標未收盤日期)"""
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
    return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

def fetch_twse_institutional(date_str):
    """
    抓取 TWSE (上市) 三大法人買賣超 (T86)，嚴格校驗資料日期
    """
    yyyymmdd = date_str.replace('-', '')
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={yyyymmdd}&selectType=ALL"
    print(f"[{datetime.now()}] 正在抓取 TWSE 上市三大法人買賣超 ({date_str})...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            print(f"TWSE 回傳異常狀態碼: {resp.status_code}")
            return [], None
        res_json = resp.json()
        if res_json.get('stat') != 'OK' or not res_json.get('data'):
            print(f"TWSE 無 {date_str} 資料 (stat: {res_json.get('stat')})")
            return [], None

        actual_date_raw = str(res_json.get('date', '')).strip()
        if actual_date_raw and actual_date_raw != yyyymmdd:
            print(f"TWSE 日期不符：請求 {yyyymmdd} 但回傳 {actual_date_raw}，略過以防誤標。")
            return [], None

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
        print(f"TWSE 上市取得 {len(rows)} 檔標的。")
        return rows, date_str
    except Exception as e:
        print(f"抓取 TWSE 失敗: {e}")
        return [], None

def fetch_tpex_institutional(date_str):
    """
    抓取 TPEx (上櫃) 三大法人買賣超，傳入指定日期並校驗回傳日期
    """
    date_slash = date_str.replace('-', '/')
    url = f"https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade?type=Daily&sect=EW&date={date_slash}&response=json"
    print(f"[{datetime.now()}] 正在抓取 TPEx 上櫃三大法人買賣超 ({date_str})...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            print(f"TPEx 回傳異常狀態碼: {resp.status_code}")
            return [], None
        data = resp.json()
        if data.get('stat') != 'ok' or 'tables' not in data or len(data['tables']) == 0:
            print(f"TPEx 無 {date_str} 資料 (stat: {data.get('stat')})")
            return [], None

        actual_date_raw = str(data.get('date', '')).strip()
        yyyymmdd = date_str.replace('-', '')
        if actual_date_raw and actual_date_raw != yyyymmdd:
            print(f"TPEx 日期不符：請求 {yyyymmdd} 但回傳 {actual_date_raw}，略過以防誤標。")
            return [], None

        raw_rows = data['tables'][0].get('data', [])
        rows = []
        for d in raw_rows:
            if len(d) < 24:
                continue
            ticker = str(d[0]).strip()
            name = str(d[1]).strip()
            if not ticker:
                continue

            rows.append({
                'Date': date_str,
                'Ticker': ticker,
                'Name': name,
                'Market': 'TPEx',
                'Foreign_Buy': clean_num(d[2]),
                'Foreign_Sell': clean_num(d[3]),
                'Foreign_Net': clean_num(d[4]),
                'Foreign_Dealer_Net': clean_num(d[7]),
                'Trust_Buy': clean_num(d[11]),
                'Trust_Sell': clean_num(d[12]),
                'Trust_Net': clean_num(d[13]),
                'Dealer_Self_Net': clean_num(d[16]),
                'Dealer_Hedge_Net': clean_num(d[19]),
                'Dealer_Net': clean_num(d[22]),
                'Total_Net': clean_num(d[23]),
            })
        print(f"TPEx 上櫃取得 {len(rows)} 檔標的。")
        return rows, date_str
    except Exception as e:
        print(f"抓取 TPEx 失敗: {e}")
        return [], None

def fetch_and_save_institutional(date_str=None, overwrite=True):
    if date_str is None:
        date_str = get_latest_official_date()

    out_file = os.path.join(OUTPUT_DIR, f"{date_str}.parquet")
    if os.path.exists(out_file) and not overwrite:
        print(f"[{date_str}] 三大法人檔案已存在，略過。")
        return out_file
    
    twse_rows, twse_dt = fetch_twse_institutional(date_str)
    tpex_rows, tpex_dt = fetch_tpex_institutional(date_str)
    all_rows = twse_rows + tpex_rows

    if not all_rows:
        print(f"[{date_str}] 無任何三大法人資料可落盤。")
        return None

    df = pd.DataFrame(all_rows)
    df.sort_values(by=['Market', 'Ticker'], inplace=True)
    df.to_parquet(out_file, engine='pyarrow', compression='snappy', index=False)
    print(f"[{datetime.now()}] 成功儲存 {len(df)} 筆三大法人買賣超資料至 {out_file} (上市: {len(twse_rows)}, 上櫃: {len(tpex_rows)})")
    return out_file

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="抓取每日三大法人買賣超資料 (嚴格日期校驗)")
    parser.add_argument("--date", type=str, default=None, help="交易日期 (格式: YYYY-MM-DD)")
    args = parser.parse_args()
    fetch_and_save_institutional(args.date)
