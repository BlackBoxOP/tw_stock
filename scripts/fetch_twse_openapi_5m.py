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

def get_twse_official_date():
    """向 TWSE MI_INDEX 查詢目前報表的官方交易日期 (解決盤前或收盤前日期誤判問題)"""
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

def fetch_from_twse_web(date_str=None):
    """
    優先自證交所官方 Web 端點 (www.twse.com.tw) 抓取即時盤後每5秒委託成交統計。
    優點：當天收盤後 (約 13:35 起) 即可取得當天最新資料，無需等到次日清晨 OpenAPI 靜態檔案更新。
    """
    url = "https://www.twse.com.tw/exchangeReport/MI_5MINS?response=json"
    if date_str:
        clean_date = date_str.replace("-", "")
        url += f"&date={clean_date}"
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            res_json = resp.json()
            if res_json.get("stat") == "OK" and "data" in res_json and len(res_json["data"]) > 0:
                raw_date = res_json.get("date", "")
                if len(raw_date) == 8:
                    actual_date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
                else:
                    actual_date = date_str or datetime.now().strftime("%Y-%m-%d")
                
                cols = [
                    'Time_Formatted', 'AccBidOrders', 'AccBidVolume', 
                    'AccAskOrders', 'AccAskVolume', 'AccTransaction', 
                    'AccTradeVolume', 'AccTradeValue'
                ]
                df = pd.DataFrame(res_json['data'], columns=cols)
                df['Date'] = actual_date
                df['Time'] = df['Time_Formatted'].astype(str).str.replace(':', '')
                # 去除千分位逗號
                for col in cols[1:]:
                    df[col] = df[col].astype(str).str.replace(',', '').str.strip()
                return df, actual_date
    except Exception as e:
        print(f"[{datetime.now()}] 嘗試自 TWSE Web 抓取時發生異常: {e}，切換至 OpenAPI...")
    return None, None

def fetch_twse_mi_5mins(date_str=None):
    """
    抓取 TWSE 每5秒/5分委託成交統計。
    雙軌架構：優先由證交所即時端點抓取當日收盤資料；若失敗或遇非交易日則回退至 OpenAPI 靜態端點。
    """
    # 1. 優先嘗試 Web 端點 (取得當天收盤最新資料)
    print(f"[{datetime.now()}] 正在自 TWSE 官方端點查詢每5秒/5分委託成交資料...")
    df, actual_date = fetch_from_twse_web(date_str)
    source = "TWSE Web (即時盤後)"

    # 2. 若 Web 未取到，回退至 OpenAPI 端點
    if df is None or df.empty:
        if date_str is None:
            actual_date = get_twse_official_date()
        else:
            actual_date = date_str
            
        print(f"[{datetime.now()}] 嘗試自 TWSE OpenAPI 抓取 {actual_date} 盤中每5秒/5分委託成交資料...")
        url = "https://openapi.twse.com.tw/v1/exchangeReport/MI_5MINS"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if data and isinstance(data, list) and len(data) > 0:
                    df = pd.DataFrame(data)
                    df['Date'] = actual_date
                    source = "TWSE OpenAPI (靜態匯出)"
        except Exception as e:
            print(f"[{datetime.now()}] 自 TWSE OpenAPI 抓取失敗: {e}")

    if df is None or df.empty:
        print(f"[{datetime.now()}] 未取得任何資料，可能非交易日或資料尚未產生。")
        return None

    # 欄位轉型處理 (空白字串轉為 0)
    numeric_cols = [
        'AccBidOrders', 'AccBidVolume', 'AccAskOrders', 
        'AccAskVolume', 'AccTransaction', 'AccTradeVolume', 'AccTradeValue'
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col].replace('', '0'), errors='coerce').fillna(0).astype('int64')

    # 時間格式化 HH:MM:SS
    if 'Time_Formatted' not in df.columns and 'Time' in df.columns:
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

    # 統一欄位排序
    target_cols = [
        'Time', 'AccBidOrders', 'AccBidVolume', 'AccAskOrders', 'AccAskVolume', 
        'AccTransaction', 'AccTradeVolume', 'AccTradeValue', 'Date', 'Time_Formatted', 
        'IntervalTransaction', 'IntervalTradeVolume', 'IntervalTradeValue'
    ]
    available_cols = [c for c in target_cols if c in df.columns]
    df = df[available_cols]

    sort_cols = ['Date', 'Time']
    available_sort = [c for c in sort_cols if c in df.columns]
    df.sort_values(by=available_sort, inplace=True)

    output_path = os.path.join(OUTPUT_DIR, f"{actual_date}.parquet")
    df.to_parquet(output_path, engine='pyarrow', compression='snappy', index=False)
    print(f"[{datetime.now()}] 成功取得 {len(df)} 筆 TWSE 盤中統計資料 ({actual_date}, 來源: {source})，已儲存至 {output_path}")
    return output_path

if __name__ == "__main__":
    fetch_twse_mi_5mins()
