"""
台股基本面歷史資料回補引擎 (Fundamental Backfill Engine)
支援回補:
1. 歷史每月營業收入 (2024-01 至 2026-08, 依 YYYY-MM.parquet 儲存)
2. 歷史季報 EPS 與損益表 (2024_Q1 至 2026_Q2, 依 YYYY_QX.parquet 儲存)
整合 FinMind 與公開資訊觀測站公開標準，支援多執行緒並行抓取與自動合併
"""
import os
import sys
import time
import argparse
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

REVENUE_DIR = "data/fundamental/revenue"
EPS_DIR = "data/fundamental/eps"
STOCK_LIST_PATH = "data/tw_stock_list.parquet"

os.makedirs(REVENUE_DIR, exist_ok=True)
os.makedirs(EPS_DIR, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def get_target_stocks(limit=100, specific_symbols=None):
    if not os.path.exists(STOCK_LIST_PATH):
        return ['2330', '2317', '2454', '2308', '2382']
    
    df = pd.read_parquet(STOCK_LIST_PATH)
    if specific_symbols:
        return [str(s).strip() for s in specific_symbols]
    
    if limit and limit > 0:
        return df['Symbol'].head(limit).tolist()
    return df['Symbol'].tolist()

def get_stock_meta():
    if os.path.exists(STOCK_LIST_PATH):
        try:
            df = pd.read_parquet(STOCK_LIST_PATH)
            ind_col = next((c for c in df.columns if '產' in str(c) or 'Industry' in str(c)), None)
            res = {}
            for _, r in df.iterrows():
                sym = str(r['Symbol']).strip()
                name = str(r['Name']).strip() if 'Name' in r and pd.notna(r['Name']) else sym
                mkt = str(r['Market']).strip() if 'Market' in r and pd.notna(r['Market']) else 'TWSE'
                ind = str(r[ind_col]).strip() if ind_col and pd.notna(r[ind_col]) else ''
                res[sym] = {'Name': name, 'Market': mkt, 'Industry': ind}
            return res
        except Exception:
            pass
    return {}

# -------------------------------------------------------------
# 1. 歷史月營收回補
# -------------------------------------------------------------
def fetch_stock_monthly_revenue(symbol, start_date='2023-01-01'):
    url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockMonthRevenue&data_id={symbol}&start_date={start_date}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            return r.json().get('data', [])
    except Exception:
        pass
    return []

def backfill_monthly_revenues(symbols, max_workers=8):
    print(f"[{datetime.now()}] 開始並行回補 {len(symbols)} 檔標的之歷史月營收 (2024-01 ~ 2026-08)...")
    stock_meta = get_stock_meta()
    all_rows = []

    def worker(sym):
        recs = fetch_stock_monthly_revenue(sym)
        if not recs:
            return []
        
        df_stock = pd.DataFrame(recs)
        df_stock.sort_values(by=['revenue_year', 'revenue_month'], inplace=True)
        df_stock['YearMonth'] = df_stock['revenue_year'].astype(str) + '-' + df_stock['revenue_month'].astype(str).str.zfill(2)
        
        # 轉換為千元 (MOPS 官方標準單位)
        df_stock['Revenue_Current'] = (df_stock['revenue'] / 1000).fillna(0).astype('int64')
        df_stock['Revenue_Last_Month'] = df_stock['Revenue_Current'].shift(1).fillna(0).astype('int64')
        df_stock['Revenue_Last_Year'] = df_stock['Revenue_Current'].shift(12).fillna(0).astype('int64')
        
        df_stock['MoM_Growth'] = ((df_stock['Revenue_Current'] - df_stock['Revenue_Last_Month']) / df_stock['Revenue_Last_Month'] * 100).replace([np.inf, -np.inf], 0).round(4).fillna(0.0)
        df_stock['YoY_Growth'] = ((df_stock['Revenue_Current'] - df_stock['Revenue_Last_Year']) / df_stock['Revenue_Last_Year'] * 100).replace([np.inf, -np.inf], 0).round(4).fillna(0.0)

        # 累計計算
        df_stock['Cumulative_Current'] = df_stock.groupby('revenue_year')['Revenue_Current'].cumsum()
        df_stock['Cumulative_Last_Year'] = df_stock['Cumulative_Current'].shift(12).fillna(0).astype('int64')
        df_stock['Cumulative_YoY_Growth'] = ((df_stock['Cumulative_Current'] - df_stock['Cumulative_Last_Year']) / df_stock['Cumulative_Last_Year'] * 100).replace([np.inf, -np.inf], 0).round(4).fillna(0.0)

        meta = stock_meta.get(str(sym), {})
        name = meta.get('Name', str(sym))
        mkt = meta.get('Market', 'TWSE')
        ind = meta.get('Industry', '')

        rows = []
        for _, r in df_stock.iterrows():
            if r['YearMonth'] < '2024-01':
                continue
            rows.append({
                'YearMonth': r['YearMonth'],
                'Ticker': str(sym),
                'Name': name,
                'Market': mkt,
                'Industry': ind,
                'Revenue_Current': int(r['Revenue_Current']),
                'Revenue_Last_Month': int(r['Revenue_Last_Month']),
                'Revenue_Last_Year': int(r['Revenue_Last_Year']),
                'MoM_Growth': float(r['MoM_Growth']),
                'YoY_Growth': float(r['YoY_Growth']),
                'Cumulative_Current': int(r['Cumulative_Current']),
                'Cumulative_Last_Year': int(r['Cumulative_Last_Year']),
                'Cumulative_YoY_Growth': float(r['Cumulative_YoY_Growth']),
                'Note': '-'
            })
        return rows

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for res in executor.map(worker, symbols):
            all_rows.extend(res)

    if not all_rows:
        print("未取得任何月營收資料。")
        return

    full_df = pd.DataFrame(all_rows)
    # 按月份分組寫入各月份 parquet
    saved_count = 0
    for ym, group in full_df.groupby('YearMonth'):
        out_file = os.path.join(REVENUE_DIR, f"{ym}.parquet")
        if os.path.exists(out_file):
            existing_df = pd.read_parquet(out_file)
            # 合併，依 Ticker 去重保留最新
            combined = pd.concat([existing_df, group], ignore_index=True)
            combined.drop_duplicates(subset=['Ticker'], keep='last', inplace=True)
            combined.sort_values(by=['Market', 'Ticker'], inplace=True)
            combined.to_parquet(out_file, engine='pyarrow', compression='snappy', index=False)
        else:
            group_sorted = group.sort_values(by=['Market', 'Ticker'])
            group_sorted.to_parquet(out_file, engine='pyarrow', compression='snappy', index=False)
        saved_count += 1

    print(f"[{datetime.now()}] 成功回補/更新 {saved_count} 個月份之歷史月營收資料至 {REVENUE_DIR}")

# -------------------------------------------------------------
# 2. 歷史季報 EPS 與損益表回補
# -------------------------------------------------------------
def fetch_stock_financial_statements(symbol, start_date='2024-01-01'):
    url = f"https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockFinancialStatements&data_id={symbol}&start_date={start_date}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            return r.json().get('data', [])
    except Exception:
        pass
    return []

def backfill_quarterly_eps(symbols, max_workers=8):
    print(f"[{datetime.now()}] 開始並行回補 {len(symbols)} 檔標的之歷史季報 EPS 與損益 (2024_Q1 ~ 2026_Q2)...")
    stock_meta = get_stock_meta()
    all_rows = []

    def worker(sym):
        recs = fetch_stock_financial_statements(sym)
        if not recs:
            return []

        df_stock = pd.DataFrame(recs)
        if df_stock.empty or 'type' not in df_stock.columns:
            return []

        # 篩選 EPS、營收、營業利益與淨利
        meta = stock_meta.get(str(sym), {})
        name = meta.get('Name', str(sym))
        mkt = meta.get('Market', 'TWSE')
        ind = meta.get('Industry', '')

        rows = []
        for dt_str, group in df_stock.groupby('date'):
            # 解析年份與季度
            try:
                dt = datetime.strptime(str(dt_str).strip(), '%Y-%m-%d')
                year = dt.year
                month = dt.month
                quarter = (month - 1) // 3 + 1
                period = f"{year}_Q{quarter}"
            except Exception:
                continue

            # 提取各項財務指標
            val_map = group.set_index('type')['value'].to_dict()
            eps = round(float(val_map.get('EPS', 0.0)), 4) if 'EPS' in val_map else 0.0
            rev = int(val_map.get('Revenue', 0) / 1000) if 'Revenue' in val_map else 0
            op_profit = int(val_map.get('OperatingIncome', 0) / 1000) if 'OperatingIncome' in val_map else 0
            net_income = int(val_map.get('IncomeAfterTaxes', 0) / 1000) if 'IncomeAfterTaxes' in val_map else 0

            rows.append({
                'Year': year,
                'Quarter': quarter,
                'Period': period,
                'Ticker': str(sym),
                'Name': name,
                'Market': mkt,
                'Industry': ind,
                'EPS': eps,
                'Operating_Revenue': rev,
                'Operating_Profit': op_profit,
                'Non_Operating_Income': 0,
                'Net_Income': net_income
            })
        return rows

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for res in executor.map(worker, symbols):
            all_rows.extend(res)

    if not all_rows:
        print("未取得任何季報 EPS 資料。")
        return

    full_df = pd.DataFrame(all_rows)
    saved_count = 0
    for period, group in full_df.groupby('Period'):
        out_file = os.path.join(EPS_DIR, f"{period}.parquet")
        if os.path.exists(out_file):
            existing_df = pd.read_parquet(out_file)
            combined = pd.concat([existing_df, group], ignore_index=True)
            combined.drop_duplicates(subset=['Ticker'], keep='last', inplace=True)
            combined.sort_values(by=['Market', 'Ticker'], inplace=True)
            combined.to_parquet(out_file, engine='pyarrow', compression='snappy', index=False)
        else:
            group_sorted = group.sort_values(by=['Market', 'Ticker'])
            group_sorted.to_parquet(out_file, engine='pyarrow', compression='snappy', index=False)
        saved_count += 1

    print(f"[{datetime.now()}] 成功回補/更新 {saved_count} 個季度之歷史季報 EPS 至 {EPS_DIR}")

def run_fundamental_backfill(limit=100, symbols=None):
    target_symbols = get_target_stocks(limit=limit, specific_symbols=symbols)
    print(f"[{datetime.now()}] 準備針對 {len(target_symbols)} 檔核心權值標的執行全量歷史基本面回補...")
    
    # 1. 回補歷史月營收 (32 個月份)
    backfill_monthly_revenues(target_symbols)
    
    # 2. 回補歷史季報 EPS (10 個季度)
    backfill_quarterly_eps(target_symbols)

    print(f"\n[{datetime.now()}] 基本面歷史數據回補流程全部完成！")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="台股基本面歷史資料回補引擎 (月營收 + 季報 EPS)")
    parser.add_argument("--limit", type=int, default=100, help="回補標的數量 (依權重由大至小，預設: 100)")
    parser.add_argument("--symbols", nargs="+", default=None, help="指定回補之股票代號清單")
    args = parser.parse_args()
    run_fundamental_backfill(limit=args.limit, symbols=args.symbols)
