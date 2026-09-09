import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime

OUTPUT_DIR = "data/twse_openapi/mi_5mins"
os.makedirs(OUTPUT_DIR, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def fetch_twse_mi_5mins(date_str=None):
    """
    抓取 TWSE 官方 OpenAPI 的 /exchangeReport/MI_5MINS (每5秒/5分委託成交統計)
    """
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
        
    url = "https://openapi.twse.com.tw/v1/exchangeReport/MI_5MINS"
    print(f"[{datetime.now()}] 正在自 TWSE OpenAPI 抓取 {date_str} 盤中每5秒/5分委託成交資料...")
    
    resp = requests.get(url, headers=HEADERS, timeout=30)
    if resp.status_code != 200:
        raise ConnectionError(f"TWSE OpenAPI 回傳異常 HTTP 狀態碼: {resp.status_code}")
        
    data = resp.json()
    if not data or not isinstance(data, list):
        print(f"[{datetime.now()}] 未取得任何資料，可能非交易日或資料尚未產生。")
        return None

    df = pd.DataFrame(data)
    df['Date'] = date_str

    # 欄位轉型處理 (空白字串轉為 0)
    numeric_cols = [
        'AccBidOrders', 'AccBidVolume', 'AccAskOrders', 
        'AccAskVolume', 'AccTransaction', 'AccTradeVolume', 'AccTradeValue'
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].replace('', '0'), errors='coerce').fillna(0).astype('int64')

    # 時間格式化 HH:MM:SS
    if 'Time' in df.columns:
        df['Time_Formatted'] = df['Time'].astype(str).str.zfill(6).apply(
            lambda t: f"{t[:2]}:{t[2:4]}:{t[4:6]}" if len(t) == 6 else t
        )

    # 計算間隔增量值 (每期新增筆數、量、金額)
    if 'AccTransaction' in df.columns:
        df['IntervalTransaction'] = df['AccTransaction'].diff().fillna(df['AccTransaction']).clip(lower=0).astype('int64')
    if 'AccTradeVolume' in df.columns:
        df['IntervalTradeVolume'] = df['AccTradeVolume'].diff().fillna(df['AccTradeVolume']).clip(lower=0).astype('int64')
    if 'AccTradeValue' in df.columns:
        df['IntervalTradeValue'] = df['AccTradeValue'].diff().fillna(df['AccTradeValue']).clip(lower=0).astype('int64')

    # 排序列
    sort_cols = ['Date', 'Time']
    available_sort = [c for c in sort_cols if c in df.columns]
    df.sort_values(by=available_sort, inplace=True)

    output_path = os.path.join(OUTPUT_DIR, f"{date_str}.parquet")
    df.to_parquet(output_path, engine='pyarrow', compression='snappy', index=False)
    print(f"[{datetime.now()}] 成功取得 {len(df)} 筆 TWSE 盤中統計資料，已儲存至 {output_path}")
    return output_path

if __name__ == "__main__":
    fetch_twse_mi_5mins()
