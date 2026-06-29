#!/usr/bin/env python3
"""
数据库初始化脚本

初始化Blastogene SQLite数据库
"""

import sys
import logging
from pathlib import Path

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from blastogene.storage import MessageStore


def init_database(db_path: str = None):
    """
    初始化数据库
    
    Args:
        db_path: 数据库路径
    """
    print(f"Initializing Blastogene database...")
    
    try:
        store = MessageStore(db_path)
        
        # 获取统计信息
        stats = store.get_database_stats()
        
        print(f"\nDatabase initialized successfully!")
        print(f"  Path: {store.db_path}")
        print(f"  Size: {stats['db_file_size_mb']:.2f} MB")
        print(f"  Messages: {stats['total_messages']}")
        print(f"  Chats: {stats['total_chats']}")
        print(f"  Senders: {stats['total_senders']}")
        print(f"  Alerts: {stats['total_alerts']}")
        
        return True
        
    except Exception as e:
        print(f"\nError initializing database: {e}")
        return False


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Initialize Blastogene database')
    parser.add_argument('--db', default=None, help='Database path')
    
    args = parser.parse_args()
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    success = init_database(args.db)
    sys.exit(0 if success else 1)
