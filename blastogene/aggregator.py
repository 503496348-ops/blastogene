"""
聚合引擎 - 指标计算与统计

从SQLite读取原始消息，计算聚合指标，写回统计表
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from collections import defaultdict

from .storage import MessageStore

logger = logging.getLogger(__name__)


@dataclass
class TimeRange:
    """时间范围"""
    start: datetime
    end: datetime
    
    @classmethod
    def last_hour(cls) -> 'TimeRange':
        """最近一小时"""
        now = datetime.now()
        return cls(start=now - timedelta(hours=1), end=now)
    
    @classmethod
    def last_day(cls) -> 'TimeRange':
        """最近一天"""
        now = datetime.now()
        return cls(start=now - timedelta(days=1), end=now)
    
    @classmethod
    def last_week(cls) -> 'TimeRange':
        """最近一周"""
        now = datetime.now()
        return cls(start=now - timedelta(weeks=1), end=now)
    
    @classmethod
    def today(cls) -> 'TimeRange':
        """今天"""
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return cls(start=today_start, end=now)
    
    @classmethod
    def yesterday(cls) -> 'TimeRange':
        """昨天"""
        now = datetime.now()
        yesterday_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_end = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return cls(start=yesterday_start, end=yesterday_end)


class MetricsAggregator:
    """指标聚合器"""
    
    def __init__(self, store: MessageStore):
        """
        初始化聚合器
        
        Args:
            store: 消息存储实例
        """
        self.store = store
    
    def calculate_message_count(
        self,
        chat_id: str,
        time_range: TimeRange
    ) -> int:
        """
        计算消息数量
        
        Args:
            chat_id: 群组ID
            time_range: 时间范围
        
        Returns:
            消息数量
        """
        return self.store.get_message_count(
            chat_id=chat_id,
            start_time=time_range.start,
            end_time=time_range.end
        )
    
    def calculate_active_users(
        self,
        chat_id: str,
        time_range: TimeRange
    ) -> int:
        """
        计算活跃用户数
        
        Args:
            chat_id: 群组ID
            time_range: 时间范围
        
        Returns:
            活跃用户数
        """
        senders = self.store.get_unique_senders(
            chat_id=chat_id,
            start_time=time_range.start,
            end_time=time_range.end
        )
        return len(senders)
    
    def calculate_messages_per_user(
        self,
        chat_id: str,
        time_range: TimeRange
    ) -> Dict[str, int]:
        """
        计算每用户消息数
        
        Args:
            chat_id: 群组ID
            time_range: 时间范围
        
        Returns:
            {sender_id: message_count}
        """
        messages = self.store.get_messages(
            chat_id=chat_id,
            start_time=time_range.start,
            end_time=time_range.end,
            limit=10000  # 限制内存使用
        )
        
        count_by_user = defaultdict(int)
        for msg in messages:
            count_by_user[msg.sender_id] += 1
        
        return dict(count_by_user)
    
    def calculate_peak_hours(
        self,
        chat_id: str,
        time_range: TimeRange
    ) -> Dict[int, int]:
        """
        计算每小时消息分布
        
        Args:
            chat_id: 群组ID
            time_range: 时间范围
        
        Returns:
            {hour: message_count}
        """
        messages = self.store.get_messages(
            chat_id=chat_id,
            start_time=time_range.start,
            end_time=time_range.end,
            limit=10000
        )
        
        count_by_hour = defaultdict(int)
        for msg in messages:
            hour = msg.timestamp.hour
            count_by_hour[hour] += 1
        
        return dict(count_by_hour)
    
    def calculate_response_time(
        self,
        chat_id: str,
        time_range: TimeRange
    ) -> Dict[str, float]:
        """
        计算响应时间（简化版）
        
        假设：问题后有人回复即为响应
        返回平均响应时间（秒）
        
        Args:
            chat_id: 群组ID
            time_range: 时间范围
        
        Returns:
            {'avg_seconds': float, 'median_seconds': float, 'count': int}
        """
        messages = self.store.get_messages(
            chat_id=chat_id,
            start_time=time_range.start,
            end_time=time_range.end,
            limit=10000
        )
        
        if len(messages) < 2:
            return {'avg_seconds': 0, 'median_seconds': 0, 'count': 0}
        
        # 按时间排序
        messages.sort(key=lambda m: m.timestamp)
        
        # 计算连续消息之间的时间差
        response_times = []
        for i in range(1, len(messages)):
            # 只计算不同用户之间的回复
            if messages[i].sender_id != messages[i-1].sender_id:
                time_diff = (messages[i].timestamp - messages[i-1].timestamp).total_seconds()
                # 排除过长的间隔（超过1小时）
                if 0 < time_diff < 3600:
                    response_times.append(time_diff)
        
        if not response_times:
            return {'avg_seconds': 0, 'median_seconds': 0, 'count': 0}
        
        avg_seconds = sum(response_times) / len(response_times)
        sorted_times = sorted(response_times)
        median_seconds = sorted_times[len(sorted_times) // 2]
        
        return {
            'avg_seconds': round(avg_seconds, 2),
            'median_seconds': round(median_seconds, 2),
            'count': len(response_times)
        }
    
    def calculate_engagement_score(
        self,
        chat_id: str,
        time_range: TimeRange
    ) -> float:
        """
        计算参与度分数（0-100）
        
        基于：
        - 消息数量（权重0.4）
        - 活跃用户数（权重0.3）
        - 响应时间（权重0.3）
        
        Args:
            chat_id: 群组ID
            time_range: 时间范围
        
        Returns:
            参与度分数
        """
        # 消息数量得分（假设100条/天为满分）
        message_count = self.calculate_message_count(chat_id, time_range)
        days = max((time_range.end - time_range.start).days, 1)
        messages_per_day = message_count / days
        message_score = min(messages_per_day / 100, 1.0) * 100
        
        # 活跃用户得分（假设20个活跃用户为满分）
        active_users = self.calculate_active_users(chat_id, time_range)
        user_score = min(active_users / 20, 1.0) * 100
        
        # 响应时间得分（越快越好，60秒内为满分）
        response_stats = self.calculate_response_time(chat_id, time_range)
        if response_stats['count'] > 0:
            response_score = max(0, 100 - (response_stats['avg_seconds'] / 60))
        else:
            response_score = 50  # 无响应数据给中等分
        
        # 加权平均
        engagement_score = (
            message_score * 0.4 +
            user_score * 0.3 +
            response_score * 0.3
        )
        
        return round(engagement_score, 2)
    
    def aggregate_period(
        self,
        chat_id: str,
        period: str,
        time_range: TimeRange
    ) -> Dict[str, Any]:
        """
        聚合指定周期的指标
        
        Args:
            chat_id: 群组ID
            period: 周期类型 (hourly, daily, weekly)
            time_range: 时间范围
        
        Returns:
            聚合指标字典
        """
        metrics = {}
        
        # 消息数量
        message_count = self.calculate_message_count(chat_id, time_range)
        metrics['message_count'] = message_count
        
        # 活跃用户数
        active_users = self.calculate_active_users(chat_id, time_range)
        metrics['active_users'] = active_users
        
        # 每用户消息数
        messages_per_user = self.calculate_messages_per_user(chat_id, time_range)
        metrics['messages_per_user'] = messages_per_user
        
        # 每小时分布
        peak_hours = self.calculate_peak_hours(chat_id, time_range)
        metrics['peak_hours'] = peak_hours
        
        # 响应时间
        response_stats = self.calculate_response_time(chat_id, time_range)
        metrics['response_time'] = response_stats
        
        # 参与度分数
        engagement_score = self.calculate_engagement_score(chat_id, time_range)
        metrics['engagement_score'] = engagement_score
        
        return metrics
    
    def store_aggregation(
        self,
        chat_id: str,
        period: str,
        time_range: TimeRange,
        metrics: Dict[str, Any]
    ):
        """
        存储聚合结果
        
        Args:
            chat_id: 群组ID
            period: 周期类型
            time_range: 时间范围
            metrics: 聚合指标
        """
        # 存储各个指标
        for metric_type, metric_value in metrics.items():
            if isinstance(metric_value, (int, float)):
                self.store.store_aggregated_stat(
                    chat_id=chat_id,
                    metric_type=metric_type,
                    metric_value=float(metric_value),
                    period=period,
                    period_start=time_range.start,
                    period_end=time_range.end
                )
    
    def run_aggregation(
        self,
        chat_ids: List[str],
        period: str = 'daily'
    ) -> Dict[str, Dict[str, Any]]:
        """
        运行聚合任务
        
        Args:
            chat_ids: 群组ID列表
            period: 周期类型
        
        Returns:
            {chat_id: metrics}
        """
        # 根据周期确定时间范围
        if period == 'hourly':
            time_range = TimeRange.last_hour()
        elif period == 'daily':
            time_range = TimeRange.last_day()
        elif period == 'weekly':
            time_range = TimeRange.last_week()
        else:
            raise ValueError(f"Invalid period: {period}")
        
        results = {}
        
        for chat_id in chat_ids:
            try:
                logger.info(f"Aggregating {period} metrics for {chat_id}")
                
                # 计算指标
                metrics = self.aggregate_period(chat_id, period, time_range)
                
                # 存储结果
                self.store_aggregation(chat_id, period, time_range, metrics)
                
                results[chat_id] = metrics
                
                logger.info(f"Completed aggregation for {chat_id}: {metrics['message_count']} messages, {metrics['active_users']} active users")
                
            except Exception as e:
                logger.error(f"Error aggregating {chat_id}: {e}")
                results[chat_id] = {'error': str(e)}
        
        return results
    
    def get_historical_comparison(
        self,
        chat_id: str,
        metric_type: str,
        period: str,
        current_range: TimeRange,
        previous_range: TimeRange
    ) -> Dict[str, Any]:
        """
        获取历史对比数据
        
        Args:
            chat_id: 群组ID
            metric_type: 指标类型
            period: 周期类型
            current_range: 当前时间范围
            previous_range: 上一时间范围
        
        Returns:
            对比结果
        """
        # 获取当前周期数据
        current_stats = self.store.get_aggregated_stats(
            chat_id=chat_id,
            metric_type=metric_type,
            period=period,
            start_time=current_range.start,
            end_time=current_range.end,
            limit=1
        )
        
        # 获取上一周期数据
        previous_stats = self.store.get_aggregated_stats(
            chat_id=chat_id,
            metric_type=metric_type,
            period=period,
            start_time=previous_range.start,
            end_time=previous_range.end,
            limit=1
        )
        
        current_value = current_stats[0]['metric_value'] if current_stats else 0
        previous_value = previous_stats[0]['metric_value'] if previous_stats else 0
        
        # 计算变化率
        if previous_value > 0:
            change_rate = (current_value - previous_value) / previous_value
        else:
            change_rate = 0 if current_value == 0 else 1.0
        
        return {
            'current': current_value,
            'previous': previous_value,
            'change': current_value - previous_value,
            'change_rate': round(change_rate, 4),
            'change_percentage': f"{change_rate * 100:+.1f}%"
        }
    
    def detect_anomalies(
        self,
        chat_id: str,
        metric_type: str,
        period: str,
        threshold_multiplier: float = 2.0
    ) -> List[Dict[str, Any]]:
        """
        检测异常值
        
        Args:
            chat_id: 群组ID
            metric_type: 指标类型
            period: 周期类型
            threshold_multiplier: 阈值倍数（超过均值的倍数视为异常）
        
        Returns:
            异常值列表
        """
        # 获取历史数据
        stats = self.store.get_aggregated_stats(
            chat_id=chat_id,
            metric_type=metric_type,
            period=period,
            limit=30  # 最近30个周期
        )
        
        if len(stats) < 3:
            return []
        
        # 计算均值和标准差
        values = [s['metric_value'] for s in stats]
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        std_dev = variance ** 0.5
        
        # 检测异常值
        anomalies = []
        threshold = mean + (std_dev * threshold_multiplier)
        
        for stat in stats:
            if stat['metric_value'] > threshold:
                anomalies.append({
                    'period_start': stat['period_start'],
                    'period_end': stat['period_end'],
                    'value': stat['metric_value'],
                    'mean': round(mean, 2),
                    'std_dev': round(std_dev, 2),
                    'threshold': round(threshold, 2),
                    'deviation': round((stat['metric_value'] - mean) / std_dev, 2)
                })
        
        return anomalies


if __name__ == '__main__':
    import argparse
    from .storage import MessageStore
    
    parser = argparse.ArgumentParser(description='Blastogene Metrics Aggregator')
    parser.add_argument('--db', default=None, help='Database path')
    parser.add_argument('--chat-id', required=True, help='Chat ID to aggregate')
    parser.add_argument('--period', default='daily', choices=['hourly', 'daily', 'weekly'], help='Aggregation period')
    
    args = parser.parse_args()
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 创建聚合并运行
    store = MessageStore(args.db)
    aggregator = MetricsAggregator(store)
    
    results = aggregator.run_aggregation([args.chat_id], args.period)
    
    print(f"\nAggregation Results for {args.chat_id}:")
    for chat_id, metrics in results.items():
        print(f"\n  Messages: {metrics.get('message_count', 0)}")
        print(f"  Active Users: {metrics.get('active_users', 0)}")
        print(f"  Engagement Score: {metrics.get('engagement_score', 0)}")
        
        response_time = metrics.get('response_time', {})
        if response_time.get('count', 0) > 0:
            print(f"  Avg Response Time: {response_time['avg_seconds']}s")
            print(f"  Median Response Time: {response_time['median_seconds']}s")
