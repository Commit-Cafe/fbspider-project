# -*- coding: utf-8 -*-
"""
数据库适配层 - 支持 MongoDB 和 SQLite 无缝切换
用于单用户场景的轻量化部署
"""
import os
import json
import sqlite3
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from contextlib import contextmanager


class SQLiteAdapter:
    """SQLite 适配器，模拟 MongoDB 的 API"""

    def __init__(self, db_path: str = "fbspider.db"):
        self.db_path = db_path
        self._init_tables()

    @contextmanager
    def _get_conn(self):
        """获取数据库连接（上下文管理器）"""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row  # 返回字典格式
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_tables(self):
        """初始化数据库表结构"""
        with self._get_conn() as conn:
            cursor = conn.cursor()

            # 用户表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT DEFAULT 'user',
                    status TEXT DEFAULT 'active',
                    created_at TEXT,
                    created_by TEXT,
                    last_login TEXT
                )
            """)

            # API Keys
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    key_hash TEXT UNIQUE NOT NULL,
                    scope TEXT,
                    created_at TEXT,
                    last_used TEXT
                )
            """)

            # 认证会话
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS auth_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    token_hash TEXT UNIQUE NOT NULL,
                    expires_at TEXT,
                    created_at TEXT
                )
            """)

            # 命令队列
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS command_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    command_type TEXT NOT NULL,
                    params TEXT,
                    status TEXT DEFAULT 'pending',
                    result TEXT,
                    trace_id TEXT,
                    created_at TEXT,
                    completed_at TEXT
                )
            """)

            # 广告账户
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS ad_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    account_name TEXT,
                    account_status TEXT,
                    currency TEXT,
                    timezone_name TEXT,
                    updated_at TEXT,
                    UNIQUE(user_id, account_id)
                )
            """)

            # BM 列表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS bm_list (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    bm_id TEXT NOT NULL,
                    bm_name TEXT,
                    updated_at TEXT,
                    UNIQUE(user_id, bm_id)
                )
            """)

            # Pixels
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS pixels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    pixel_id TEXT NOT NULL,
                    pixel_name TEXT,
                    updated_at TEXT,
                    UNIQUE(user_id, pixel_id)
                )
            """)

            # 操作日志
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS action_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT,
                    action TEXT NOT NULL,
                    details TEXT,
                    created_at TEXT
                )
            """)

            # 创建索引
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_users_username ON users(username)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_command_queue_user_status ON command_queue(user_id, status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_ad_accounts_user ON ad_accounts(user_id)")

            conn.commit()

    def collection(self, name: str):
        """返回集合操作对象（模拟 MongoDB collection）"""
        return SQLiteCollection(self.db_path, name)


class SQLiteCollection:
    """模拟 MongoDB Collection 的 API"""

    def __init__(self, db_path: str, table_name: str):
        self.db_path = db_path
        self.table_name = table_name

    @contextmanager
    def _get_conn(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _row_to_dict(self, row) -> Dict:
        """将 SQLite Row 转换为字典"""
        if row is None:
            return None
        d = dict(row)
        # 将 id 映射为 _id（兼容 MongoDB）
        if 'id' in d:
            d['_id'] = d['id']
        return d

    def find_one(self, query: Dict = None) -> Optional[Dict]:
        """查找单条记录"""
        query = query or {}
        with self._get_conn() as conn:
            cursor = conn.cursor()

            if not query:
                cursor.execute(f"SELECT * FROM {self.table_name} LIMIT 1")
            else:
                where_clause, params = self._build_where(query)
                cursor.execute(f"SELECT * FROM {self.table_name} WHERE {where_clause} LIMIT 1", params)

            row = cursor.fetchone()
            return self._row_to_dict(row)

    def find(self, query: Dict = None, projection: Dict = None) -> List[Dict]:
        """查找多条记录"""
        query = query or {}
        with self._get_conn() as conn:
            cursor = conn.cursor()

            if not query:
                cursor.execute(f"SELECT * FROM {self.table_name}")
            else:
                where_clause, params = self._build_where(query)
                cursor.execute(f"SELECT * FROM {self.table_name} WHERE {where_clause}", params)

            rows = cursor.fetchall()
            return [self._row_to_dict(row) for row in rows]

    def insert_one(self, document: Dict) -> Any:
        """插入单条记录"""
        with self._get_conn() as conn:
            cursor = conn.cursor()

            # 移除 _id（SQLite 自动生成）
            doc = document.copy()
            doc.pop('_id', None)

            # 处理 JSON 字段
            for key, value in doc.items():
                if isinstance(value, (dict, list)):
                    doc[key] = json.dumps(value, ensure_ascii=False)

            columns = ', '.join(doc.keys())
            placeholders = ', '.join(['?' for _ in doc])

            cursor.execute(
                f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})",
                list(doc.values())
            )

            # 返回插入的 ID
            class InsertResult:
                def __init__(self, inserted_id):
                    self.inserted_id = inserted_id

            return InsertResult(cursor.lastrowid)

    def update_one(self, query: Dict, update: Dict) -> Any:
        """更新单条记录"""
        with self._get_conn() as conn:
            cursor = conn.cursor()

            # 处理 $set 操作符
            if '$set' in update:
                update_data = update['$set']
            else:
                update_data = update

            # 处理 JSON 字段
            for key, value in update_data.items():
                if isinstance(value, (dict, list)):
                    update_data[key] = json.dumps(value, ensure_ascii=False)

            set_clause = ', '.join([f"{k} = ?" for k in update_data.keys()])
            where_clause, where_params = self._build_where(query)

            cursor.execute(
                f"UPDATE {self.table_name} SET {set_clause} WHERE {where_clause}",
                list(update_data.values()) + where_params
            )

            class UpdateResult:
                def __init__(self, modified_count):
                    self.modified_count = modified_count

            return UpdateResult(cursor.rowcount)

    def delete_one(self, query: Dict) -> Any:
        """删除单条记录"""
        with self._get_conn() as conn:
            cursor = conn.cursor()
            where_clause, params = self._build_where(query)
            cursor.execute(f"DELETE FROM {self.table_name} WHERE {where_clause} LIMIT 1", params)

            class DeleteResult:
                def __init__(self, deleted_count):
                    self.deleted_count = deleted_count

            return DeleteResult(cursor.rowcount)

    def count_documents(self, query: Dict = None) -> int:
        """统计记录数"""
        query = query or {}
        with self._get_conn() as conn:
            cursor = conn.cursor()

            if not query:
                cursor.execute(f"SELECT COUNT(*) FROM {self.table_name}")
            else:
                where_clause, params = self._build_where(query)
                cursor.execute(f"SELECT COUNT(*) FROM {self.table_name} WHERE {where_clause}", params)

            return cursor.fetchone()[0]

    def _build_where(self, query: Dict) -> tuple:
        """构建 WHERE 子句"""
        if not query:
            return "1=1", []

        conditions = []
        params = []

        for key, value in query.items():
            if isinstance(value, dict):
                # 处理操作符（如 $gte, $lte）
                for op, val in value.items():
                    if op == '$gte':
                        conditions.append(f"{key} >= ?")
                        params.append(val)
                    elif op == '$lte':
                        conditions.append(f"{key} <= ?")
                        params.append(val)
                    elif op == '$ne':
                        conditions.append(f"{key} != ?")
                        params.append(val)
            else:
                conditions.append(f"{key} = ?")
                params.append(value)

        return ' AND '.join(conditions), params


def get_db_adapter(use_sqlite: bool = True):
    """获取数据库适配器"""
    if use_sqlite:
        return SQLiteAdapter()
    else:
        # 保留 MongoDB 支持
        from models import get_db
        return get_db()
