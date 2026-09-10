"""
期交所 (TAIFEX) 三大法人期貨交易與未平倉部位服務層
資料來源: 臺灣期貨交易所 (taifex.com.tw)
提供臺股期貨 (大台)、小型臺指期貨 (小台)、電子期、金融期之三大法人未平倉與多空口數
嚴格校驗期交所官方公佈日期，杜絕資料誤標
"""
import os
import re
import argparse
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from bs4 import BeautifulSoup

OUTPUT_DIR = "data/taifex/institutional"
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def clean_num(val):
    if val is None or pd.isna(val):
        return 0
    s = re.sub(r'[^\d\-]', '', str(val).strip())
    if not s or s == '-':
        return 0
    try:
        return int(s)
    except ValueError:
        try:
            return int(float(s))
        except ValueError:
            return 0

def get_latest_official_date():
    """向 TWSE MI_INDEX 查詢官方最新已結算交易日"""
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

def fetch_taifex_futures_institutional(date_str):
    """
    抓取指定日期期貨三大法人多空與未平倉部位
    端點: https://www.taifex.com.tw/cht/3/futContractsDate?queryDate={YYYY/MM/DD}
    """
    date_slash = date_str.replace('-', '/')
    url = f"https://www.taifex.com.tw/cht/3/futContractsDate?queryDate={date_slash}"
    print(f"[{datetime.now()}] 正在自 TAIFEX 抓取三大法人期貨未平倉部位 ({date_str})...")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=25)
        if resp.status_code != 200:
            print(f"TAIFEX 回傳異常狀態碼: {resp.status_code}")
            return [], None

        html = resp.text
        date_match = re.search(r'class=.right.[^>]*>.*?(\d{4}/\d{2}/\d{2})', html, re.DOTALL)
        if not date_match:
            print(f"TAIFEX 無 {date_str} 資料 (未找到官方結算日期)")
            return [], None

        actual_date_slash = date_match.group(1).strip()
        actual_date = actual_date_slash.replace('/', '-')
        if actual_date != date_str:
            print(f"TAIFEX 日期不符：請求 {date_str} 但回傳 {actual_date}，略過以防誤標。")
            return [], None

        soup = BeautifulSoup(html, 'html.parser')
        tables = soup.find_all('table')
        if not tables:
            print(f"TAIFEX 無表格資料")
            return [], None

        main_table = tables[0]
        rows = []
        cur_commodity = ''

        for tr in main_table.find_all('tr'):
            tds = [td.get_text(strip=True) for td in tr.find_all(['td', 'th'])]
            if not tds:
                continue

            # 判斷是否為商品起始列 (長度為 15)
            if len(tds) == 15 and tds[0].isdigit():
                cur_commodity = tds[1]
                inst = tds[2]
                buy_vol, buy_amt = clean_num(tds[3]), clean_num(tds[4])
                sell_vol, sell_amt = clean_num(tds[5]), clean_num(tds[6])
                net_vol, net_amt = clean_num(tds[7]), clean_num(tds[8])
                oi_long_vol, oi_long_amt = clean_num(tds[9]), clean_num(tds[10])
                oi_short_vol, oi_short_amt = clean_num(tds[11]), clean_num(tds[12])
                oi_net_vol, oi_net_amt = clean_num(tds[13]), clean_num(tds[14])
            # 商品後續列 (長度為 13)
            elif len(tds) == 13 and cur_commodity:
                inst = tds[0]
                buy_vol, buy_amt = clean_num(tds[1]), clean_num(tds[2])
                sell_vol, sell_amt = clean_num(tds[3]), clean_num(tds[4])
                net_vol, net_amt = clean_num(tds[5]), clean_num(tds[6])
                oi_long_vol, oi_long_amt = clean_num(tds[7]), clean_num(tds[8])
                oi_short_vol, oi_short_amt = clean_num(tds[9]), clean_num(tds[10])
                oi_net_vol, oi_net_amt = clean_num(tds[11]), clean_num(tds[12])
            else:
                continue

            # 正規化機構名稱
            inst_clean = inst.replace('及陸資', '').strip()

            rows.append({
                'Date': date_str,
                'Commodity': cur_commodity,
                'Institution': inst_clean,
                'Buy_Volume': buy_vol,
                'Buy_Amount': buy_amt,
                'Sell_Volume': sell_vol,
                'Sell_Amount': sell_amt,
                'Net_Volume': net_vol,
                'Net_Amount': net_amt,
                'OI_Long_Volume': oi_long_vol,
                'OI_Long_Amount': oi_long_amt,
                'OI_Short_Volume': oi_short_vol,
                'OI_Short_Amount': oi_short_amt,
                'OI_Net_Volume': oi_net_vol,
                'OI_Net_Amount': oi_net_amt,
            })

        print(f"TAIFEX 取得 {len(rows)} 筆法人期貨部位資料。")
        return rows, date_str
    except Exception as e:
        print(f"抓取 TAIFEX 失敗: {e}")
        return [], None

def fetch_and_save_taifex(date_str=None, overwrite=True):
    if date_str is None:
        date_str = get_latest_official_date()

    out_file = os.path.join(OUTPUT_DIR, f"{date_str}.parquet")
    if os.path.exists(out_file) and not overwrite:
        print(f"[{date_str}] TAIFEX 期貨法人檔案已存在，略過。")
        return out_file

    rows, dt = fetch_taifex_futures_institutional(date_str)
    if not rows:
        print(f"[{date_str}] 無 TAIFEX 期貨法人資料可落盤。")
        return None

    df = pd.DataFrame(rows)
    df.to_parquet(out_file, engine='pyarrow', compression='snappy', index=False)
    print(f"[{datetime.now()}] 成功儲存 {len(df)} 筆期交所法人期貨資料至 {out_file}")
    return out_file

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="抓取每日期交所三大法人期貨部位 (嚴格日期校驗)")
    parser.add_argument("--date", type=str, default=None, help="交易日期 (格式: YYYY-MM-DD)")
    args = parser.parse_args()
    fetch_and_save_taifex(args.date)

