"""
存储层 - SQLite数据库操作

Phase 1主存储：原始消息、聚合统计、告警记录
"""

import sqlite3
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, asdict

# 消息数据模型
@dataclass
class Message:
    """消息数据模型"""
    message_id: str
    chat_id: str
    chat_type: str  # group, p2p
    sender_id: str
    sender_type: str  # user, bot
    content: str
    content_type: str  # text, image, file, etc.
    timestamp: datetime
    raw_event: Optional[Dict] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        data['timestamp'] = self.timestamp.isoformat()
        if self.raw_event:
            data['raw_event'] = json.dumps(self.raw_event, ensure_ascii=False)
        return data


@dataclass
class AlertRecord:
    """告警记录数据模型"""
    alert_id: str
    chat_id: str
    alert_type: str
    severity: str  # info, warning, critical
    message: str
    details: Optional[Dict] = None
    timestamp: Optional[datetime] = None
    acknowledged: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        data = asdict(self)
        if self.timestamp:
            data['timestamp'] = self.timestamp.isoformat()
        if self.details:
            data['details'] = json.dumps(self.details, ensure_ascii=False)
        return data


class MessageStore:
    """消息存储管理器"""
    
    def __init__(self, db_path: str = None):
        """
        初始化存储管理器
        
        Args:
            db_path: 数据库路径，None则使用默认路径
        """
        if db_path is None:
            db_path = str(Path.home() / ".hermes" / "data" / "blastogene.db")
        
        self.db_path = db_path
        
        # 确保目录存在
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        
        # 初始化数据库连接
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        
        # 设置SQLite优化参数
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        
        # 初始化数据库表
        self._init_db()
    
    def _init_db(self):
        """初始化数据库表"""
        try:
            # 原始消息表
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    chat_type TEXT DEFAULT 'group',
                    sender_id TEXT NOT NULL,
                    sender_type TEXT DEFAULT 'user',
                    content TEXT,
                    content_type TEXT DEFAULT 'text',
                    timestamp TEXT NOT NULL,
                    raw_event TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # 创建索引
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_chat_id ON messages(chat_id)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_timestamp ON messages(timestamp)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_messages_sender_id ON messages(sender_id)")
            
            # 聚合统计表
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS aggregated_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id TEXT NOT NULL,
                    metric_type TEXT NOT NULL,
                    metric_value REAL,
                    period TEXT NOT NULL,
                    period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(chat_id, metric_type, period, period_start)
                )
            """)
            
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_stats_chat_metric ON aggregated_stats(chat_id, metric_type)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_stats_period ON aggregated_stats(period, period_start)")
            
            # 告警记录表
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    alert_id TEXT PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    alert_type TEXT NOT NULL,
                    severity TEXT DEFAULT 'info',
                    message TEXT,
                    details TEXT,
                    timestamp TEXT NOT NULL,
                    acknowledged INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_chat_id ON alerts(chat_id)")
            self._conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_timestamp ON alerts(timestamp)")
            
            self._conn.commit()
            
        except Exception as e:
            raise RuntimeError(f"Failed to initialize database: {e}")
    
    def store_message(self, message: Message) -> bool:
        """
        存储消息（幂等）
        
        Returns:
            True: 新消息已存储
            False: 消息已存在（跳过）
        """
        try:
            # 幂等检查
            existing = self._conn.execute(
                "SELECT message_id FROM messages WHERE message_id = ?",
                (message.message_id,)
            ).fetchone()
            
            if existing:
                return False
            
            # 插入新消息
            self._conn.execute(
                """
                INSERT INTO messages (message_id, chat_id, chat_type, sender_id, sender_type, content, content_type, timestamp, raw_event)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message.message_id,
                    message.chat_id,
                    message.chat_type,
                    message.sender_id,
                    message.sender_type,
                    message.content,
                    message.content_type,
                    message.timestamp.isoformat(),
                    json.dumps(message.raw_event, ensure_ascii=False) if message.raw_event else None
                )
            )
            
            self._conn.commit()
            return True
            
        except Exception as e:
            self._conn.rollback()
            raise RuntimeError(f"Failed to store message: {e}")
    
    def store_messages_batch(self, messages: List[Message]) -> int:
        """
        批量存储消息（幂等）
        
        Returns:
            新存储的消息数量
        """
        stored_count = 0
        
        try:
            for message in messages:
                # 幂等检查
                existing = self._conn.execute(
                    "SELECT message_id FROM messages WHERE message_id = ?",
                    (message.message_id,)
                ).fetchone()
                
                if existing:
                    continue
                
                # 插入新消息
                self._conn.execute(
                    """
                    INSERT INTO messages (message_id, chat_id, chat_type, sender_id, sender_type, content, content_type, timestamp, raw_event)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        message.message_id,
                        message.chat_id,
                        message.chat_type,
                        message.sender_id,
                        message.sender_type,
                        message.content,
                        message.content_type,
                        message.timestamp.isoformat(),
                        json.dumps(message.raw_event, ensure_ascii=False) if message.raw_event else None
                    )
                )
                
                stored_count += 1
            
            self._conn.commit()
            return stored_count
            
        except Exception as e:
            self._conn.rollback()
            raise RuntimeError(f"Failed to store messages batch: {e}")
    
    def get_messages(
        self,
        chat_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        sender_id: Optional[str] = None,
        content_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Message]:
        """
        获取消息列表
        
        Args:
            chat_id: 群组ID
            start_time: 开始时间
            end_time: 结束时间
            sender_id: 发送者ID
            content_type: 内容类型
            limit: 返回数量限制
            offset: 偏移量
        
        Returns:
            消息列表
        """
        query = "SELECT * FROM messages WHERE chat_id = ?"
        params = [chat_id]
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())
        
        if sender_id:
            query += " AND sender_id = ?"
            params.append(sender_id)
        
        if content_type:
            query += " AND content_type = ?"
            params.append(content_type)
        
        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        rows = self._conn.execute(query, params).fetchall()
        
        return [
            Message(
                message_id=row['message_id'],
                chat_id=row['chat_id'],
                chat_type=row['chat_type'],
                sender_id=row['sender_id'],
                sender_type=row['sender_type'],
                content=row['content'],
                content_type=row['content_type'],
                timestamp=datetime.fromisoformat(row['timestamp']),
                raw_event=json.loads(row['raw_event']) if row['raw_event'] else None
            )
            for row in rows
        ]
    
    def get_message_count(
        self,
        chat_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> int:
        """
        获取消息数量
        
        Args:
            chat_id: 群组ID
            start_time: 开始时间
            end_time: 结束时间
        
        Returns:
            消息数量
        """
        query = "SELECT COUNT(*) as count FROM messages WHERE chat_id = ?"
        params = [chat_id]
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())
        
        result = self._conn.execute(query, params).fetchone()
        return result['count'] if result else 0
    
    def get_unique_senders(
        self,
        chat_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[str]:
        """
        获取唯一发送者列表
        
        Args:
            chat_id: 群组ID
            start_time: 开始时间
            end_time: 结束时间
        
        Returns:
            发送者ID列表
        """
        query = "SELECT DISTINCT sender_id FROM messages WHERE chat_id = ?"
        params = [chat_id]
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())
        
        rows = self._conn.execute(query, params).fetchall()
        return [row['sender_id'] for row in rows]
    
    def store_aggregated_stat(
        self,
        chat_id: str,
        metric_type: str,
        metric_value: float,
        period: str,
        period_start: datetime,
        period_end: datetime
    ):
        """
        存储聚合统计
        
        Args:
            chat_id: 群组ID
            metric_type: 指标类型
            metric_value: 指标值
            period: 周期类型 (hourly, daily, weekly)
            period_start: 周期开始时间
            period_end: 周期结束时间
        """
        try:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO aggregated_stats 
                (chat_id, metric_type, metric_value, period, period_start, period_end)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    chat_id,
                    metric_type,
                    metric_value,
                    period,
                    period_start.isoformat(),
                    period_end.isoformat()
                )
            )
            
            self._conn.commit()
            
        except Exception as e:
            self._conn.rollback()
            raise RuntimeError(f"Failed to store aggregated stat: {e}")
    
    def get_aggregated_stats(
        self,
        chat_id: str,
        metric_type: str,
        period: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        获取聚合统计
        
        Args:
            chat_id: 群组ID
            metric_type: 指标类型
            period: 周期类型
            start_time: 开始时间
            end_time: 结束时间
            limit: 返回数量限制
        
        Returns:
            聚合统计列表
        """
        query = """
            SELECT * FROM aggregated_stats 
            WHERE chat_id = ? AND metric_type = ? AND period = ?
        """
        params = [chat_id, metric_type, period]
        
        if start_time:
            query += " AND period_start >= ?"
            params.append(start_time.isoformat())
        
        if end_time:
            query += " AND period_end <= ?"
            params.append(end_time.isoformat())
        
        query += " ORDER BY period_start DESC LIMIT ?"
        params.append(limit)
        
        rows = self._conn.execute(query, params).fetchall()
        
        return [
            {
                'id': row['id'],
                'chat_id': row['chat_id'],
                'metric_type': row['metric_type'],
                'metric_value': row['metric_value'],
                'period': row['period'],
                'period_start': row['period_start'],
                'period_end': row['period_end'],
                'created_at': row['created_at']
            }
            for row in rows
        ]
    
    def store_alert(self, alert: AlertRecord):
        """
        存储告警记录
        
        Args:
            alert: 告警记录
        """
        try:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO alerts 
                (alert_id, chat_id, alert_type, severity, message, details, timestamp, acknowledged)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    alert.alert_id,
                    alert.chat_id,
                    alert.alert_type,
                    alert.severity,
                    alert.message,
                    json.dumps(alert.details, ensure_ascii=False) if alert.details else None,
                    alert.timestamp.isoformat() if alert.timestamp else datetime.now().isoformat(),
                    1 if alert.acknowledged else 0
                )
            )
            
            self._conn.commit()
            
        except Exception as e:
            self._conn.rollback()
            raise RuntimeError(f"Failed to store alert: {e}")
    
    def get_alerts(
        self,
        chat_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        severity: Optional[str] = None,
        acknowledged: Optional[bool] = None,
        limit: int = 100
    ) -> List[AlertRecord]:
        """
        获取告警记录
        
        Args:
            chat_id: 群组ID
            start_time: 开始时间
            end_time: 结束时间
            severity: 严重程度
            acknowledged: 是否已确认
            limit: 返回数量限制
        
        Returns:
            告警记录列表
        """
        query = "SELECT * FROM alerts WHERE 1=1"
        params = []
        
        if chat_id:
            query += " AND chat_id = ?"
            params.append(chat_id)
        
        if start_time:
            query += " AND timestamp >= ?"
            params.append(start_time.isoformat())
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time.isoformat())
        
        if severity:
            query += " AND severity = ?"
            params.append(severity)
        
        if acknowledged is not None:
            query += " AND acknowledged = ?"
            params.append(1 if acknowledged else 0)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        rows = self._conn.execute(query, params).fetchall()
        
        return [
            AlertRecord(
                alert_id=row['alert_id'],
                chat_id=row['chat_id'],
                alert_type=row['alert_type'],
                severity=row['severity'],
                message=row['message'],
                details=json.loads(row['details']) if row['details'] else None,
                timestamp=datetime.fromisoformat(row['timestamp']) if row['timestamp'] else None,
                acknowledged=bool(row['acknowledged'])
            )
            for row in rows
        ]
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """
        确认告警
        
        Args:
            alert_id: 告警ID
        
        Returns:
            是否成功
        """
        try:
            cursor = self._conn.execute(
                "UPDATE alerts SET acknowledged = 1 WHERE alert_id = ?",
                (alert_id,)
            )
            
            self._conn.commit()
            return cursor.rowcount > 0
            
        except Exception as e:
            self._conn.rollback()
            raise RuntimeError(f"Failed to acknowledge alert: {e}")
    
    def get_database_stats(self) -> Dict[str, Any]:
        """
        获取数据库统计信息
        
        Returns:
            统计信息字典
        """
        try:
            # 消息总数
            total_messages = self._conn.execute("SELECT COUNT(*) as count FROM messages").fetchone()['count']
            
            # 群组数量
            total_chats = self._conn.execute("SELECT COUNT(DISTINCT chat_id) as count FROM messages").fetchone()['count']
            
            # 发送者数量
            total_senders = self._conn.execute("SELECT COUNT(DISTINCT sender_id) as count FROM messages").fetchone()['count']
            
            # 告警数量
            total_alerts = self._conn.execute("SELECT COUNT(*) as count FROM alerts").fetchone()['count']
            
            # 最新消息时间
            latest_message = self._conn.execute("SELECT MAX(timestamp) as latest FROM messages").fetchone()['latest']
            
            # 数据库文件大小
            db_size = 0
            if self.db_path != ":memory:" and os.path.exists(self.db_path):
                db_size = os.path.getsize(self.db_path)
            
            return {
                'total_messages': total_messages,
                'total_chats': total_chats,
                'total_senders': total_senders,
                'total_alerts': total_alerts,
                'latest_message_time': latest_message,
                'db_file_size_mb': db_size / (1024 * 1024)
            }
            
        except Exception as e:
            raise RuntimeError(f"Failed to get database stats: {e}")
    
    def cleanup_old_data(self, days: int = 90):
        """
        清理旧数据
        
        Args:
            days: 保留天数
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            # 删除旧消息
            self._conn.execute(
                "DELETE FROM messages WHERE timestamp < ?",
                (cutoff_date.isoformat(),)
            )
            
            # 删除旧统计
            self._conn.execute(
                "DELETE FROM aggregated_stats WHERE period_start < ?",
                (cutoff_date.isoformat(),)
            )
            
            # 删除旧告警
            self._conn.execute(
                "DELETE FROM alerts WHERE timestamp < ?",
                (cutoff_date.isoformat(),)
            )
            
            self._conn.commit()
            
            # 压缩数据库
            self._conn.execute("VACUUM")
            
        except Exception as e:
            self._conn.rollback()
            raise RuntimeError(f"Failed to cleanup old data: {e}")
    
    def close(self):
        """关闭数据库连接"""
        if self._conn:
            self._conn.close()
            self._conn = None
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Blastogene Message Store')
    parser.add_argument('--db', default=None, help='Database path')
    parser.add_argument('--stats', action='store_true', help='Show database statistics')
    parser.add_argument('--cleanup', type=int, metavar='DAYS', help='Cleanup data older than DAYS')
    
    args = parser.parse_args()
    
    # 创建存储实例
    store = MessageStore(args.db)
    
    if args.stats:
        stats = store.get_database_stats()
        print("\nDatabase Statistics:")
        print(f"  Total Messages: {stats['total_messages']}")
        print(f"  Total Chats: {stats['total_chats']}")
        print(f"  Total Senders: {stats['total_senders']}")
        print(f"  Total Alerts: {stats['total_alerts']}")
        print(f"  Latest Message: {stats['latest_message_time']}")
        print(f"  Database Size: {stats['db_file_size_mb']:.2f} MB")
    
    elif args.cleanup:
        print(f"\nCleaning up data older than {args.cleanup} days...")
        store.cleanup_old_data(args.cleanup)
        print("Cleanup completed!")
    
    else:
        print("Use --stats to show database statistics or --cleanup DAYS to cleanup old data")
    
    store.close()
