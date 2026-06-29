"""
告警引擎 - 规则检查与通知路由

检查聚合指标，触发告警，发送通知
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

from .storage import MessageStore, AlertRecord
from .aggregator import MetricsAggregator, TimeRange

logger = logging.getLogger(__name__)


class AlertType(str, Enum):
    """告警类型"""
    MESSAGE_SPIKE = "message_spike"  # 消息突增
    MESSAGE_DROP = "message_drop"  # 消息骤降
    USER_EXODUS = "user_exodus"  # 用户流失
    KEYWORD_TRIGGER = "keyword_trigger"  # 关键词触发
    NO_RESPONSE = "no_response"  # 无人响应
    ENGAGEMENT_DROP = "engagement_drop"  # 参与度下降


class AlertSeverity(str, Enum):
    """告警严重程度"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class AlertRule:
    """告警规则"""
    rule_id: str
    alert_type: AlertType
    severity: AlertSeverity
    enabled: bool = True
    description: str = ""
    
    # 阈值配置
    threshold: float = 0.0
    comparison: str = "gt"  # gt, lt, gte, lte, eq, neq
    
    # 时间窗口
    check_period: str = "daily"  # hourly, daily, weekly
    lookback_periods: int = 1  # 回溯周期数
    
    # 通知配置
    notify_chat: str = ""  # 通知群组ID
    notify_users: List[str] = field(default_factory=list)  # 通知用户ID列表
    
    # 关键词配置（仅用于keyword_trigger类型）
    keywords: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'rule_id': self.rule_id,
            'alert_type': self.alert_type.value,
            'severity': self.severity.value,
            'enabled': self.enabled,
            'description': self.description,
            'threshold': self.threshold,
            'comparison': self.comparison,
            'check_period': self.check_period,
            'lookback_periods': self.lookback_periods,
            'notify_chat': self.notify_chat,
            'notify_users': self.notify_users,
            'keywords': self.keywords
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AlertRule':
        """从字典创建"""
        return cls(
            rule_id=data.get('rule_id', ''),
            alert_type=AlertType(data.get('alert_type', 'message_spike')),
            severity=AlertSeverity(data.get('severity', 'warning')),
            enabled=data.get('enabled', True),
            description=data.get('description', ''),
            threshold=data.get('threshold', 0.0),
            comparison=data.get('comparison', 'gt'),
            check_period=data.get('check_period', 'daily'),
            lookback_periods=data.get('lookback_periods', 1),
            notify_chat=data.get('notify_chat', ''),
            notify_users=data.get('notify_users', []),
            keywords=data.get('keywords', [])
        )


