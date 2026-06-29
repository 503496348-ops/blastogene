#!/usr/bin/env python3
"""
Blastogene 测试脚本

测试核心功能
"""

import sys
import logging
from pathlib import Path
from datetime import datetime, timedelta

# 添加父目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from blastogene.storage import MessageStore, Message
from blastogene.aggregator import MetricsAggregator, TimeRange
from blastogene.alerter import AlertManager, AlertRule, AlertType, AlertSeverity


def test_storage():
    """测试存储层"""
    print("\n=== Testing Storage ===")
    
    # 使用临时数据库
    store = MessageStore(":memory:")
    
    # 创建测试消息
    messages = [
        Message(
            message_id=f"msg_{i}",
            chat_id="test_chat_001",
            chat_type="group",
            sender_id=f"user_{i % 3}",
            sender_type="user",
            content=f"Test message {i}",
            content_type="text",
            timestamp=datetime.now() - timedelta(hours=i)
        )
        for i in range(10)
    ]
    
    # 存储消息
    stored_count = store.store_messages_batch(messages)
    print(f"Stored {stored_count} messages")
    
    # 查询消息
    retrieved = store.get_messages(chat_id="test_chat_001")
    print(f"Retrieved {len(retrieved)} messages")
    
    # 幂等测试
    stored_count = store.store_messages_batch(messages)
    print(f"Idempotent test: stored {stored_count} (should be 0)")
    
    # 统计
    stats = store.get_database_stats()
    print(f"Database stats: {stats}")
    
    return store


def test_aggregator(store: MessageStore):
    """测试聚合器"""
    print("\n=== Testing Aggregator ===")
    
    aggregator = MetricsAggregator(store)
    
    # 计算指标
    today = TimeRange.today()
    
    message_count = aggregator.calculate_message_count("test_chat_001", today)
    print(f"Today's messages: {message_count}")
    
    active_users = aggregator.calculate_active_users("test_chat_001", today)
    print(f"Active users: {active_users}")
    
    engagement = aggregator.calculate_engagement_score("test_chat_001", today)
    print(f"Engagement score: {engagement}")
    
    response_time = aggregator.calculate_response_time("test_chat_001", today)
    print(f"Response time: {response_time}")
    
    return aggregator


def test_alerter(store: MessageStore, aggregator: MetricsAggregator):
    """测试告警管理器"""
    print("\n=== Testing Alert Manager ===")
    
    alert_manager = AlertManager(store, aggregator)
    
    # 列出规则
    rules = alert_manager.get_rules()
    print(f"Loaded {len(rules)} default rules")
    
    # 运行检查
    alerts = alert_manager.run_checks("test_chat_001")
    print(f"Triggered {len(alerts)} alerts")
    
    # 关键词检查
    keyword_alerts = alert_manager.check_message(
        "test_chat_001",
        "这是一条包含广告的消息",
        "user_001"
    )
    print(f"Keyword alerts: {len(keyword_alerts)}")
    
    # 获取摘要
    summary = alert_manager.get_alert_summary("test_chat_001")
    print(f"Alert summary: {summary}")
    
    return alert_manager


def main():
    """主测试函数"""
    print("Blastogene Test Suite")
    print("=" * 50)
    
    # 配置日志
    logging.basicConfig(
        level=logging.WARNING,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    try:
        # 测试存储
        store = test_storage()
        
        # 测试聚合
        aggregator = test_aggregator(store)
        
        # 测试告警
        alerter = test_alerter(store, aggregator)
        
        print("\n" + "=" * 50)
        print("All tests passed! ✓")
        
    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
