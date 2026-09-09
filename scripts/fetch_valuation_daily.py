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

def get_latest_trading_date():
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
    url = "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_d"
    print(f"[{datetime.now()}] 正在抓取 TWSE 上市本益比、殖利率、淨值比...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            print(f"TWSE 回傳 HTTP {resp.status_code}")
            return []
        data = resp.json()
        if not isinstance(data, list) or len(data) == 0:
            return []

        rows = []
        for d in data:
            ticker = str(d.get('Code', '')).strip()
            name = str(d.get('Name', '')).strip()
            if not ticker:
                continue

            pe = clean_float(d.get('PEratio'))
            pb = clean_float(d.get('PBratio'))
            dy = clean_float(d.get('DividendYield'))
            close_price = clean_float(d.get('ClosePrice'))
            quarter = str(d.get('FiscalYearQuarter', '')).strip()

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
        return rows
    except Exception as e:
        print(f"抓取 TWSE 評價面失敗: {e}")
        return []

def fetch_tpex_valuation(date_str):
    url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis"
    print(f"[{datetime.now()}] 正在抓取 TPEx 上櫃本益比、殖利率、淨值比...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            print(f"TPEx 回傳 HTTP {resp.status_code}")
            return []
        data = resp.json()
        if not isinstance(data, list) or len(data) == 0:
            return []

        rows = []
        for d in data:
            ticker = str(d.get('SecuritiesCompanyCode', '')).strip()
            name = str(d.get('CompanyName', '')).strip()
            if not ticker:
                continue

            pe = clean_float(d.get('PriceEarningRatio'))
            pb = clean_float(d.get('PriceBookRatio'))
            dy = clean_float(d.get('YieldRatio'))
            dps = clean_float(d.get('DividendPerShare'))

            rows.append({
                'Date': date_str,
                'Ticker': ticker,
                'Name': name,
                'Market': 'TPEx',
                'Close_Price': np.nan,
                'PE_Ratio': pe,
                'PB_Ratio': pb,
                'Dividend_Yield': dy,
                'Fiscal_Quarter': ''
            })
        print(f"TPEx 上櫃取得 {len(rows)} 檔評價面資料。")
        return rows
    except Exception as e:
        print(f"抓取 TPEx 評價面失敗: {e}")
        return []

def fetch_and_save_valuation(date_str=None):
    if date_str is None:
        date_str = get_latest_trading_date()

    twse_rows = fetch_twse_valuation(date_str)
    tpex_rows = fetch_tpex_valuation(date_str)
    all_rows = twse_rows + tpex_rows

    if not all_rows:
        print(f"[{date_str}] 無評價面資料可落盤。")
        return None

    df = pd.DataFrame(all_rows)
    df.sort_values(by=['Market', 'Ticker'], inplace=True)
    out_file = os.path.join(OUTPUT_DIR, f"{date_str}.parquet")
    df.to_parquet(out_file, engine='pyarrow', compression='snappy', index=False)
    print(f"[{datetime.now()}] 成功儲存 {len(df)} 筆評價面資料至 {out_file}")
    return out_file

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="抓取每日本益比、殖利率與淨值比資料")
    parser.add_argument("--date", type=str, default=None, help="交易日期 (格式: YYYY-MM-DD)")
    args = parser.parse_args()
    fetch_and_save_valuation(args.date)

