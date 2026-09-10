"""
分點主力 (Broker Flow) 服務層 — 券商分點進出資料
資料來源: fubon-ebrokerdj.fbs.com.tw (嘉實資訊)
提供即時抓取、HTML 解析、本地 SQLite 快取管理機制與 Parquet 匯出
"""
import os
import sys
import logging
import re
import argparse
import urllib3
from datetime import datetime
import requests
import pandas as pd

try:
    from .db_helper import get_conn
except (ImportError, ValueError):
    from db_helper import get_conn

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

FUBON_URL = 'https://fubon-ebrokerdj.fbs.com.tw/z/zc/zco/zco_{stock}_{period}.djhtm'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

PARQUET_OUTPUT_DIR = "data/chips/broker_trading"
os.makedirs(PARQUET_OUTPUT_DIR, exist_ok=True)

PERIOD_MAP = {
    1: ('近一日', 1),
    2: ('近五日', 5),
    3: ('近十日', 10),
    4: ('近20日', 20),
    5: ('近40日', 40),
    6: ('近60日', 60),
    7: ('近120日', 120),
    8: ('近240日', 240),
}

def init_broker_table():
    """建立分點主力資料表與元資料表"""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tw_broker_trading (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fetch_date TEXT NOT NULL,
            stock_id TEXT NOT NULL,
            period INTEGER NOT NULL,
            side TEXT NOT NULL,
            rank INTEGER NOT NULL,
            broker_id TEXT,
            broker_name TEXT NOT NULL,
            buy_qty INTEGER DEFAULT 0,
            sell_qty INTEGER DEFAULT 0,
            net_qty INTEGER DEFAULT 0,
            pct TEXT,
            updated_at TEXT DEFAULT (datetime('now', 'localtime')),
            UNIQUE(fetch_date, stock_id, period, side, rank)
        );
        CREATE INDEX IF NOT EXISTS idx_broker_stock ON tw_broker_trading(stock_id, fetch_date);

        CREATE TABLE IF NOT EXISTS tw_broker_meta (
            fetch_date TEXT NOT NULL,
            stock_id TEXT NOT NULL,
            period INTEGER NOT NULL,
            total_buy INTEGER,
            total_sell INTEGER,
            avg_buy_cost TEXT,
            avg_sell_cost TEXT,
            updated_at TEXT DEFAULT (datetime('now', 'localtime')),
            PRIMARY KEY(fetch_date, stock_id, period)
        );

        CREATE TABLE IF NOT EXISTS symbol_names (
            symbol TEXT PRIMARY KEY,
            name_zh TEXT
        );
    """)

    # 若 symbol_names 為空，自 tw_stock_list 匯入基本標的名稱
    check = conn.execute("SELECT COUNT(*) as cnt FROM symbol_names").fetchone()
    if check and check['cnt'] == 0:
        stock_list_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "tw_stock_list.parquet")
        if os.path.exists(stock_list_path):
            try:
                sdf = pd.read_parquet(stock_list_path)
                for _, r in sdf.iterrows():
                    sym = str(r['Symbol']).strip()
                    nm = str(r['Name']).strip()
                    conn.execute("INSERT OR IGNORE INTO symbol_names (symbol, name_zh) VALUES (%s, %s)", (sym, nm))
            except Exception as e:
                logging.warning("Failed to populate symbol_names: %s", e)

    conn.commit()
    conn.close()

def _parse_number(s):
    """解析數字字串 (移除逗號)"""
    if not s:
        return 0
    clean_s = re.sub(r'[^\d\-]', '', str(s))
    try:
        return int(clean_s)
    except ValueError:
        return 0

def _parse_broker_html(html):
    """解析 Fubon DJ 分點主力 HTML，回傳 (buy_list, sell_list, meta)"""
    buy_list = []
    sell_list = []
    meta = {}

    date_match = re.search(r'最後更新日[：:]\s*([\d/]+)', html)
    if date_match:
        meta['last_update'] = date_match.group(1).replace('/', '-')

    rows = re.findall(r'<TR>\s*(.*?)\s*</TR>', html, re.DOTALL | re.IGNORECASE)

    for row in rows:
        cells = re.findall(r'<TD[^>]*>(.*?)</TD>', row, re.DOTALL | re.IGNORECASE)
        if len(cells) != 10:
            continue

        # 左邊5欄: 買超券商
        buy_broker_match = re.search(r'BHID=([^"\']+)["\']>([^<]+)</a>', cells[0])
        if buy_broker_match:
            broker_id = buy_broker_match.group(1)
            broker_name = buy_broker_match.group(2).strip()
            buy_qty = _parse_number(re.sub(r'<[^>]+>', '', cells[1]))
            sell_qty = _parse_number(re.sub(r'<[^>]+>', '', cells[2]))
            net_qty = _parse_number(re.sub(r'<[^>]+>', '', cells[3]))
            pct = re.sub(r'<[^>]+>', '', cells[4]).strip()
            buy_list.append({
                'broker_id': broker_id,
                'broker_name': broker_name,
                'buy_qty': buy_qty,
                'sell_qty': sell_qty,
                'net_qty': net_qty,
                'pct': pct,
            })

        # 右邊5欄: 賣超券商
        sell_broker_match = re.search(r'BHID=([^"\']+)["\']>([^<]+)</a>', cells[5])
        if sell_broker_match:
            broker_id = sell_broker_match.group(1)
            broker_name = sell_broker_match.group(2).strip()
            buy_qty = _parse_number(re.sub(r'<[^>]+>', '', cells[6]))
            sell_qty = _parse_number(re.sub(r'<[^>]+>', '', cells[7]))
            net_qty = _parse_number(re.sub(r'<[^>]+>', '', cells[8]))
            pct = re.sub(r'<[^>]+>', '', cells[9]).strip()
            sell_list.append({
                'broker_id': broker_id,
                'broker_name': broker_name,
                'buy_qty': buy_qty,
                'sell_qty': sell_qty,
                'net_qty': net_qty,
                'pct': pct,
            })

    total_buy_match = re.search(r'合計買超張數.*?<td[^>]*>([^<]+)</td>', html, re.DOTALL | re.IGNORECASE)
    total_sell_match = re.search(r'合計賣超張數.*?<td[^>]*>([^<]+)</td>', html, re.DOTALL | re.IGNORECASE)
    avg_buy_match = re.search(r'(?:平均買超成本|買超均價).*?<td[^>]*>([^<]+)</td>', html, re.DOTALL | re.IGNORECASE)
    avg_sell_match = re.search(r'(?:平均賣超成本|賣超均價).*?<td[^>]*>([^<]+)</td>', html, re.DOTALL | re.IGNORECASE)

    if total_buy_match:
        meta['total_buy'] = _parse_number(total_buy_match.group(1))
    if total_sell_match:
        meta['total_sell'] = _parse_number(total_sell_match.group(1))
    if avg_buy_match:
        meta['avg_buy_cost'] = avg_buy_match.group(1).strip().replace(',', '')
    if avg_sell_match:
        meta['avg_sell_cost'] = avg_sell_match.group(1).strip().replace(',', '')

    return buy_list, sell_list, meta

def fetch_broker_trading(stock_id, period=1):
    """
    實時抓取個股分點主力資料並存入 DB

    Args:
        stock_id: 股票代碼 (例如 '2330')
        period: 1=近1日, 2=近5日, 3=近10日, 4=近20日, 5=近40日, 6=近60日

    Returns:
        dict with buy_list, sell_list, meta, stock_id, period
    """
    label = PERIOD_MAP.get(period, ('近一日', 1))[0]
    url = FUBON_URL.format(stock=stock_id, period=period)
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30, verify=False)
        resp.encoding = 'big5'
        html = resp.text
    except Exception as e:
        logging.error("fetch_broker_trading failed for %s: %s", stock_id, e)
        return None

    buy_list, sell_list, meta = _parse_broker_html(html)

    if not buy_list and not sell_list:
        return None

    if not meta.get('last_update'):
        logging.warning("個股 %s 分點資料未解析到官方最後更新日，略過以防誤標日期。", stock_id)
        return None

    result = {
        'stock_id': stock_id,
        'period': period,
        'period_label': label,
        'buy_list': buy_list,
        'sell_list': sell_list,
        'meta': meta,
    }

    _save_to_db(result)
    return result

def _save_to_db(result):
    """儲存分點資料與元資料到 SQLite"""
    init_broker_table()
    conn = get_conn()
    meta = result.get('meta', {})
    today = meta.get('last_update')
    if not today:
        conn.close()
        return
    stock_id = result['stock_id']
    period = result['period']

    for rank, item in enumerate(result['buy_list'], 1):
        try:
            conn.execute("""
                INSERT INTO tw_broker_trading
                (fetch_date, stock_id, period, side, rank, broker_id, broker_name,
                 buy_qty, sell_qty, net_qty, pct)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (fetch_date, stock_id, period, side, rank) 
                DO UPDATE SET 
                    broker_id=EXCLUDED.broker_id, broker_name=EXCLUDED.broker_name,
                    buy_qty=EXCLUDED.buy_qty, sell_qty=EXCLUDED.sell_qty,
                    net_qty=EXCLUDED.net_qty, pct=EXCLUDED.pct,
                    updated_at=CURRENT_TIMESTAMP
            """, (today, stock_id, period, 'buy', rank,
                  item['broker_id'], item['broker_name'],
                  item['buy_qty'], item['sell_qty'], item['net_qty'], item['pct']))
        except Exception as e:
            logging.warning("broker_trading buy insert error: %s", e)

    for rank, item in enumerate(result['sell_list'], 1):
        try:
            conn.execute("""
                INSERT INTO tw_broker_trading
                (fetch_date, stock_id, period, side, rank, broker_id, broker_name,
                 buy_qty, sell_qty, net_qty, pct)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (fetch_date, stock_id, period, side, rank) 
                DO UPDATE SET 
                    broker_id=EXCLUDED.broker_id, broker_name=EXCLUDED.broker_name,
                    buy_qty=EXCLUDED.buy_qty, sell_qty=EXCLUDED.sell_qty,
                    net_qty=EXCLUDED.net_qty, pct=EXCLUDED.pct,
                    updated_at=CURRENT_TIMESTAMP
            """, (today, stock_id, period, 'sell', rank,
                  item['broker_id'], item['broker_name'],
                  item['buy_qty'], item['sell_qty'], item['net_qty'], item['pct']))
        except Exception as e:
            logging.warning("broker_trading sell insert error: %s", e)

    try:
        conn.execute("""
            INSERT INTO tw_broker_meta
            (fetch_date, stock_id, period, total_buy, total_sell, avg_buy_cost, avg_sell_cost)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (fetch_date, stock_id, period)
            DO UPDATE SET
                total_buy=EXCLUDED.total_buy, total_sell=EXCLUDED.total_sell,
                avg_buy_cost=EXCLUDED.avg_buy_cost, avg_sell_cost=EXCLUDED.avg_sell_cost
        """, (today, stock_id, period,
              meta.get('total_buy'), meta.get('total_sell'),
              meta.get('avg_buy_cost'), meta.get('avg_sell_cost')))
    except Exception as e:
        logging.warning("broker_meta insert error: %s", e)

    conn.commit()
    conn.close()

def get_broker_trading(stock_id, period=1):
    """
    從 DB 讀取分點資料，若今日尚無快取或缺少完整成本資料，則即時線上抓取刷新
    """
    init_broker_table()
    conn = get_conn()
    today = datetime.now().strftime('%Y-%m-%d')
    label = PERIOD_MAP.get(period, ('近一日', 1))[0]

    existing = conn.execute(
        "SELECT COUNT(*) as cnt FROM tw_broker_trading WHERE stock_id=%s AND period=%s AND fetch_date=%s",
        (stock_id, period, today)
    ).fetchone()

    meta_row = None
    if existing and existing['cnt'] > 0:
        meta_row = conn.execute(
            "SELECT total_buy, total_sell, avg_buy_cost, avg_sell_cost FROM tw_broker_meta WHERE stock_id=%s AND period=%s AND fetch_date=%s",
            (stock_id, period, today)
        ).fetchone()

    if not existing or existing['cnt'] == 0 or not meta_row or meta_row['avg_buy_cost'] is None:
        conn.close()
        res = fetch_broker_trading(stock_id, period)
        if res:
            return res
        
        conn = get_conn()
        latest_date_row = conn.execute(
            "SELECT MAX(fetch_date) as max_date FROM tw_broker_trading WHERE stock_id=%s AND period=%s",
            (stock_id, period)
        ).fetchone()
        if not latest_date_row or not latest_date_row['max_date']:
            conn.close()
            return None
        today = latest_date_row['max_date']
        meta_row = conn.execute(
            "SELECT total_buy, total_sell, avg_buy_cost, avg_sell_cost FROM tw_broker_meta WHERE stock_id=%s AND period=%s AND fetch_date=%s",
            (stock_id, period, today)
        ).fetchone()

    buy_rows = conn.execute("""
        SELECT broker_id, broker_name, buy_qty, sell_qty, net_qty, pct
        FROM tw_broker_trading
        WHERE stock_id=%s AND period=%s AND fetch_date=%s AND side='buy'
        ORDER BY rank ASC
    """, (stock_id, period, today)).fetchall()

    sell_rows = conn.execute("""
        SELECT broker_id, broker_name, buy_qty, sell_qty, net_qty, pct
        FROM tw_broker_trading
        WHERE stock_id=%s AND period=%s AND fetch_date=%s AND side='sell'
        ORDER BY rank ASC
    """, (stock_id, period, today)).fetchall()

    conn.close()

    buy_list = [dict(r) for r in buy_rows]
    sell_list = [dict(r) for r in sell_rows]

    total_buy = (meta_row and meta_row['total_buy']) or sum(b['buy_qty'] for b in buy_list)
    total_sell = (meta_row and meta_row['total_sell']) or sum(s['sell_qty'] for s in sell_list)
    avg_buy_cost = meta_row['avg_buy_cost'] if meta_row else None
    avg_sell_cost = meta_row['avg_sell_cost'] if meta_row else None

    return {
        'stock_id': stock_id,
        'period': period,
        'period_label': label,
        'buy_list': buy_list,
        'sell_list': sell_list,
        'meta': {
            'last_update': today,
            'total_buy': total_buy if total_buy and total_buy > 0 else None,
            'total_sell': total_sell if total_sell and total_sell > 0 else None,
            'avg_buy_cost': avg_buy_cost,
            'avg_sell_cost': avg_sell_cost,
        }
    }

def get_broker_summary(limit=8):
    """取得分點主力摘要 — 今日買超冠軍分點"""
    init_broker_table()
    conn = get_conn()
    try:
        latest_row = conn.execute("SELECT MAX(fetch_date) FROM tw_broker_trading").fetchone()
        latest = latest_row[0] if latest_row else None
        if not latest:
            conn.close()
            return []
        rows = conn.execute("""
            SELECT b.stock_id, b.broker_name, b.net_qty, b.pct, s.name_zh
            FROM tw_broker_trading b
            LEFT JOIN symbol_names s ON b.stock_id = s.symbol
            WHERE b.fetch_date = %s AND b.period = 1 AND b.side = 'buy' AND b.rank = 1
            ORDER BY ABS(b.net_qty) DESC LIMIT %s
        """, (latest, limit)).fetchall()
        conn.close()
        return [{
            "stock_id": r[0],
            "stock_name": r[4] or r[0],
            "broker_name": r[1],
            "net_qty": r[2],
            "pct": r[3],
            "date": latest
        } for r in rows]
    except Exception as e:
        logging.error("get_broker_summary failed: %s", e)
        conn.close()
        return []

def export_to_parquet(target_date=None):
    """將 SQLite 中的券商分點明細匯出為標準 Parquet 格式，支援 DuckDB 查詢"""
    conn = get_conn()
    if target_date is None:
        latest_row = conn.execute("SELECT MAX(fetch_date) FROM tw_broker_trading").fetchone()
        if not latest_row or not latest_row[0]:
            conn.close()
            return None
        target_date = latest_row[0]

    rows = conn.execute("""
        SELECT b.fetch_date as Date, b.stock_id as Ticker, s.name_zh as Name,
               b.period as Period, b.side as Side, b.rank as Rank,
               b.broker_id as Broker_ID, b.broker_name as Broker_Name,
               b.buy_qty as Buy_Qty, b.sell_qty as Sell_Qty, b.net_qty as Net_Qty,
               b.pct as Share_Pct,
               m.total_buy as Total_Buy, m.total_sell as Total_Sell,
               m.avg_buy_cost as Avg_Buy_Cost, m.avg_sell_cost as Avg_Sell_Cost
        FROM tw_broker_trading b
        LEFT JOIN symbol_names s ON b.stock_id = s.symbol
        LEFT JOIN tw_broker_meta m ON b.stock_id = m.stock_id AND b.fetch_date = m.fetch_date AND b.period = m.period
        WHERE b.fetch_date = %s
    """, (target_date,)).fetchall()
    conn.close()

    if not rows:
        return None

    df = pd.DataFrame([dict(r) for r in rows])
    out_file = os.path.join(PARQUET_OUTPUT_DIR, f"{target_date}.parquet")
    df.to_parquet(out_file, engine='pyarrow', compression='snappy', index=False)
    print(f"[{datetime.now()}] 成功匯出 {len(df)} 筆券商分點明細至 {out_file}")
    return out_file

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="抓取並查詢券商分點主力資料 (Fubon DJ)")
    parser.add_argument("--stocks", nargs="+", default=["2330", "2317", "2454"], help="指定股票代號清單")
    parser.add_argument("--period", type=int, default=1, help="週期: 1=近1日, 2=近5日, 3=近10日, 4=近20日")
    parser.add_argument("--export-parquet", action="store_true", help="是否匯出為 Parquet")
    args = parser.parse_args()

    for stk in args.stocks:
        print(f"正在抓取 {stk} 分點主力 (週期={args.period})...")
        res = fetch_broker_trading(stk, period=args.period)
        if res:
            meta = res['meta']
            print(f"  {stk} 買超前3: {[b['broker_name'] + '(' + str(b['net_qty']) + '張)' for b in res['buy_list'][:3]]}")
            print(f"  {stk} 賣超前3: {[s['broker_name'] + '(' + str(s['net_qty']) + '張)' for s in res['sell_list'][:3]]}")
            print(f"  合計買超: {meta.get('total_buy')} 張, 均價: {meta.get('avg_buy_cost')} | 合計賣超: {meta.get('total_sell')} 張, 均價: {meta.get('avg_sell_cost')}")

    if args.export_parquet:
        export_to_parquet()

    print("\n今日買超冠軍分點摘要:")
    summary = get_broker_summary(limit=5)
    for s in summary:
        print(f"  [{s['date']}] {s['stock_id']} {s['stock_name']} -> {s['broker_name']} 淨買 {s['net_qty']} 張 ({s['pct']})")

