import os
import re
import requests
import pandas as pd
from datetime import datetime

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

DATA_DIR = "data"
os.makedirs(DATA_DIR, exist_ok=True)

def fetch_isin_market(str_mode: int, market_name: str, yfinance_suffix: str) -> pd.DataFrame:
    url = f"https://isin.twse.com.tw/isin/C_public.jsp?strMode={str_mode}"
    print(f"[{datetime.now()}] 正在抓取 {market_name} 名單...")
    
    resp = requests.get(url, headers=HEADERS)
    resp.encoding = 'big5'
    
    tables = pd.read_html(resp.text)
    if not tables:
        raise ValueError(f"無法解析 {url} 網頁表格")
    
    df = tables[0]
    df.columns = df.iloc[0]
    df = df.iloc[1:].copy()
    
    # 透過非空過濾掉大分類標題列
    df = df.dropna(subset=['國際證券辨識號碼']).copy()
    
    # 拆分代號與名稱（中間通常隔全形或半形空白）
    col_code_name = '有價證券代號及名稱'
    split_data = df[col_code_name].str.strip().str.split(r'[\s ]+', n=1, expand=True)
    df['Symbol'] = split_data[0]
    df['Name'] = split_data[1] if split_data.shape[1] > 1 else ''
    df['Market'] = market_name
    df['YF_Ticker'] = df['Symbol'] + yfinance_suffix
    
    keep_cols = ['Symbol', 'Name', 'Market', 'YF_Ticker', 'CFICode', '市場別', '產業別', '上市日']
    existing_cols = [c for c in keep_cols if c in df.columns]
    return df[existing_cols]

def filter_stocks_and_etfs(df: pd.DataFrame) -> pd.DataFrame:
    # 4 碼普通股 或 00 開頭 4~6 碼 ETF
    pattern = r'^(00\d{3,4}[A-Z]?|\d{4})$'
    mask = df['Symbol'].str.match(pattern, na=False)
    return df[mask].copy()

def main():
    df_twse = fetch_isin_market(str_mode=2, market_name='TWSE', yfinance_suffix='.TW')
    df_tpex = fetch_isin_market(str_mode=4, market_name='TPEx', yfinance_suffix='.TWO')
    
    full_df = pd.concat([df_twse, df_tpex], ignore_index=True)
    clean_stocks = filter_stocks_and_etfs(full_df)
    
    csv_path = os.path.join(DATA_DIR, "tw_stock_list.csv")
    parquet_path = os.path.join(DATA_DIR, "tw_stock_list.parquet")
    
    clean_stocks.to_csv(csv_path, index=False, encoding="utf-8-sig")
    clean_stocks.to_parquet(parquet_path, index=False)
    print(f"[{datetime.now()}] 成功取得 {len(clean_stocks)} 檔標的，已儲存至 {parquet_path}")

if __name__ == "__main__":
    main()

