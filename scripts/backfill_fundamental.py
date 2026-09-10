"""
台股近 5 年全市場基本面歷史資料回補引擎 (5-Year Fundamental Backfill Engine)
涵蓋:
1. 歷史月營收: 2021-01 至 2026-08 (共 68 個月份，全市場上市櫃普通股)
2. 歷史季報 EPS 與損益: 2021_Q1 至 2026_Q2 (共 22 個季度，全市場上市櫃普通股)
資料來源: 臺灣證券交易所公開資訊觀測站 (MOPS) 官方彙總報表
"""
import os
import sys
import time
import io
import argparse
import requests
import pandas as pd
import numpy as np
from datetime import datetime

REVENUE_DIR = "data/fundamental/revenue"
EPS_DIR = "data/fundamental/eps"
STOCK_LIST_PATH = "data/tw_stock_list.parquet"

os.makedirs(REVENUE_DIR, exist_ok=True)
os.makedirs(EPS_DIR, exist_ok=True)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://mopsov.twse.com.tw/mops/web/t163sb04',
}

def clean_num(val):
    if val is None or pd.isna(val):
        return 0
    s = str(val).replace(',', '').strip()
    if not s or s in ('--', '-'):
        return 0
    try:
        return int(float(s))
    except ValueError:
        return 0

def clean_float(val):
    if val is None or pd.isna(val):
        return 0.0
    s = str(val).replace(',', '').strip()
    if not s or s in ('--', '-'):
        return 0.0
    try:
        return round(float(s), 4)
    except ValueError:
        return 0.0

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
# 1. 回補近 5 年月營收 (2021-01 ~ 2026-08)
# -------------------------------------------------------------
def backfill_5y_revenue(start_year=2021, end_year=2026, force=False):
    stock_meta = get_stock_meta()
    months_to_run = []
    for y in range(start_year, end_year + 1):
        max_m = 8 if y == 2026 else 12
        for m in range(1, max_m + 1):
            months_to_run.append((y, m))

    total = len(months_to_run)
    print(f"[{datetime.now()}] 開始執行近 5 年歷史月營收回補 (共 {total} 個月份: 2021-01 ~ 2026-08)...")

    saved_count = 0
    for idx, (year, month) in enumerate(months_to_run, 1):
        ym_str = f"{year}-{month:02d}"
        out_file = os.path.join(REVENUE_DIR, f"{ym_str}.parquet")

        if not force and os.path.exists(out_file):
            try:
                cur_df = pd.read_parquet(out_file)
                if len(cur_df) >= 1500:
                    print(f"  [{idx}/{total}] {ym_str} 已存在完整資料 ({len(cur_df)} 檔)，略過。")
                    continue
            except Exception:
                pass

        print(f"  [{idx}/{total}] 正在抓取 {ym_str} 全市場月營收 (MOPS)...")
        roc_year = year - 1911
        rows = []

        for market, mkt_label in [('sii', 'TWSE'), ('otc', 'TPEx')]:
            url = f"https://mopsov.twse.com.tw/nas/t21/{market}/t21sc03_{roc_year}_{month}_0.html"
            try:
                r = requests.get(url, headers=HEADERS, timeout=20)
                if r.status_code != 200:
                    continue
                r.encoding = 'cp950'
                dfs = pd.read_html(io.StringIO(r.text))
                for df in dfs:
                    if df.shape[1] >= 11:
                        sub = df.copy()
                        sub.columns = range(sub.shape[1])
                        sub = sub[sub[0].astype(str).str.match(r'^\d{4}$')]
                        for _, row in sub.iterrows():
                            sym = str(row[0]).strip()
                            meta = stock_meta.get(sym, {})
                            name = meta.get('Name') or str(row[1]).strip()
                            ind = meta.get('Industry', '')

                            rows.append({
                                'YearMonth': ym_str,
                                'Ticker': sym,
                                'Name': name,
                                'Market': mkt_label,
                                'Industry': ind,
                                'Revenue_Current': clean_num(row[2]),
                                'Revenue_Last_Month': clean_num(row[3]),
                                'Revenue_Last_Year': clean_num(row[4]),
                                'MoM_Growth': clean_float(row[5]),
                                'YoY_Growth': clean_float(row[6]),
                                'Cumulative_Current': clean_num(row[7]),
                                'Cumulative_Last_Year': clean_num(row[8]),
                                'Cumulative_YoY_Growth': clean_float(row[9]),
                                'Note': str(row[10]).strip() if pd.notna(row[10]) else '-'
                            })
                time.sleep(0.3)
            except Exception as e:
                print(f"    {market} 抓取異常: {e}")

        if rows:
            df_out = pd.DataFrame(rows)
            df_out.drop_duplicates(subset=['Ticker'], keep='last', inplace=True)
            df_out.sort_values(by=['Market', 'Ticker'], inplace=True)
            df_out.to_parquet(out_file, engine='pyarrow', compression='snappy', index=False)
            saved_count += 1
            print(f"    成功儲存 {ym_str}.parquet ({len(df_out)} 檔標的)")
        else:
            print(f"    {ym_str} 未取得資料")

    print(f"[{datetime.now()}] 歷史月營收回補完成，共更新 {saved_count} 個月份檔案。\n")

