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
    s = str(val).replace(',', '').strip()
    if not s or s == '--':
        return 0
    try:
        return int(s)
    except ValueError:
        try:
            return int(float(s))
        except ValueError:
            return 0

def get_latest_trading_date():
    """透過 TWSE MI_INDEX 取得最近官方交易日 (格式 YYYY-MM-DD)"""
    try:
        r = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX", headers=HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data, list) and len(data) > 0:
                raw_date = list(data[0].values())[0]  # 民國年月日，如 "1150908"
                if len(raw_date) >= 6:
                    roc_year = int(raw_date[:-4])
                    month = raw_date[-4:-2]
                    day = raw_date[-2:]
                    return f"{roc_year + 1911}-{month}-{day}"
    except Exception:
        pass
    return datetime.now().strftime("%Y-%m-%d")

def fetch_twse_institutional(date_str):
    """
    抓取 TWSE (上市) 三大法人買賣超 (T86)
    date_str: 'YYYY-MM-DD'
    """
    yyyymmdd = date_str.replace('-', '')
    url = f"https://www.twse.com.tw/rwd/zh/fund/T86?response=json&date={yyyymmdd}&selectType=ALL"
    print(f"[{datetime.now()}] 正在抓取 TWSE 上市三大法人買賣超: {date_str}...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            print(f"TWSE 回傳 HTTP {resp.status_code}")
            return []
        res_json = resp.json()
        if res_json.get('stat') != 'OK' or not res_json.get('data'):
            print(f"TWSE 無 {date_str} 三大法人資料: {res_json.get('stat')}")
            return []
        
        rows = []
        for d in res_json['data']:
            if len(d) < 19:
                continue
            ticker = str(d[0]).strip()
            name = str(d[1]).strip()
            rows.append({
                'Date': date_str,
                'Ticker': ticker,
                'Name': name,
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
        print(f"TWSE 上市取得 {len(rows)} 檔標的三大法人資料。")
        return rows
    except Exception as e:
        print(f"抓取 TWSE 失敗: {e}")
        return []

def fetch_tpex_institutional(date_str):
    """
    抓取 TPEx (上櫃) 三大法人買賣超
    """
    url = "https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading"
    print(f"[{datetime.now()}] 正在抓取 TPEx 上櫃三大法人買賣超...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            print(f"TPEx 回傳 HTTP {resp.status_code}")
            return []
        data = resp.json()
        if not isinstance(data, list) or len(data) == 0:
            print(f"TPEx 無回傳資料")
            return []

        rows = []
        for d in data:
            ticker = str(d.get('SecuritiesCompanyCode', '')).strip()
            name = str(d.get('CompanyName', '')).strip()
            if not ticker:
                continue
            
            # 解析外資買賣
            foreign_buy = clean_num(d.get('Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Total Buy'))
            foreign_sell = clean_num(d.get(' Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Total Sell'))
            foreign_net = clean_num(d.get('Foreign Investors include Mainland Area Investors (Foreign Dealers excluded)-Difference'))
            foreign_dealer_net = clean_num(d.get('ForeignDealers-Difference'))

            # 投信
            trust_buy = clean_num(d.get('SecuritiesInvestmentTrustCompanies-TotalBuy'))
            trust_sell = clean_num(d.get('SecuritiesInvestmentTrustCompanies-TotalSell'))
            trust_net = clean_num(d.get('SecuritiesInvestmentTrustCompanies-Difference'))

            # 自營商
            dealer_net = clean_num(d.get('Dealers-Difference'))
            total_net = clean_num(d.get('TotalDifference'))

            rows.append({
                'Date': date_str,
                'Ticker': ticker,
                'Name': name,
                'Market': 'TPEx',
                'Foreign_Buy': foreign_buy,
                'Foreign_Sell': foreign_sell,
                'Foreign_Net': foreign_net,
                'Foreign_Dealer_Net': foreign_dealer_net,
                'Trust_Buy': trust_buy,
                'Trust_Sell': trust_sell,
                'Trust_Net': trust_net,
                'Dealer_Self_Net': 0,
                'Dealer_Hedge_Net': 0,
                'Dealer_Net': dealer_net,
                'Total_Net': total_net,
            })
        print(f"TPEx 上櫃取得 {len(rows)} 檔標的三大法人資料。")
        return rows
    except Exception as e:
        print(f"抓取 TPEx 失敗: {e}")
        return []

def fetch_and_save_institutional(date_str=None):
    if date_str is None:
        date_str = get_latest_trading_date()
    
    twse_rows = fetch_twse_institutional(date_str)
    tpex_rows = fetch_tpex_institutional(date_str)
    all_rows = twse_rows + tpex_rows

    if not all_rows:
        print(f"[{date_str}] 無任何法人資料可落盤。")
        return None

    df = pd.DataFrame(all_rows)
    df.sort_values(by=['Market', 'Ticker'], inplace=True)
    out_file = os.path.join(OUTPUT_DIR, f"{date_str}.parquet")
    df.to_parquet(out_file, engine='pyarrow', compression='snappy', index=False)
    print(f"[{datetime.now()}] 成功儲存 {len(df)} 筆三大法人買賣超資料至 {out_file}")
    return out_file

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="抓取每日三大法人買賣超資料")
    parser.add_argument("--date", type=str, default=None, help="交易日期 (格式: YYYY-MM-DD)")
    args = parser.parse_args()
    fetch_and_save_institutional(args.date)

