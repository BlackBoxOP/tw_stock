"""
台股歷史多維度數據回補引擎 (Backfill Engine)
整合上市 (TWSE) 與上櫃 (TPEx) 之三大法人買賣超、融資融券餘額、本益比殖利率、大盤產業指數
支援嚴格官方日期校驗，防止數據誤標
"""
import os
import sys
import time
import argparse
import glob
from datetime import datetime, timedelta

# 加入 scripts 目錄以支援相對引入
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SCRIPTS_DIR)

from fetch_institutional_daily import fetch_and_save_institutional
from fetch_margin_daily import fetch_and_save_margin
from fetch_valuation_daily import fetch_and_save_valuation
from fetch_market_indices import fetch_and_save_market_indices

INSTITUTIONAL_DIR = "data/institutional"
MARGIN_DIR = "data/margin"
VALUATION_DIR = "data/valuation"
INDICES_DIR = "data/market_indices"

def get_trading_days(start_date=None, end_date=None, days_limit=None):
    """自 data/by_date 或日曆取得有效交易日"""
    by_date_files = sorted(glob.glob("data/by_date/*.parquet"))
    all_dates = [os.path.splitext(os.path.basename(f))[0] for f in by_date_files]

    if not all_dates:
        cur = datetime.now()
        all_dates = []
        for i in range(120):
            d = cur - timedelta(days=i)
            if d.weekday() < 5:
                all_dates.append(d.strftime("%Y-%m-%d"))
        all_dates.sort()

    if start_date:
        all_dates = [d for d in all_dates if d >= start_date]
    if end_date:
        all_dates = [d for d in all_dates if d <= end_date]

    if days_limit and len(all_dates) > days_limit:
        all_dates = all_dates[-days_limit:]

    return all_dates

def run_backfill(days=10, start=None, end=None, delay=1.0, overwrite=False):
    trading_days = get_trading_days(start_date=start, end_date=end, days_limit=days)
    if not trading_days:
        print("未找到符合條件之交易日。")
        return

    print(f"[{datetime.now()}] 準備回補 {len(trading_days)} 個交易日之多維度歷史資料 (TWSE+TPEx 三大法人、融資融券、本益比殖利率、指數)...")
    print(f"涵蓋日期區間: {trading_days[0]} ~ {trading_days[-1]} (overwrite={overwrite})\n")

    for i, dt in enumerate(reversed(trading_days), 1):
        print(f"[{i}/{len(trading_days)}] 處理交易日 {dt}...")
        
        # 1. 三大法人
        inst_path = os.path.join(INSTITUTIONAL_DIR, f"{dt}.parquet")
        if overwrite or not os.path.exists(inst_path):
            fetch_and_save_institutional(dt, overwrite=overwrite)
            time.sleep(delay)
        else:
            print(f"  [三大法人] {dt} 已存在，略過。")

        # 2. 融資融券
        margin_path = os.path.join(MARGIN_DIR, f"{dt}.parquet")
        if overwrite or not os.path.exists(margin_path):
            fetch_and_save_margin(dt, overwrite=overwrite)
            time.sleep(delay)
        else:
            print(f"  [融資融券] {dt} 已存在，略過。")

        # 3. 本益比殖利率
        val_path = os.path.join(VALUATION_DIR, f"{dt}.parquet")
        if overwrite or not os.path.exists(val_path):
            fetch_and_save_valuation(dt, overwrite=overwrite)
            time.sleep(delay)
        else:
            print(f"  [評價面] {dt} 已存在，略過。")

        # 4. 大盤指數
        idx_path = os.path.join(INDICES_DIR, f"{dt}.parquet")
        if overwrite or not os.path.exists(idx_path):
            fetch_and_save_market_indices(dt, overwrite=overwrite)
            time.sleep(delay)
        else:
            print(f"  [大盤指數] {dt} 已存在，略過。")

    print(f"\n[{datetime.now()}] 歷史數據回補流程執行完畢！")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="台股歷史多維度數據回補腳本 (TWSE + TPEx)")
    parser.add_argument("--days", type=int, default=10, help="回補最近 N 個交易日 (預設: 10)")
    parser.add_argument("--start", type=str, default=None, help="起始日期 (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=None, help="結束日期 (YYYY-MM-DD)")
    parser.add_argument("--delay", type=float, default=1.0, help="每次網路請求間隔秒數 (預設: 1.0秒)")
    parser.add_argument("--overwrite", action="store_true", help="強制重新抓取覆蓋既有檔案")
    args = parser.parse_args()

    run_backfill(days=args.days, start=args.start, end=args.end, delay=args.delay, overwrite=args.overwrite)
