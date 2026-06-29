"""指标引擎模块 - 声明式指标定义与多维聚合

核心能力：
- 声明式指标定义（指标注册表）
- 多维数据聚合（时间/分组/平台）
- 自动生成统计报告
- 看板数据快照
- HTML看板渲染
"""

import logging
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple


logger = logging.getLogger(__name__)


@dataclass
class Metric:
    """指标定义"""
    name: str
    display_name: str
    description: str
    unit: str = ""
    aggregation: str = "sum"        # sum/avg/count/max/min
    format_fn: Optional[Callable] = None

    def format_value(self, value: Any) -> str:
        if self.format_fn:
            return self.format_fn(value)
        if isinstance(value, float):
            return f"{value:.2f}{self.unit}"
        return f"{value}{self.unit}"


@dataclass
class DataPoint:
    """数据点"""
    timestamp: datetime
    metric_name: str
    value: float
    dimensions: Dict[str, str] = field(default_factory=dict)


@dataclass
class DashboardSnapshot:
    """看板快照"""
    snapshot_id: str
    created_at: datetime
    metrics: Dict[str, Any]
    period: str
    highlights: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "snapshot_id": self.snapshot_id,
            "created_at": self.created_at.isoformat(),
            "period": self.period,
            "metrics": self.metrics,
            "highlights": self.highlights,
        }


class MetricsRegistry:
    """指标注册表 - 声明式指标管理"""

    def __init__(self):
        self._metrics: Dict[str, Metric] = {}
        self._data_points: List[DataPoint] = []
        self.logger = logging.getLogger(__name__)

    def register(self, metric: Metric):
        """注册指标"""
        self._metrics[metric.name] = metric
        self.logger.info("Registered metric: %s (%s)", metric.name, metric.display_name)

    def get(self, name: str) -> Optional[Metric]:
        return self._metrics.get(name)

    def list_metrics(self) -> List[Dict]:
        return [
            {"name": m.name, "display_name": m.display_name,
             "description": m.description, "unit": m.unit, "aggregation": m.aggregation}
            for m in self._metrics.values()
        ]

    def record(self, metric_name: str, value: float,
              dimensions: Optional[Dict[str, str]] = None,
              timestamp: Optional[datetime] = None):
        """记录数据点"""
        self._data_points.append(DataPoint(
            timestamp=timestamp or datetime.now(),
            metric_name=metric_name,
            value=value,
            dimensions=dimensions or {},
        ))

    def query(self, metric_name: str,
             start: Optional[datetime] = None,
             end: Optional[datetime] = None,
             group_by: Optional[str] = None) -> Dict[str, Any]:
        """查询指标数据"""
        points = [p for p in self._data_points if p.metric_name == metric_name]

        if start:
            points = [p for p in points if p.timestamp >= start]
        if end:
            points = [p for p in points if p.timestamp <= end]

        if not points:
            return {"metric": metric_name, "values": [], "total": 0}

        metric = self._metrics.get(metric_name)

        if group_by:
            # 按维度分组
            groups: Dict[str, List[float]] = defaultdict(list)
            for p in points:
                key = p.dimensions.get(group_by, "unknown")
                groups[key].append(p.value)

            result = {}
            for key, values in groups.items():
                agg_value = self._aggregate(values, metric.aggregation if metric else "sum")
                result[key] = {
                    "value": agg_value,
                    "formatted": metric.format_value(agg_value) if metric else str(agg_value),
                    "count": len(values),
                }
            return {"metric": metric_name, "group_by": group_by, "groups": result}
        else:
            values = [p.value for p in points]
            agg_value = self._aggregate(values, metric.aggregation if metric else "sum")
            return {
                "metric": metric_name,
                "value": agg_value,
                "formatted": metric.format_value(agg_value) if metric else str(agg_value),
                "count": len(values),
            }

    def _aggregate(self, values: List[float], method: str) -> float:
        if not values:
            return 0.0
        if method == "sum":
            return sum(values)
        elif method == "avg":
            return sum(values) / len(values)
        elif method == "count":
            return float(len(values))
        elif method == "max":
            return max(values)
        elif method == "min":
            return min(values)
        return sum(values)


