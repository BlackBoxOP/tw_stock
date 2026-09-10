import os
import argparse
import requests
import pandas as pd
import numpy as np
from datetime import datetime

OUTPUT_DIR = "data/margin"
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
        return 0.0
    s = str(val).replace(',', '').strip()
    if not s or s == '--' or s == '-':
        return 0.0
    try:
        return round(float(s), 4)
    except ValueError:
        return 0.0

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

def fetch_twse_margin(date_str):
    """
    抓取 TWSE (上市) 融資融券餘額，嚴格比對回傳日期
    端點: https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={YYYYMMDD}&selectType=ALL&response=json
    """
    yyyymmdd = date_str.replace('-', '')
    url = f"https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={yyyymmdd}&selectType=ALL&response=json"
    print(f"[{datetime.now()}] 正在抓取 TWSE 上市融資融券餘額 ({date_str})...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=25)
        if resp.status_code != 200:
            print(f"TWSE 回傳異常狀態碼: {resp.status_code}")
            return [], None
        res_json = resp.json()
        if res_json.get('stat') != 'OK' or 'tables' not in res_json or len(res_json['tables']) < 2:
            print(f"TWSE 無 {date_str} 融資融券資料 (stat: {res_json.get('stat')})")
            return [], None

        actual_date_raw = str(res_json.get('date', '')).strip()
        if actual_date_raw and actual_date_raw != yyyymmdd:
            print(f"TWSE 日期不符：請求 {yyyymmdd} 但回傳 {actual_date_raw}，略過以防誤標。")
            return [], None

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
        print(f"TWSE 上市取得 {len(rows)} 檔融資融券資料。")
        return rows, date_str
    except Exception as e:
        print(f"抓取 TWSE 融資融券失敗: {e}")
        return [], None

def fetch_tpex_margin(date_str):
    """
    抓取 TPEx (上櫃) 融資融券餘額，嚴格比對回傳日期
    端點: https://www.tpex.org.tw/www/zh-tw/margin/balance?date={YYYY/MM/DD}&response=json
    """
    date_slash = date_str.replace('-', '/')
    yyyymmdd = date_str.replace('-', '')
    url = f"https://www.tpex.org.tw/www/zh-tw/margin/balance?date={date_slash}&response=json"
    print(f"[{datetime.now()}] 正在抓取 TPEx 上櫃融資融券餘額 ({date_str})...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=25)
        if resp.status_code != 200:
            print(f"TPEx 回傳異常狀態碼: {resp.status_code}")
            return [], None
        res_json = resp.json()
        if res_json.get('stat') != 'ok' or 'tables' not in res_json or len(res_json['tables']) == 0:
            print(f"TPEx 無 {date_str} 融資融券資料 (stat: {res_json.get('stat')})")
            return [], None

        actual_date_raw = str(res_json.get('date', '')).strip()
        if actual_date_raw and actual_date_raw != yyyymmdd:
            print(f"TPEx 日期不符：請求 {yyyymmdd} 但回傳 {actual_date_raw}，略過以防誤標。")
            return [], None

        raw_rows = res_json['tables'][0].get('data', [])
        rows = []
        for d in raw_rows:
            if len(d) < 19:
                continue
            ticker = str(d[0]).strip()
            name = str(d[1]).strip()
            if not ticker:
                continue

            m_prev_bal = clean_num(d[2])
            m_buy = clean_num(d[3])
            m_sell = clean_num(d[4])
            m_cash_repay = clean_num(d[5])
            m_bal = clean_num(d[6])
            m_util = clean_float(d[8])
            m_limit = clean_num(d[9])

            s_prev_bal = clean_num(d[10])
            s_sell = clean_num(d[11])
            s_buy = clean_num(d[12])
            s_stock_repay = clean_num(d[13])
            s_bal = clean_num(d[14])
            s_util = clean_float(d[16])
            s_limit = clean_num(d[17])

            offset = clean_num(d[18])

            rows.append({
                'Date': date_str,
                'Ticker': ticker,
                'Name': name,
                'Market': 'TPEx',
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
        print(f"TPEx 上櫃取得 {len(rows)} 檔融資融券資料。")
        return rows, date_str
    except Exception as e:
        print(f"抓取 TPEx 融資融券失敗: {e}")
        return [], None

def fetch_and_save_margin(date_str=None, overwrite=True):
    if date_str is None:
        date_str = get_latest_official_date()

    out_file = os.path.join(OUTPUT_DIR, f"{date_str}.parquet")
    if os.path.exists(out_file) and not overwrite:
        print(f"[{date_str}] 融資融券檔案已存在，略過。")
        return out_file

    twse_rows, twse_dt = fetch_twse_margin(date_str)
    tpex_rows, tpex_dt = fetch_tpex_margin(date_str)
    all_rows = twse_rows + tpex_rows

    if not all_rows:
        print(f"[{date_str}] 無融資融券資料可落盤。")
        return None

    df = pd.DataFrame(all_rows)
    df.sort_values(by=['Market', 'Ticker'], inplace=True)
    df.to_parquet(out_file, engine='pyarrow', compression='snappy', index=False)
    print(f"[{datetime.now()}] 成功儲存 {len(df)} 筆融資融券資料至 {out_file} (上市: {len(twse_rows)}, 上櫃: {len(tpex_rows)})")
    return out_file

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="抓取每日融資融券信用交易資料 (嚴格日期校驗)")
    parser.add_argument("--date", type=str, default=None, help="交易日期 (格式: YYYY-MM-DD)")
    args = parser.parse_args()
    fetch_and_save_margin(args.date)
