import os
import argparse
import requests
import pandas as pd
import numpy as np
from datetime import datetime

OUTPUT_DIR = "data/valuation"
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

def fetch_twse_valuation(date_str):
    """
    抓取 TWSE (上市) 本益比、殖利率、淨值比，嚴格比對回傳日期
    端點: https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d?date={YYYYMMDD}&selectType=ALL&response=json
    """
    yyyymmdd = date_str.replace('-', '')
    url = f"https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d?date={yyyymmdd}&selectType=ALL&response=json"
    print(f"[{datetime.now()}] 正在抓取 TWSE 上市評價面資料 ({date_str})...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=25)
        if resp.status_code != 200:
            print(f"TWSE 回傳異常狀態碼: {resp.status_code}")
            return [], None
        res_json = resp.json()
        if res_json.get('stat') != 'OK' or not res_json.get('data'):
            print(f"TWSE 無 {date_str} 評價面資料 (stat: {res_json.get('stat')})")
            return [], None

        actual_date_raw = str(res_json.get('date', '')).strip()
        if actual_date_raw and actual_date_raw != yyyymmdd:
            print(f"TWSE 日期不符：請求 {yyyymmdd} 但回傳 {actual_date_raw}，略過以防誤標。")
            return [], None

        rows = []
        for d in res_json['data']:
            if len(d) < 8:
                continue
            ticker = str(d[0]).strip()
            name = str(d[1]).strip()
            if not ticker:
                continue

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
        print(f"TWSE 上市取得 {len(rows)} 檔評價面資料。")
        return rows, date_str
    except Exception as e:
        print(f"抓取 TWSE 評價面失敗: {e}")
        return [], None

def fetch_tpex_valuation(date_str):
    """
    抓取 TPEx (上櫃) 本益比、殖利率、淨值比，嚴格比對回傳日期
    端點: https://www.tpex.org.tw/www/zh-tw/afterTrading/peQryDate?date={YYYY/MM/DD}&response=json
    """
    date_slash = date_str.replace('-', '/')
    yyyymmdd = date_str.replace('-', '')
    url = f"https://www.tpex.org.tw/www/zh-tw/afterTrading/peQryDate?date={date_slash}&response=json"
    print(f"[{datetime.now()}] 正在抓取 TPEx 上櫃評價面資料 ({date_str})...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=25)
        if resp.status_code != 200:
            print(f"TPEx 回傳異常狀態碼: {resp.status_code}")
            return [], None
        res_json = resp.json()
        if res_json.get('stat') != 'ok' or 'tables' not in res_json or len(res_json['tables']) == 0:
            print(f"TPEx 無 {date_str} 評價面資料 (stat: {res_json.get('stat')})")
            return [], None

        actual_date_raw = str(res_json.get('date', '')).strip()
        if actual_date_raw and actual_date_raw != yyyymmdd:
            print(f"TPEx 日期不符：請求 {yyyymmdd} 但回傳 {actual_date_raw}，略過以防誤標。")
            return [], None

        raw_rows = res_json['tables'][0].get('data', [])
        rows = []
        for d in raw_rows:
            if len(d) < 8:
                continue
            ticker = str(d[0]).strip()
            name = str(d[1]).strip()
            if not ticker:
                continue

            pe = clean_float(d[2])
            dy = clean_float(d[5])
            pb = clean_float(d[6])
            quarter = str(d[7]).strip()

            rows.append({
                'Date': date_str,
                'Ticker': ticker,
                'Name': name,
                'Market': 'TPEx',
                'Close_Price': np.nan,
                'PE_Ratio': pe,
                'PB_Ratio': pb,
                'Dividend_Yield': dy,
                'Fiscal_Quarter': quarter
            })
        print(f"TPEx 上櫃取得 {len(rows)} 檔評價面資料。")
        return rows, date_str
    except Exception as e:
        print(f"抓取 TPEx 評價面失敗: {e}")
        return [], None

def fetch_and_save_valuation(date_str=None, overwrite=True):
    if date_str is None:
        date_str = get_latest_official_date()

    out_file = os.path.join(OUTPUT_DIR, f"{date_str}.parquet")
    if os.path.exists(out_file) and not overwrite:
        print(f"[{date_str}] 評價面檔案已存在，略過。")
        return out_file

    twse_rows, twse_dt = fetch_twse_valuation(date_str)
    tpex_rows, tpex_dt = fetch_tpex_valuation(date_str)
    all_rows = twse_rows + tpex_rows

    if not all_rows:
        print(f"[{date_str}] 無評價面資料可落盤。")
        return None

    df = pd.DataFrame(all_rows)
    df.sort_values(by=['Market', 'Ticker'], inplace=True)
    df.to_parquet(out_file, engine='pyarrow', compression='snappy', index=False)
    print(f"[{datetime.now()}] 成功儲存 {len(df)} 筆評價面資料至 {out_file} (上市: {len(twse_rows)}, 上櫃: {len(tpex_rows)})")
    return out_file

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="抓取每日本益比、殖利率、淨值比 (嚴格日期校驗)")
    parser.add_argument("--date", type=str, default=None, help="交易日期 (格式: YYYY-MM-DD)")
    args = parser.parse_args()
    fetch_and_save_valuation(args.date)
