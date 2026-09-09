import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "tw_stock.db")

class CompatSQLiteConnection:
    """
    相容型 SQLite 連線包裝器：
    - 支援使用 %s 作為佔位符 (自動轉為 SQLite 標準之 ?)
    - 支援 sqlite3.Row (欄位名稱字典與下標索引雙重存取)
    - 提供標準 execute, executescript, commit, close 介面
    """
    def __init__(self, db_path=DB_PATH):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def execute(self, sql, params=None):
        clean_sql = sql.replace('%s', '?')
        cur = self.conn.cursor()
        if params is not None:
            cur.execute(clean_sql, params)
        else:
            cur.execute(clean_sql)
        return cur

    def executescript(self, script):
        clean_script = script.replace('%s', '?')
        return self.conn.executescript(clean_script)

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

def get_conn(db_path=None):
    if db_path is None:
        db_path = DB_PATH
    return CompatSQLiteConnection(db_path)

