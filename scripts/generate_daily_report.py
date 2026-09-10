"""
台股每日量化盤後綜合分析儀表板與日報產生器 (Daily Quant Market Summary Report)
跨維度整合：
1. 大盤與產業指數 (Market Indices)
2. 期交所三大法人未平倉淨口數 (TAIFEX Futures Net OI)
3. 現貨三大法人買賣超 (Institutional Flow)
4. 融資融券與全市場借券賣出 (Margin & SBL Short Flow)
5. 券商分點主力進出 (Broker Tracking)
6. 基本面月營收與 EPS 成長篩選 (Fundamental Screens)
產出終端排版並自動落盤儲存為 reports/{date}_market_summary.md
"""
import os
import sys
import glob
import argparse
import duckdb
import pandas as pd
from datetime import datetime

# Windows 控制台 Unicode 相容設定
try:
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.stderr.encoding != 'utf-8':
        sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

REPORT_DIR = "reports"
os.makedirs(REPORT_DIR, exist_ok=True)

def get_latest_date():
    inst_files = sorted(glob.glob("data/institutional/*.parquet"))
    if inst_files:
        return os.path.splitext(os.path.basename(inst_files[-1]))[0]
    return datetime.now().strftime("%Y-%m-%d")

def generate_report(target_date=None, save_md=True):
    if target_date is None:
        target_date = get_latest_date()

    con = duckdb.connect(':memory:')
    md_lines = []

    def log_and_append(s=""):
        print(s)
        md_lines.append(s)

    log_and_append(f"# 📊 台灣股市量化盤後總覽日報 ({target_date})")
    log_and_append(f"> 產出時間：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 數據引擎：DuckDB + Apache Parquet\n")

    # -------------------------------------------------------------
    # 1. 大盤與主要指數
    # -------------------------------------------------------------
    idx_file = f"data/market_indices/{target_date}.parquet"
    if os.path.exists(idx_file):
        log_and_append("## 1. 📈 市場大盤與核心指數")
        df_idx = con.execute(f"""
            SELECT Index_Name, Close_Index, Change_Points, Change_Percent 
            FROM read_parquet('{idx_file}')
            WHERE Index_Name IN ('發行量加權股價指數', '寶島股價指數', '臺灣50指數', '電子類指數', '金融保險類指數', '櫃買指數')
               OR Index_Name LIKE '%加權%' OR Index_Name LIKE '%臺灣50%'
            LIMIT 5
        """).df()
        if not df_idx.empty:
            log_and_append("| 指數名稱 | 收盤指數 | 漲跌點數 | 漲跌幅 (%) |")
            log_and_append("| :--- | :--- | :--- | :--- |")
            for _, r in df_idx.iterrows():
                sign = "+" if r['Change_Points'] > 0 else ""
                log_and_append(f"| **{r['Index_Name']}** | {r['Close_Index']:,.2f} | {sign}{r['Change_Points']:,.2f} | {sign}{r['Change_Percent']:.2f}% |")
            log_and_append("")
    
    # -------------------------------------------------------------
    # 2. 期交所三大法人未平倉部位 (市場多空先行指標)
    # -------------------------------------------------------------
    taifex_file = f"data/taifex/institutional/{target_date}.parquet"
    if os.path.exists(taifex_file):
        log_and_append("## 2. 🧭 期貨三大法人大額交易與未平倉 (先行風向球)")
        df_tf = con.execute(f"""
            SELECT Commodity, Institution, Net_Volume, OI_Long_Volume, OI_Short_Volume, OI_Net_Volume 
            FROM read_parquet('{taifex_file}')
            WHERE Commodity IN ('臺股期貨', '小型臺指期貨', '電子期貨', '金融期貨')
            ORDER BY 
                CASE Commodity 
                    WHEN '臺股期貨' THEN 1 
                    WHEN '小型臺指期貨' THEN 2 
                    WHEN '電子期貨' THEN 3 
                    WHEN '金融期貨' THEN 4 
                    ELSE 5 
                END,
                CASE Institution 
                    WHEN '外資' THEN 1 
                    WHEN '投信' THEN 2 
                    WHEN '自營商' THEN 3 
                    ELSE 4 
                END
        """).df()
        if not df_tf.empty:
            log_and_append("| 契約商品 | 參與機構 | 當日買賣淨口數 | 多方未平倉 (口) | 空方未平倉 (口) | 淨未平倉 (口) |")
            log_and_append("| :--- | :--- | :--- | :--- | :--- | :--- |")
            for _, r in df_tf.iterrows():
                day_sign = "+" if r['Net_Volume'] > 0 else ""
                oi_sign = "+" if r['OI_Net_Volume'] > 0 else ""
                log_and_append(f"| {r['Commodity']} | **{r['Institution']}** | {day_sign}{r['Net_Volume']:,} | {r['OI_Long_Volume']:,} | {r['OI_Short_Volume']:,} | **{oi_sign}{r['OI_Net_Volume']:,}** |")
            log_and_append("")

    # -------------------------------------------------------------
    # 3. 現貨三大法人買賣超 (上市 + 上櫃)
    # -------------------------------------------------------------
    inst_file = f"data/institutional/{target_date}.parquet"
    if os.path.exists(inst_file):
        log_and_append("## 3. 💼 現貨三大法人買賣超動向")
        df_inst_sum = con.execute(f"""
            SELECT Market,
                   ROUND(SUM(Foreign_Net) / 1000.0, 1) as Foreign_Net_K,
                   ROUND(SUM(Trust_Net) / 1000.0, 1) as Trust_Net_K,
                   ROUND(SUM(Dealer_Net) / 1000.0, 1) as Dealer_Net_K,
                   ROUND(SUM(Total_Net) / 1000.0, 1) as Total_Net_K
            FROM read_parquet('{inst_file}')
            GROUP BY Market
            ORDER BY Market DESC
        """).df()
        if not df_inst_sum.empty:
            log_and_append("| 市場 | 外資買賣超 (張) | 投信買賣超 (張) | 自營商買賣超 (張) | 三大法人合計 (張) |")
            log_and_append("| :--- | :--- | :--- | :--- | :--- |")
            for _, r in df_inst_sum.iterrows():
                log_and_append(f"| **{r['Market']}** | {r['Foreign_Net_K']:,.1f}K | {r['Trust_Net_K']:,.1f}K | {r['Dealer_Net_K']:,.1f}K | **{r['Total_Net_K']:,.1f}K** |")
            log_and_append("")

    # -------------------------------------------------------------
    # 4. 信用交易 (融資融券) 與全市場借券賣出 (SBL)
    # -------------------------------------------------------------
    margin_file = f"data/margin/{target_date}.parquet"
    sbl_file = f"data/margin/sbl/{target_date}.parquet"
    if os.path.exists(margin_file) or os.path.exists(sbl_file):
        log_and_append("## 4. ⚖️ 信用籌碼與借券避險 (槓桿與空方力道)")
        margin_str = ""
        if os.path.exists(margin_file):
            df_m = con.execute(f"""
                SELECT 
                    SUM(Margin_Buy - Margin_Sell) as Margin_Net_Daily,
                    SUM(Margin_Balance) as Margin_Total_Bal,
                    SUM(Short_Sell - Short_Buy) as Short_Net_Daily,
                    SUM(Short_Balance) as Short_Total_Bal
                FROM read_parquet('{margin_file}')
            """).df().iloc[0]
            m_sign = "+" if df_m['Margin_Net_Daily'] > 0 else ""
            s_sign = "+" if df_m['Short_Net_Daily'] > 0 else ""
            margin_str = f"- **融資增減**：今日 {m_sign}{df_m['Margin_Net_Daily']:,} 張 (總餘額: {df_m['Margin_Total_Bal']:,} 張)\n- **融券增減**：今日 {s_sign}{df_m['Short_Net_Daily']:,} 張 (總餘額: {df_m['Short_Total_Bal']:,} 張)"
        
        sbl_str = ""
        if os.path.exists(sbl_file):
            df_sbl = con.execute(f"""
                SELECT 
                    ROUND(SUM(SBL_Net_Change) / 1000.0, 1) as SBL_Net_Change_K,
                    ROUND(SUM(SBL_Balance) / 1000.0, 1) as SBL_Total_Bal_K
                FROM read_parquet('{sbl_file}')
            """).df().iloc[0]
            sbl_sign = "+" if df_sbl['SBL_Net_Change_K'] > 0 else ""
            sbl_str = f"- **借券賣出**：今日 {sbl_sign}{df_sbl['SBL_Net_Change_K']:,.1f}K 張 (總餘額: {df_sbl['SBL_Total_Bal_K']:,.1f}K 張)"

        log_and_append(margin_str)
        if sbl_str:
            log_and_append(sbl_str)
        log_and_append("")

    # -------------------------------------------------------------
    # 5. 法人同步大幅加碼 TOP 10 (外資 + 投信同買)
    # -------------------------------------------------------------
    if os.path.exists(inst_file):
        log_and_append("## 5. 🚀 法人同步大買精選 TOP 10 (外資與投信合力加碼)")
        df_co_buy = con.execute(f"""
            SELECT Ticker, Name, Market,
                   ROUND(Foreign_Net / 1000.0, 1) as Foreign_K,
                   ROUND(Trust_Net / 1000.0, 1) as Trust_K,
                   ROUND(Total_Net / 1000.0, 1) as Total_K
            FROM read_parquet('{inst_file}')
            WHERE Foreign_Net > 0 AND Trust_Net > 0
            ORDER BY Total_Net DESC
            LIMIT 10
        """).df()
        if not df_co_buy.empty:
            log_and_append("| 代號 | 股票名稱 | 市場 | 外資買超 (張) | 投信買超 (張) | 合計買超 (張) |")
            log_and_append("| :--- | :--- | :--- | :--- | :--- | :--- |")
            for _, r in df_co_buy.iterrows():
                log_and_append(f"| **{r['Ticker']}** | {r['Name']} | {r['Market']} | +{r['Foreign_K']:,.1f}K | +{r['Trust_K']:,.1f}K | **+{r['Total_K']:,.1f}K** |")
            log_and_append("")

    # -------------------------------------------------------------
    # 6. 外資借券賣出大幅回補 TOP 10 (空頭回補力道)
    # -------------------------------------------------------------
    if os.path.exists(sbl_file):
        log_and_append("## 6. 🔄 借券賣出空單大回補 TOP 10 (SBL 還券大增)")
        df_sbl_cover = con.execute(f"""
            SELECT Ticker, Name,
                   ROUND(SBL_Daily_Return / 1000.0, 1) as Return_K,
                   ROUND(SBL_Daily_Sell / 1000.0, 1) as Sell_K,
                   ROUND(SBL_Net_Change / 1000.0, 1) as Net_Change_K,
                   ROUND(SBL_Balance / 1000.0, 1) as Balance_K
            FROM read_parquet('{sbl_file}')
            WHERE SBL_Net_Change < -50000
            ORDER BY SBL_Net_Change ASC
            LIMIT 10
        """).df()
        if not df_sbl_cover.empty:
            log_and_append("| 代號 | 股票名稱 | 當日還券 (張) | 當日借賣 (張) | 借券淨增減 (張) | 借券賣出餘額 (張) |")
            log_and_append("| :--- | :--- | :--- | :--- | :--- | :--- |")
            for _, r in df_sbl_cover.iterrows():
                log_and_append(f"| **{r['Ticker']}** | {r['Name']} | {r['Return_K']:,.1f}K | {r['Sell_K']:,.1f}K | **{r['Net_Change_K']:,.1f}K** | {r['Balance_K']:,.1f}K |")
            log_and_append("")

    # -------------------------------------------------------------
    # 7. 券商主力大戶重壓標的 (Broker Flow)
    # -------------------------------------------------------------
    broker_file = f"data/chips/broker_trading/{target_date}.parquet"
    if os.path.exists(broker_file):
        log_and_append("## 7. 🏦 券商分點主力買超精選")
        df_brk = con.execute(f"""
            SELECT Ticker, Name, Broker_Name, Net_Qty, Share_Pct, Total_Buy, Avg_Buy_Cost
            FROM read_parquet('{broker_file}')
            WHERE Side = 'buy' AND Rank <= 2
            ORDER BY Net_Qty DESC
            LIMIT 6
        """).df()
        if not df_brk.empty:
            log_and_append("| 代號 | 股票名稱 | 買超主力分點 | 淨買超 (張) | 買超佔比 | 該股分點總買量 | 買超均價 |")
            log_and_append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
            for _, r in df_brk.iterrows():
                log_and_append(f"| **{r['Ticker']}** | {r['Name']} | {r['Broker_Name']} | +{r['Net_Qty']:,} | {r['Share_Pct']} | {r['Total_Buy']:,} | {r['Avg_Buy_Cost']} |")
            log_and_append("")

    # -------------------------------------------------------------
    # 8. 價值成長優選篩選 (高殖利率 + 成長 + 合理估值)
    # -------------------------------------------------------------
    val_file = f"data/valuation/{target_date}.parquet"
    rev_files = sorted(glob.glob("data/fundamental/revenue/*.parquet"))
    eps_files = sorted(glob.glob("data/fundamental/eps/*.parquet"))
    if os.path.exists(val_file) and rev_files and eps_files:
        log_and_append("## 8. 💎 價值成長量化精選 (殖利率 > 4% + 本益比 < 18 + 營收成長)")
        latest_rev = rev_files[-1]
        latest_eps = eps_files[-1]
        df_val_growth = con.execute(f"""
            SELECT v.Ticker, v.Name, v.Close_Price, v.PE_Ratio, v.Dividend_Yield,
                   r.YoY_Growth as Rev_YoY, e.EPS as Latest_Quarter_EPS
            FROM read_parquet('{val_file}') v
            JOIN read_parquet('{latest_rev}') r ON v.Ticker = r.Ticker
            JOIN read_parquet('{latest_eps}') e ON v.Ticker = e.Ticker
            WHERE v.Dividend_Yield >= 4.0
              AND v.PE_Ratio BETWEEN 5.0 AND 18.0
              AND r.YoY_Growth > 10.0
            ORDER BY v.Dividend_Yield DESC, r.YoY_Growth DESC
            LIMIT 8
        """).df()
        if not df_val_growth.empty:
            log_and_append("| 代號 | 股票名稱 | 收盤價 | 本益比 | 殖利率 (%) | 營收年增率 (%) | 最新季 EPS |")
            log_and_append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- |")
            for _, r in df_val_growth.iterrows():
                close_str = f"{r['Close_Price']:.2f}" if pd.notna(r['Close_Price']) else "--"
                log_and_append(f"| **{r['Ticker']}** | {r['Name']} | {close_str} | {r['PE_Ratio']:.2f} | **{r['Dividend_Yield']:.2f}%** | +{r['Rev_YoY']:.2f}% | {r['Latest_Quarter_EPS']:.2f} |")
            log_and_append("")

    if save_md:
        out_path = os.path.join(REPORT_DIR, f"{target_date}_market_summary.md")
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(md_lines) + "\n")
        print(f"\n[OK] 每日量化總評報告已成功儲存至 {out_path}")
        return out_path
    return None

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="產生每日台股全方位量化盤後日報 (Markdown & Console)")
    parser.add_argument("--date", type=str, default=None, help="指定日期 (格式: YYYY-MM-DD)")
    args = parser.parse_args()
    generate_report(args.date)