class Dashboard:
    """看板引擎 - 数据可视化"""

    def __init__(self, registry: MetricsRegistry):
        self.registry = registry
        self._snapshots: List[DashboardSnapshot] = []
        self._widgets: List[Dict] = []
        self.logger = logging.getLogger(__name__)

    def add_widget(self, widget_type: str, title: str, metric_name: str,
                  config: Optional[Dict] = None):
        """添加看板组件"""
        self._widgets.append({
            "type": widget_type,
            "title": title,
            "metric": metric_name,
            "config": config or {},
        })

    def snapshot(self, period: str = "all") -> DashboardSnapshot:
        """生成看板快照"""
        import uuid
        metrics_data = {}
        highlights = []

        for widget in self._widgets:
            metric_name = widget["metric"]
            result = self.registry.query(metric_name)
            if result.get("value") is not None:
                metrics_data[metric_name] = result["value"]
                metric = self.registry.get(metric_name)
                if metric:
                    formatted = metric.format_value(result["value"])
                    highlights.append(f"{metric.display_name}: {formatted}")

        snapshot = DashboardSnapshot(
            snapshot_id=str(uuid.uuid4())[:8],
            created_at=datetime.now(),
            metrics=metrics_data,
            period=period,
            highlights=highlights,
        )
        self._snapshots.append(snapshot)
        return snapshot

    def render_html(self, title: str = "社群运营看板") -> str:
        """渲染HTML看板"""
        snapshot = self.snapshot()

        metrics_html = ""
        for widget in self._widgets:
            metric_name = widget["metric"]
            metric = self.registry.get(metric_name)
            result = self.registry.query(metric_name)

            value_str = "N/A"
            if metric and result.get("value") is not None:
                value_str = metric.format_value(result["value"])

            metrics_html += f"""
            <div class="metric-card">
                <div class="metric-title">{widget['title']}</div>
                <div class="metric-value">{value_str}</div>
                <div class="metric-count">{result.get('count', 0)} 条数据</div>
            </div>"""

        return f"""<!DOCTYPE html>
<html lang="zh">
<head>
    <meta charset="UTF-8">
    <title>{title}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, sans-serif; background: #f5f5f5; padding: 20px; }}
        h1 {{ text-align: center; color: #333; margin-bottom: 20px; }}
        .dashboard {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap: 16px; }}
        .metric-card {{
            background: white; border-radius: 12px; padding: 24px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08); text-align: center;
        }}
        .metric-title {{ font-size: 14px; color: #666; margin-bottom: 8px; }}
        .metric-value {{ font-size: 32px; font-weight: 700; color: #1a73e8; }}
        .metric-count {{ font-size: 12px; color: #999; margin-top: 4px; }}
        .footer {{ text-align: center; color: #999; font-size: 12px; margin-top: 20px; }}
    </style>
</head>
<body>
    <h1>📊 {title}</h1>
    <div class="dashboard">{metrics_html}
    </div>
    <div class="footer">快照时间: {snapshot.created_at.strftime('%Y-%m-%d %H:%M:%S')}</div>
</body>
</html>"""

    def get_snapshots(self, limit: int = 10) -> List[Dict]:
        """获取历史快照"""
        return [s.to_dict() for s in self._snapshots[-limit:]]

    def get_stats(self) -> Dict[str, Any]:
        """获取看板统计"""
        return {
            "widgets": len(self._widgets),
            "snapshots": len(self._snapshots),
            "metrics_registered": len(self.registry._metrics),
            "total_data_points": len(self.registry._data_points),
        }


def setup_blastogene_dashboard(registry: MetricsRegistry) -> Dashboard:
    """配置暴躁因子默认看板"""
    # 注册核心指标
    metrics = [
        Metric("msg_count", "消息总数", "处理的消息总数", "条", "count"),
        Metric("alert_count", "告警次数", "触发的告警总数", "次", "count"),
        Metric("avg_sentiment", "平均情感值", "消息平均情感分数", "", "avg"),
        Metric("active_users", "活跃用户", "活跃用户数", "人", "count"),
        Metric("response_time", "平均响应时间", "消息处理平均耗时", "ms", "avg"),
    ]
    for m in metrics:
        registry.register(m)

    # 配置看板组件
    dashboard = Dashboard(registry)
    dashboard.add_widget("number", "消息总数", "msg_count")
    dashboard.add_widget("number", "告警次数", "alert_count")
    dashboard.add_widget("number", "活跃用户", "active_users")
    dashboard.add_widget("number", "平均情感", "avg_sentiment")
    dashboard.add_widget("number", "响应时间", "response_time")

    return dashboard