class AlertManager:
    """告警管理器"""
    
    def __init__(
        self,
        store: MessageStore,
        aggregator: MetricsAggregator,
        rules: Optional[List[AlertRule]] = None,
        on_alert: Optional[Callable[[AlertRecord], None]] = None
    ):
        """
        初始化告警管理器
        
        Args:
            store: 消息存储实例
            aggregator: 聚合器实例
            rules: 告警规则列表
            on_alert: 告警回调函数
        """
        self.store = store
        self.aggregator = aggregator
        self.rules = rules or []
        self.on_alert = on_alert
        
        # 如果没有提供规则，加载默认规则
        if not self.rules:
            self.rules = self._load_default_rules()
    
    def _load_default_rules(self) -> List[AlertRule]:
        """加载默认告警规则"""
        return [
            AlertRule(
                rule_id="default_spike",
                alert_type=AlertType.MESSAGE_SPIKE,
                severity=AlertSeverity.WARNING,
                description="消息量突增",
                threshold=1.5,  # 增长50%
                comparison="gt",
                check_period="daily"
            ),
            AlertRule(
                rule_id="default_drop",
                alert_type=AlertType.MESSAGE_DROP,
                severity=AlertSeverity.WARNING,
                description="消息量骤降",
                threshold=0.5,  # 下降50%
                comparison="lt",
                check_period="daily"
            ),
            AlertRule(
                rule_id="default_keyword",
                alert_type=AlertType.KEYWORD_TRIGGER,
                severity=AlertSeverity.CRITICAL,
                description="关键词触发",
                keywords=["广告", "刷单", "兼职", "赚钱", "加微信"],
                check_period="daily"
            ),
            AlertRule(
                rule_id="default_no_response",
                alert_type=AlertType.NO_RESPONSE,
                severity=AlertSeverity.WARNING,
                description="问题无人响应",
                threshold=3600,  # 3600秒 = 1小时
                comparison="gt",
                check_period="hourly"
            )
        ]
    
    def add_rule(self, rule: AlertRule):
        """添加规则"""
        # 检查是否已存在
        for existing_rule in self.rules:
            if existing_rule.rule_id == rule.rule_id:
                # 更新现有规则
                self.rules.remove(existing_rule)
                break
        
        self.rules.append(rule)
        logger.info(f"Added alert rule: {rule.rule_id}")
    
    def remove_rule(self, rule_id: str) -> bool:
        """移除规则"""
        for rule in self.rules:
            if rule.rule_id == rule_id:
                self.rules.remove(rule)
                logger.info(f"Removed alert rule: {rule_id}")
                return True
        return False
    
    def get_rules(self) -> List[AlertRule]:
        """获取所有规则"""
        return self.rules.copy()
    
    def check_message_spike(
        self,
        chat_id: str,
        rule: AlertRule
    ) -> Optional[AlertRecord]:
        """
        检查消息突增
        
        Args:
            chat_id: 群组ID
            rule: 告警规则
        
        Returns:
            告警记录（如果触发）
        """
        now = datetime.now()
        
        # 当前周期
        if rule.check_period == 'hourly':
            current_range = TimeRange.last_hour()
            previous_range = TimeRange(
                start=now - timedelta(hours=2),
                end=now - timedelta(hours=1)
            )
        elif rule.check_period == 'daily':
            current_range = TimeRange.today()
            previous_range = TimeRange.yesterday()
        else:  # weekly
            current_range = TimeRange.last_week()
            previous_range = TimeRange(
                start=now - timedelta(weeks=2),
                end=now - timedelta(weeks=1)
            )
        
        # 获取对比数据
        comparison = self.aggregator.get_historical_comparison(
            chat_id=chat_id,
            metric_type='message_count',
            period=rule.check_period,
            current_range=current_range,
            previous_range=previous_range
        )
        
        current_value = comparison['current']
        change_rate = comparison['change_rate']
        
        # 检查是否触发
        if rule.comparison == 'gt' and change_rate > rule.threshold:
            return self._create_alert(
                chat_id=chat_id,
                alert_type=rule.alert_type,
                severity=rule.severity,
                message=f"消息量突增 {comparison['change_percentage']}（当前: {current_value}, 上期: {comparison['previous']}）",
                details={
                    'current': current_value,
                    'previous': comparison['previous'],
                    'change_rate': change_rate,
                    'threshold': rule.threshold
                }
            )
        
        return None
    
    def check_message_drop(
        self,
        chat_id: str,
        rule: AlertRule
    ) -> Optional[AlertRecord]:
        """
        检查消息骤降
        
        Args:
            chat_id: 群组ID
            rule: 告警规则
        
        Returns:
            告警记录（如果触发）
        """
        now = datetime.now()
        
        # 当前周期
        if rule.check_period == 'hourly':
            current_range = TimeRange.last_hour()
            previous_range = TimeRange(
                start=now - timedelta(hours=2),
                end=now - timedelta(hours=1)
            )
        elif rule.check_period == 'daily':
            current_range = TimeRange.today()
            previous_range = TimeRange.yesterday()
        else:  # weekly
            current_range = TimeRange.last_week()
            previous_range = TimeRange(
                start=now - timedelta(weeks=2),
                end=now - timedelta(weeks=1)
            )
        
        # 获取对比数据
        comparison = self.aggregator.get_historical_comparison(
            chat_id=chat_id,
            metric_type='message_count',
            period=rule.check_period,
            current_range=current_range,
            previous_range=previous_range
        )
        
        current_value = comparison['current']
        change_rate = comparison['change_rate']
        
        # 检查是否触发
        if rule.comparison == 'lt' and change_rate < rule.threshold:
            return self._create_alert(
                chat_id=chat_id,
                alert_type=rule.alert_type,
                severity=rule.severity,
                message=f"消息量骤降 {comparison['change_percentage']}（当前: {current_value}, 上期: {comparison['previous']}）",
                details={
                    'current': current_value,
                    'previous': comparison['previous'],
                    'change_rate': change_rate,
                    'threshold': rule.threshold
                }
            )
        
        return None
    
    def check_keyword_trigger(
        self,
        chat_id: str,
        rule: AlertRule,
        message_content: str,
        sender_id: str
    ) -> Optional[AlertRecord]:
        """
        检查关键词触发
        
        Args:
            chat_id: 群组ID
            rule: 告警规则
            message_content: 消息内容
            sender_id: 发送者ID
        
        Returns:
            告警记录（如果触发）
        """
        if not rule.keywords:
            return None
        
        # 检查是否包含关键词
        triggered_keywords = []
        for keyword in rule.keywords:
            if keyword.lower() in message_content.lower():
                triggered_keywords.append(keyword)
        
        if triggered_keywords:
            return self._create_alert(
                chat_id=chat_id,
                alert_type=rule.alert_type,
                severity=rule.severity,
                message=f"关键词触发: {', '.join(triggered_keywords)}",
                details={
                    'keywords': triggered_keywords,
                    'sender_id': sender_id,
                    'message_preview': message_content[:100]
                }
            )
        
        return None
    
    def check_no_response(
        self,
        chat_id: str,
        rule: AlertRule
    ) -> Optional[AlertRecord]:
        """
        检查无人响应
        
        Args:
            chat_id: 群组ID
            rule: 告警规则
        
        Returns:
            告警记录（如果触发）
        """
        # 获取最近的消息
        recent_messages = self.store.get_messages(
            chat_id=chat_id,
            start_time=datetime.now() - timedelta(hours=1),
            limit=10
        )
        
        if not recent_messages:
            return None
        
        # 检查最后一条消息是否是问题（简化判断：以问号结尾）
        last_message = recent_messages[0]
        if not last_message.content.endswith('?') and not last_message.content.endswith('？'):
            return None
        
        # 检查是否有回复
        has_response = False
        for msg in recent_messages[1:]:
            if msg.sender_id != last_message.sender_id:
                has_response = True
                break
        
        if not has_response:
            # 计算等待时间
            wait_time = (datetime.now() - last_message.timestamp).total_seconds()
            
            if wait_time > rule.threshold:
                return self._create_alert(
                    chat_id=chat_id,
                    alert_type=rule.alert_type,
                    severity=rule.severity,
                    message=f"问题等待回复超过 {int(wait_time / 60)} 分钟",
                    details={
                        'question': last_message.content[:100],
                        'sender_id': last_message.sender_id,
                        'wait_time_seconds': wait_time
                    }
                )
        
        return None
    
    def check_engagement_drop(
        self,
        chat_id: str,
        rule: AlertRule
    ) -> Optional[AlertRecord]:
        """
        检查参与度下降
        
        Args:
            chat_id: 群组ID
            rule: 告警规则
        
        Returns:
            告警记录（如果触发）
        """
        now = datetime.now()
        
        # 当前周期
        current_range = TimeRange.today()
        previous_range = TimeRange.yesterday()
        
        # 获取参与度分数
        current_score = self.aggregator.calculate_engagement_score(chat_id, current_range)
        previous_score = self.aggregator.calculate_engagement_score(chat_id, previous_range)
        
        # 计算变化
        if previous_score > 0:
            change_rate = (current_score - previous_score) / previous_score
        else:
            change_rate = 0
        
        # 检查是否触发
        if rule.comparison == 'lt' and change_rate < rule.threshold:
            return self._create_alert(
                chat_id=chat_id,
                alert_type=rule.alert_type,
                severity=rule.severity,
                message=f"参与度下降 {change_rate * 100:+.1f}%（当前: {current_score}, 上期: {previous_score}）",
                details={
                    'current_score': current_score,
                    'previous_score': previous_score,
                    'change_rate': change_rate,
                    'threshold': rule.threshold
                }
            )
        
        return None
    
    def _create_alert(
        self,
        chat_id: str,
        alert_type: AlertType,
        severity: AlertSeverity,
        message: str,
        details: Optional[Dict] = None
    ) -> AlertRecord:
        """创建告警记录"""
        alert_id = f"{chat_id}_{alert_type.value}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        alert = AlertRecord(
            alert_id=alert_id,
            chat_id=chat_id,
            alert_type=alert_type.value,
            severity=severity.value,
            message=message,
            details=details,
            timestamp=datetime.now()
        )
        
        # 存储告警
        self.store.store_alert(alert)
        
        # 调用回调
        if self.on_alert:
            self.on_alert(alert)
        
        logger.warning(f"Alert triggered: {alert_type.value} for {chat_id}: {message}")
        
        return alert
    
    def run_checks(self, chat_id: str) -> List[AlertRecord]:
        """
        运行所有检查
        
        Args:
            chat_id: 群组ID
        
        Returns:
            触发的告警列表
        """
        alerts = []
        
        for rule in self.rules:
            if not rule.enabled:
                continue
            
            try:
                alert = None
                
                if rule.alert_type == AlertType.MESSAGE_SPIKE:
                    alert = self.check_message_spike(chat_id, rule)
                elif rule.alert_type == AlertType.MESSAGE_DROP:
                    alert = self.check_message_drop(chat_id, rule)
                elif rule.alert_type == AlertType.NO_RESPONSE:
                    alert = self.check_no_response(chat_id, rule)
                elif rule.alert_type == AlertType.ENGAGEMENT_DROP:
                    alert = self.check_engagement_drop(chat_id, rule)
                # keyword_trigger需要实时消息，不在这里检查
                
                if alert:
                    alerts.append(alert)
                    
            except Exception as e:
                logger.error(f"Error checking rule {rule.rule_id} for {chat_id}: {e}")
        
        return alerts
    
    def check_message(self, chat_id: str, message_content: str, sender_id: str) -> List[AlertRecord]:
        """
        检查单条消息（用于实时关键词检测）
        
        Args:
            chat_id: 群组ID
            message_content: 消息内容
            sender_id: 发送者ID
        
        Returns:
            触发的告警列表
        """
        alerts = []
        
        for rule in self.rules:
            if not rule.enabled:
                continue
            
            if rule.alert_type == AlertType.KEYWORD_TRIGGER:
                try:
                    alert = self.check_keyword_trigger(chat_id, rule, message_content, sender_id)
                    if alert:
                        alerts.append(alert)
                except Exception as e:
                    logger.error(f"Error checking keyword rule {rule.rule_id}: {e}")
        
        return alerts
    
    def get_recent_alerts(
        self,
        chat_id: Optional[str] = None,
        limit: int = 50
    ) -> List[AlertRecord]:
        """获取最近的告警"""
        return self.store.get_alerts(
            chat_id=chat_id,
            limit=limit
        )
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """确认告警"""
        return self.store.acknowledge_alert(alert_id)
    
    def get_alert_summary(
        self,
        chat_id: str,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        获取告警摘要
        
        Args:
            chat_id: 群组ID
            days: 天数
        
        Returns:
            告警摘要
        """
        start_time = datetime.now() - timedelta(days=days)
        
        alerts = self.store.get_alerts(
            chat_id=chat_id,
            start_time=start_time,
            limit=1000
        )
        
        # 按类型统计
        by_type = {}
        for alert in alerts:
            alert_type = alert.alert_type
            if alert_type not in by_type:
                by_type[alert_type] = 0
            by_type[alert_type] += 1
        
        # 按严重程度统计
        by_severity = {}
        for alert in alerts:
            severity = alert.severity
            if severity not in by_severity:
                by_severity[severity] = 0
            by_severity[severity] += 1
        
        # 未确认的告警
        unacknowledged = [a for a in alerts if not a.acknowledged]
        
        return {
            'total_alerts': len(alerts),
            'by_type': by_type,
            'by_severity': by_severity,
            'unacknowledged_count': len(unacknowledged),
            'unacknowledged_alerts': [
                {
                    'alert_id': a.alert_id,
                    'alert_type': a.alert_type,
                    'severity': a.severity,
                    'message': a.message,
                    'timestamp': a.timestamp.isoformat() if a.timestamp else None
                }
                for a in unacknowledged[:10]  # 最多返回10个
            ]
        }


def create_alert_manager(
    store: MessageStore,
    aggregator: MetricsAggregator,
    rules_config: Optional[List[Dict]] = None,
    on_alert: Optional[Callable[[AlertRecord], None]] = None
) -> AlertManager:
    """
    创建告警管理器实例
    
    Args:
        store: 消息存储实例
        aggregator: 聚合器实例
        rules_config: 规则配置列表
        on_alert: 告警回调函数
    
    Returns:
        AlertManager实例
    """
    rules = []
    
    if rules_config:
        for rule_config in rules_config:
            try:
                rule = AlertRule.from_dict(rule_config)
                rules.append(rule)
            except Exception as e:
                logger.error(f"Error loading rule config: {e}")
    
    return AlertManager(store, aggregator, rules, on_alert)


if __name__ == '__main__':
    import argparse
    from .storage import MessageStore
    from .aggregator import MetricsAggregator
    
    parser = argparse.ArgumentParser(description='Blastogene Alert Manager')
    parser.add_argument('--db', default=None, help='Database path')
    parser.add_argument('--chat-id', required=True, help='Chat ID to check')
    parser.add_argument('--list-rules', action='store_true', help='List alert rules')
    parser.add_argument('--check', action='store_true', help='Run alert checks')
    parser.add_argument('--summary', action='store_true', help='Show alert summary')
    
    args = parser.parse_args()
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 创建实例
    store = MessageStore(args.db)
    aggregator = MetricsAggregator(store)
    alert_manager = create_alert_manager(store, aggregator)
    
    if args.list_rules:
        print("\nAlert Rules:")
        for rule in alert_manager.get_rules():
            print(f"  {rule.rule_id}: {rule.alert_type.value} ({rule.severity.value})")
            print(f"    Enabled: {rule.enabled}")
            print(f"    Description: {rule.description}")
            print()
    
    elif args.check:
        print(f"\nRunning alert checks for {args.chat_id}...")
        alerts = alert_manager.run_checks(args.chat_id)
        
        if alerts:
            print(f"\nTriggered {len(alerts)} alerts:")
            for alert in alerts:
                print(f"  [{alert.severity}] {alert.alert_type}: {alert.message}")
        else:
            print("\nNo alerts triggered.")
    
    elif args.summary:
        summary = alert_manager.get_alert_summary(args.chat_id)
        
        print(f"\nAlert Summary for {args.chat_id} (last 7 days):")
        print(f"  Total Alerts: {summary['total_alerts']}")
        print(f"  Unacknowledged: {summary['unacknowledged_count']}")
        
        if summary['by_type']:
            print("\n  By Type:")
            for alert_type, count in summary['by_type'].items():
                print(f"    {alert_type}: {count}")
        
        if summary['by_severity']:
            print("\n  By Severity:")
            for severity, count in summary['by_severity'].items():
                print(f"    {severity}: {count}")
