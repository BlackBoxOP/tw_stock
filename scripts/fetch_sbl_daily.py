"""
借券賣出與信用總量管制 (Securities Lending & Borrowing / SBL) 服務層
資料來源: 臺灣證券交易所 TWT93U (信用額度總量管制餘額表)
涵蓋融券與全市場借券賣出當日餘額、賣出股數、還券股數與額度限額
外資與大戶放空與避險核心指標
"""
import os
import re
import argparse
import requests
import pandas as pd
import numpy as np
from datetime import datetime

OUTPUT_DIR = "data/margin/sbl"
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
    """透過 TWSE MI_INDEX 查詢官方最新已結算交易日"""
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

def fetch_twse_sbl(date_str):
    """
    抓取指定日期信用額度總量管制與借券賣出餘額 (TWT93U)
    端點: https://www.twse.com.tw/rwd/zh/marginTrading/TWT93U?date={YYYYMMDD}&response=json
    """
    yyyymmdd = date_str.replace('-', '')
    url = f"https://www.twse.com.tw/rwd/zh/marginTrading/TWT93U?date={yyyymmdd}&response=json"
    print(f"[{datetime.now()}] 正在自 TWSE 抓取信用總量管制與借券賣出明細 ({date_str})...")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=25)
        if resp.status_code != 200:
            print(f"TWSE 回傳異常狀態碼: {resp.status_code}")
            return [], None

        res_json = resp.json()
        if res_json.get('stat') != 'OK' or not res_json.get('data'):
            print(f"TWSE 無 {date_str} 借券賣出資料 (stat: {res_json.get('stat')})")
            return [], None

        actual_date_raw = str(res_json.get('date', '')).strip()
        if actual_date_raw and actual_date_raw != yyyymmdd:
            print(f"TWSE 日期不符：請求 {yyyymmdd} 但回傳 {actual_date_raw}，略過以防誤標。")
            return [], None

        rows = []
        for d in res_json['data']:
            if len(d) < 14:
                continue
            ticker = str(d[0]).strip()
            name = str(d[1]).strip()
            if not ticker or len(ticker) < 2:
                continue

            # 融券餘額
            margin_short_bal = clean_num(d[6])
            margin_short_limit = clean_num(d[7])

            # 借券賣出 (SBL)
            sbl_prev = clean_num(d[8])
            sbl_sell = clean_num(d[9])
            sbl_return = clean_num(d[10])
            sbl_adjust = clean_num(d[11])
            sbl_bal = clean_num(d[12])
            sbl_limit = clean_num(d[13])
            sbl_net_change = sbl_sell - sbl_return

            rows.append({
                'Date': date_str,
                'Ticker': ticker,
                'Name': name,
                'Margin_Short_Balance': margin_short_bal,
                'Margin_Short_Limit': margin_short_limit,
                'SBL_Prev_Balance': sbl_prev,
                'SBL_Daily_Sell': sbl_sell,
                'SBL_Daily_Return': sbl_return,
                'SBL_Daily_Adjust': sbl_adjust,
                'SBL_Balance': sbl_bal,
                'SBL_Net_Change': sbl_net_change,
                'SBL_Next_Day_Limit': sbl_limit,
            })

        print(f"TWSE 取得 {len(rows)} 檔信用與借券賣出資料。")
        return rows, date_str
    except Exception as e:
        print(f"抓取 TWSE 借券賣出失敗: {e}")
        return [], None

def fetch_and_save_sbl(date_str=None, overwrite=True):
    if date_str is None:
        date_str = get_latest_official_date()

    out_file = os.path.join(OUTPUT_DIR, f"{date_str}.parquet")
    if os.path.exists(out_file) and not overwrite:
        print(f"[{date_str}] 借券賣出檔案已存在，略過。")
        return out_file

    rows, dt = fetch_twse_sbl(date_str)
    if not rows:
        print(f"[{date_str}] 無借券賣出資料可落盤。")
        return None

    df = pd.DataFrame(rows)
    df.sort_values(by='Ticker', inplace=True)
    df.to_parquet(out_file, engine='pyarrow', compression='snappy', index=False)
    print(f"[{datetime.now()}] 成功儲存 {len(df)} 筆借券賣出資料至 {out_file}")
    return out_file

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="抓取每日借券賣出與信用總量管制明細 (嚴格日期校驗)")
    parser.add_argument("--date", type=str, default=None, help="交易日期 (格式: YYYY-MM-DD)")
    args = parser.parse_args()
    fetch_and_save_sbl(args.date)