# -------------------------------------------------------------
# 2. 回補近 5 年季報 EPS 與損益 (2021_Q1 ~ 2026_Q2)
# -------------------------------------------------------------
def backfill_5y_eps(start_year=2021, end_year=2026, force=False):
    stock_meta = get_stock_meta()
    quarters_to_run = []
    for y in range(start_year, end_year + 1):
        max_q = 2 if y == 2026 else 4
        for q in range(1, max_q + 1):
            quarters_to_run.append((y, q))

    total = len(quarters_to_run)
    print(f"[{datetime.now()}] 開始執行近 5 年歷史季報 EPS 回補 (共 {total} 個季度: 2021_Q1 ~ 2026_Q2)...")

    saved_count = 0
    for idx, (year, quarter) in enumerate(quarters_to_run, 1):
        period_str = f"{year}_Q{quarter}"
        out_file = os.path.join(EPS_DIR, f"{period_str}.parquet")

        if not force and os.path.exists(out_file):
            try:
                cur_df = pd.read_parquet(out_file)
                if len(cur_df) >= 1500:
                    print(f"  [{idx}/{total}] {period_str} 已存在完整資料 ({len(cur_df)} 檔)，略過。")
                    continue
            except Exception:
                pass

        print(f"  [{idx}/{total}] 正在抓取 {period_str} 全市場季報損益與 EPS (MOPS)...")
        roc_year = year - 1911
        rows = []

        for typek, mkt_label in [('sii', 'TWSE'), ('otc', 'TPEx')]:
            payload = {
                'encodeURIComponent': '1',
                'step': '1',
                'firstin': '1',
                'off': '1',
                'TYPEK': typek,
                'year': str(roc_year),
                'season': str(quarter)
            }
            try:
                r = requests.post('https://mopsov.twse.com.tw/mops/web/ajax_t163sb04', data=payload, headers=HEADERS, timeout=25)
                if r.status_code != 200 or 'SECURITY REASONS' in r.text:
                    print(f"    {typek} 請求失敗 (status={r.status_code})")
                    continue
                
                dfs = pd.read_html(io.StringIO(r.text))
                for df in dfs:
                    ticker_col = next((c for c in df.columns if '代號' in str(c)), None)
                    eps_col = next((c for c in df.columns if any(k in str(c) for k in ['每股盈餘', '基本每股', 'EPS'])), None)
                    if ticker_col and eps_col:
                        rev_col = next((c for c in df.columns if '營業收入' in str(c)), None)
                        op_col = next((c for c in df.columns if '營業利益' in str(c)), None)
                        net_col = next((c for c in df.columns if any(k in str(c) for k in ['本期淨利', '稅後淨利', '本期稅後'])), None)
                        name_col = next((c for c in df.columns if '名稱' in str(c)), None)

                        sub = df[df[ticker_col].astype(str).str.match(r'^\d{4}$')]
                        for _, row in sub.iterrows():
                            sym = str(row[ticker_col]).strip()
                            meta = stock_meta.get(sym, {})
                            name = meta.get('Name') or (str(row[name_col]).strip() if name_col and pd.notna(row[name_col]) else sym)
                            ind = meta.get('Industry', '')

                            rows.append({
                                'Year': year,
                                'Quarter': quarter,
                                'Period': period_str,
                                'Ticker': sym,
                                'Name': name,
                                'Market': mkt_label,
                                'Industry': ind,
                                'EPS': clean_float(row[eps_col]),
                                'Operating_Revenue': clean_num(row[rev_col]) if rev_col else 0,
                                'Operating_Profit': clean_num(row[op_col]) if op_col else 0,
                                'Non_Operating_Income': 0,
                                'Net_Income': clean_num(row[net_col]) if net_col else 0
                            })
                time.sleep(0.5)
            except Exception as e:
                print(f"    {typek} 解析異常: {e}")

        if rows:
            df_out = pd.DataFrame(rows)
            df_out.drop_duplicates(subset=['Ticker'], keep='last', inplace=True)
            df_out.sort_values(by=['Market', 'Ticker'], inplace=True)
            df_out.to_parquet(out_file, engine='pyarrow', compression='snappy', index=False)
            saved_count += 1
            print(f"    成功儲存 {period_str}.parquet ({len(df_out)} 檔標的)")
        else:
            print(f"    {period_str} 未取得資料")

    print(f"[{datetime.now()}] 歷史季報 EPS 回補完成，共更新 {saved_count} 個季度檔案。\n")

def run_fundamental_backfill(start_year=2021, end_year=2026, force=False):
    t0 = time.time()
    backfill_5y_revenue(start_year=start_year, end_year=end_year, force=force)
    backfill_5y_eps(start_year=start_year, end_year=end_year, force=force)
    print(f"[{datetime.now()}] 全部基本面歷史回補執行完畢！總耗時: {(time.time() - t0):.1f} 秒")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="近 5 年全市場基本面歷史資料回補 (2021-2026)")
    parser.add_argument("--start-year", type=int, default=2021, help="回補起始年份 (預設: 2021)")
    parser.add_argument("--end-year", type=int, default=2026, help="回補結束年份 (預設: 2026)")
    parser.add_argument("--revenue-only", action="store_true", help="僅回補月營收")
    parser.add_argument("--eps-only", action="store_true", help="僅回補季報 EPS")
    parser.add_argument("--force", action="store_true", help="強制重新抓取覆寫既有檔案")
    args = parser.parse_args()

    run_fundamental_backfill(start_year=args.start_year, end_year=args.end_year, force=args.force)
