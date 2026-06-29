"""
暴躁因子-Blastogene - 社群运营管理工具

飞书群消息监控、数据分析、告警通知、Web看板
"""

__version__ = "1.1.0"
__author__ = "AtomCollide"

from .storage import MessageStore
from .collector import EventCollector
from .aggregator import MetricsAggregator
from .alerter import AlertManager
from .dashboard import DashboardApp

# 竞品融合增强模块
from .notifier import NotifyManager, PluginRegistry, NotifyPlugin
from .sentiment import MessageAnalyzer, SentimentLevel, SentimentResult
from .platform_manager import PlatformManager, UnifiedMessage
from .workflow_engine import WorkflowEngine, WorkflowNode, NodeType
from .classifier import MessageClassifier, Category
from .metrics_engine import MetricsRegistry, Dashboard

__all__ = [
    # 原有模块
    "MessageStore",
    "EventCollector",
    "MetricsAggregator",
    "AlertManager",
    "DashboardApp",
    # P0-1: 情感分析+敏感词检测
    "MessageAnalyzer",
    "SentimentLevel",
    "SentimentResult",
    # P0-2: 多渠道通知
    "NotifyManager",
    "PluginRegistry",
    "NotifyPlugin",
    # P1-1: 多平台统一管理
    "PlatformManager",
    "UnifiedMessage",
    # P1-2: 工作流编排
    "WorkflowEngine",
    "WorkflowNode",
    "NodeType",
    # P2-1: 消息分类
    "MessageClassifier",
    "Category",
    # P2-2: 指标引擎
    "MetricsRegistry",
    "Dashboard",
]
