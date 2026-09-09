import os
import io
import requests
import pandas as pd
import numpy as np
from datetime import datetime

OUTPUT_DIR = "data/chips/tdcc"
os.makedirs(OUTPUT_DIR, exist_ok=True)

TDCC_URL = "https://opendata.tdcc.com.tw/getOD.ashx?id=1-5"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def clean_float(val):
    try:
        return round(float(val), 4)
    except (ValueError, TypeError):
        return 0.0

def clean_int(val):
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0

def fetch_tdcc_distribution():
    print(f"[{datetime.now()}] 正在自 TDCC 集中保管結算所下載全市場集保股權分散表...")
    try:
        resp = requests.get(TDCC_URL, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            print(f"TDCC 回傳 HTTP {resp.status_code}")
            return None
        
        df = pd.read_csv(io.BytesIO(resp.content))
        if df.shape[1] < 6:
            print("TDCC 格式異常")
            return None

        # 統一欄位名稱
        df.columns = ['Raw_Date', 'Ticker', 'Level', 'Holders', 'Shares', 'Ratio']
        df['Ticker'] = df['Ticker'].astype(str).str.strip()
        df['Level'] = pd.to_numeric(df['Level'], errors='coerce').fillna(0).astype(int)
        df['Holders'] = pd.to_numeric(df['Holders'], errors='coerce').fillna(0).astype(int)
        df['Shares'] = pd.to_numeric(df['Shares'], errors='coerce').fillna(0).astype('int64')
        df['Ratio'] = pd.to_numeric(df['Ratio'], errors='coerce').fillna(0.0)

        # 解析日期 YYYYMMDD -> YYYY-MM-DD
        raw_date_str = str(df['Raw_Date'].iloc[0]).strip()
        if len(raw_date_str) == 8:
            date_str = f"{raw_date_str[:4]}-{raw_date_str[4:6]}-{raw_date_str[6:]}"
        else:
            date_str = datetime.now().strftime("%Y-%m-%d")

        print(f"[{datetime.now()}] 成功取得 {date_str} 集保資料，共 {len(df)} 筆級距紀錄，開始聚合計算關鍵指標...")

        # 聚合計算每檔個股之關鍵指標
        summary_rows = []
        for ticker, group in df.groupby('Ticker'):
            # Level 17 是官方合計行
            tot_row = group[group['Level'] == 17]
            if not tot_row.empty:
                tot_holders = tot_row['Holders'].iloc[0]
                tot_shares = tot_row['Shares'].iloc[0]
            else:
                tot_holders = group[group['Level'] <= 15]['Holders'].sum()
                tot_shares = group[group['Level'] <= 15]['Shares'].sum()

            # 散戶: Level 1~5 (< 10,000 股 / 10張以下)
            retail = group[(group['Level'] >= 1) & (group['Level'] <= 5)]
            retail_pct = clean_float(retail['Ratio'].sum())
            retail_holders = clean_int(retail['Holders'].sum())

            # 400張以上大戶: Level 12~15 (>= 400,000 股)
            over_400k = group[(group['Level'] >= 12) & (group['Level'] <= 15)]
            over_400k_pct = clean_float(over_400k['Ratio'].sum())
            over_400k_holders = clean_int(over_400k['Holders'].sum())

            # 千張大戶: Level 15 (>= 1,000,000 股)
            over_1000k = group[group['Level'] == 15]
            over_1000k_pct = clean_float(over_1000k['Ratio'].sum()) if not over_1000k.empty else 0.0
            over_1000k_holders = clean_int(over_1000k['Holders'].sum()) if not over_1000k.empty else 0

            summary_rows.append({
                'Date': date_str,
                'Ticker': ticker,
                'Total_Holders': tot_holders,
                'Total_Shares': tot_shares,
                'Under_10K_Pct': retail_pct,
                'Under_10K_Holders': retail_holders,
                'Over_400K_Pct': over_400k_pct,
                'Over_400K_Holders': over_400k_holders,
                'Over_1000K_Pct': over_1000k_pct,
                'Over_1000K_Holders': over_1000k_holders,
            })

        sum_df = pd.DataFrame(summary_rows)
        sum_df.sort_values(by='Ticker', inplace=True)
        out_file = os.path.join(OUTPUT_DIR, f"{date_str}.parquet")
        sum_df.to_parquet(out_file, engine='pyarrow', compression='snappy', index=False)
        print(f"[{datetime.now()}] 成功計算並儲存 {len(sum_df)} 檔標的之集保大戶持股統計至 {out_file}")
        return out_file

    except Exception as e:
        print(f"抓取 TDCC 失敗: {e}")
        return None

if __name__ == "__main__":
    fetch_tdcc_distribution()

