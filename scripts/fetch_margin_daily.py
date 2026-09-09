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
    if not s or s == '--':
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
    if not s or s == '--':
        return 0.0
    try:
        return round(float(s), 4)
    except ValueError:
        return 0.0

def get_latest_trading_date():
    """透過 TWSE MI_INDEX 取得最近官方交易日 (格式 YYYY-MM-DD)"""
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
    url = "https://openapi.twse.com.tw/v1/exchangeReport/MI_MARGN"
    print(f"[{datetime.now()}] 正在抓取 TWSE 上市融資融券餘額...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            print(f"TWSE 回傳 HTTP {resp.status_code}")
            return []
        data = resp.json()
        if not isinstance(data, list) or len(data) == 0:
            print("TWSE 無融資融券資料")
            return []

        rows = []
        for d in data:
            values = list(d.values())
            if len(values) < 15:
                continue
            ticker = str(values[0]).strip()
            name = str(values[1]).strip()
            if not ticker or len(ticker) < 2:
                continue

            m_buy = clean_num(values[2])
            m_sell = clean_num(values[3])
            m_cash_repay = clean_num(values[4])
            m_prev_bal = clean_num(values[5])
            m_bal = clean_num(values[6])
            m_limit = clean_num(values[7])
            m_util = round(m_bal / m_limit * 100, 2) if m_limit > 0 else 0.0

            s_buy = clean_num(values[8])
            s_sell = clean_num(values[9])
            s_stock_repay = clean_num(values[10])
            s_prev_bal = clean_num(values[11])
            s_bal = clean_num(values[12])
            s_limit = clean_num(values[13])
            s_util = round(s_bal / s_limit * 100, 2) if s_limit > 0 else 0.0

            offset = clean_num(values[14])

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
        return rows
    except Exception as e:
        print(f"抓取 TWSE 融資融券失敗: {e}")
        return []

def fetch_tpex_margin(date_str):
    url = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_margin_balance"
    print(f"[{datetime.now()}] 正在抓取 TPEx 上櫃融資融券餘額...")
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            print(f"TPEx 回傳 HTTP {resp.status_code}")
            return []
        data = resp.json()
        if not isinstance(data, list) or len(data) == 0:
            print("TPEx 無融資融券資料")
            return []

        rows = []
        for d in data:
            ticker = str(d.get('SecuritiesCompanyCode', '')).strip()
            name = str(d.get('CompanyName', '')).strip()
            if not ticker:
                continue

            m_buy = clean_num(d.get('MarginPurchase'))
            m_sell = clean_num(d.get('MarginSales'))
            m_cash_repay = clean_num(d.get('CashRedemption'))
            m_prev_bal = clean_num(d.get('MarginPurchaseBalancePreviousDay'))
            m_bal = clean_num(d.get('MarginPurchaseBalance'))
            m_limit = clean_num(d.get('MarginPurchaseQuota'))
            m_util = clean_float(d.get('MarginPurchaseUtilizationRate'))

            s_buy = clean_num(d.get('ShortConvering'))
            s_sell = clean_num(d.get('ShortSale'))
            s_stock_repay = clean_num(d.get('StockRedemption'))
            s_prev_bal = clean_num(d.get('ShortSaleBalancePreviousDay'))
            s_bal = clean_num(d.get('ShortSaleBalance'))
            s_limit = clean_num(d.get('ShortSaleQuota'))
            s_util = clean_float(d.get('ShortSaleUtilizationRate'))

            offset = clean_num(d.get('Offsetting'))

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
        return rows
    except Exception as e:
        print(f"抓取 TPEx 融資融券失敗: {e}")
        return []

def fetch_and_save_margin(date_str=None):
    if date_str is None:
        date_str = get_latest_trading_date()

    twse_rows = fetch_twse_margin(date_str)
    tpex_rows = fetch_tpex_margin(date_str)
    all_rows = twse_rows + tpex_rows

    if not all_rows:
        print(f"[{date_str}] 無融資融券資料可落盤。")
        return None

    df = pd.DataFrame(all_rows)
    df.sort_values(by=['Market', 'Ticker'], inplace=True)
    out_file = os.path.join(OUTPUT_DIR, f"{date_str}.parquet")
    df.to_parquet(out_file, engine='pyarrow', compression='snappy', index=False)
    print(f"[{datetime.now()}] 成功儲存 {len(df)} 筆融資融券資料至 {out_file}")
    return out_file

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="抓取每日融資融券信用交易資料")
    parser.add_argument("--date", type=str, default=None, help="交易日期 (格式: YYYY-MM-DD)")
    args = parser.parse_args()
    fetch_and_save_margin(args.date)

