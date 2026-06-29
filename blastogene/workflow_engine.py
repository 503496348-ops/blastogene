
"""
工作流编排模块

核心能力：
- 声明式工作流定义（YAML/JSON）
- 节点式任务编排（串行/并行/条件分支）
- 任务状态机与重试策略
- 工作流模板与复用
- 运行历史与审计日志
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger(__name__)


class TaskState(Enum):
    PENDING = "pending"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"
    SKIPPED = "skipped"


class NodeType(Enum):
    TRIGGER = "trigger"        # 触发器（定时/事件/手动）
    ACTION = "action"          # 动作（发送/写入/调用）
    CONDITION = "condition"    # 条件判断
    TRANSFORM = "transform"    # 数据转换
    AGGREGATE = "aggregate"    # 聚合合并
    SUBFLOW = "subflow"        # 子工作流


@dataclass
class RetryPolicy:
    """重试策略"""
    max_retries: int = 3
    delay_seconds: float = 1.0
    backoff_factor: float = 2.0
    max_delay_seconds: float = 60.0
    retry_on: Optional[List[str]] = None   # 可重试的错误类型

    def get_delay(self, attempt: int) -> float:
        delay = self.delay_seconds * (self.backoff_factor ** attempt)
        return min(delay, self.max_delay_seconds)


@dataclass
class TaskResult:
    """任务执行结果"""
    task_id: str
    state: TaskState
    output: Any = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    attempt: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowNode:
    id: str
    name: str
    node_type: NodeType
    handler: Optional[Callable] = None     # 执行函数
    config: Dict[str, Any] = field(default_factory=dict)
    retry_policy: Optional[RetryPolicy] = None
    timeout_seconds: float = 300
    depends_on: List[str] = field(default_factory=list)  # 依赖的节点ID
    condition: Optional[Callable] = None   # 条件节点的判断函数

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "name": self.name,
            "type": self.node_type.value,
            "config": self.config,
            "depends_on": self.depends_on,
        }


@dataclass
class WorkflowRun:
    """工作流运行实例"""
    run_id: str
    workflow_id: str
    state: TaskState = TaskState.PENDING
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    task_results: Dict[str, TaskResult] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    def to_dict(self) -> Dict:
        return {
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "state": self.state.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_seconds": self.duration_seconds,
            "task_count": len(self.task_results),
            "tasks": {tid: tr.state.value for tid, tr in self.task_results.items()},
        }


class WorkflowEngine:
    """工作流编排引擎"""

    def __init__(self, max_concurrent_tasks: int = 10):
        self._workflows: Dict[str, Dict[str, WorkflowNode]] = {}  # workflow_id -> nodes
        self._runs: List[WorkflowRun] = []
        self._templates: Dict[str, Dict] = {}
        self._max_concurrent = max_concurrent_tasks
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self.logger = logging.getLogger(__name__)

    def register_workflow(self, workflow_id: str, nodes: List[WorkflowNode]):
        """注册工作流"""
        self._workflows[workflow_id] = {n.id: n for n in nodes}
        self.logger.info("Registered workflow '%s' with %d nodes", workflow_id, len(nodes))

    def register_template(self, template_id: str, template: Dict):
        """注册工作流模板"""
        self._templates[template_id] = template

    async def execute(self, workflow_id: str,
                     context: Optional[Dict] = None) -> WorkflowRun:
        """执行工作流"""
        nodes = self._workflows.get(workflow_id)
        if not nodes:
            raise ValueError(f"Workflow '{workflow_id}' not found")

        run = WorkflowRun(
            run_id=str(uuid.uuid4())[:8],
            workflow_id=workflow_id,
            state=TaskState.RUNNING,
            started_at=datetime.now(),
            context=context or {},
        )
        self._runs.append(run)
        self.logger.info("Starting workflow '%s' run %s", workflow_id, run.run_id)

        # 拓扑排序并执行
        execution_order = self._topological_sort(nodes)

        for batch in execution_order:
            # 同一批次并行执行
            tasks = []
            for node_id in batch:
                node = nodes[node_id]
                # 检查条件
                if node.node_type == NodeType.CONDITION and node.condition:
                    if not node.condition(run.context):
                        run.task_results[node_id] = TaskResult(
                            task_id=node_id, state=TaskState.SKIPPED,
                        )
                        continue
                tasks.append(self._execute_node(node, run))

            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        # 计算最终状态
        failed = [tr for tr in run.task_results.values() if tr.state == TaskState.FAILED]
        run.state = TaskState.FAILED if failed else TaskState.SUCCESS
        run.finished_at = datetime.now()

        self.logger.info("Workflow '%s' run %s completed: %s (%.1fs)",
                        workflow_id, run.run_id, run.state.value,
                        run.duration_seconds or 0)
        return run

    async def _execute_node(self, node: WorkflowNode, run: WorkflowRun):
        """执行单个节点"""
        result = TaskResult(
            task_id=node.id,
            state=TaskState.RUNNING,
            started_at=datetime.now(),
        )
        run.task_results[node.id] = result

        retry_policy = node.retry_policy or RetryPolicy(max_retries=0)

        for attempt in range(retry_policy.max_retries + 1):
            result.attempt = attempt
            try:
                if node.handler:
                    if asyncio.iscoroutinefunction(node.handler):
                        output = await asyncio.wait_for(
                            node.handler(run.context, node.config),
                            timeout=node.timeout_seconds,
                        )
                    else:
                        output = node.handler(run.context, node.config)
                    result.output = output
                    result.state = TaskState.SUCCESS
                    # 输出写入上下文供下游使用
                    run.context[node.id] = output
                    break
                else:
                    result.state = TaskState.SUCCESS
                    break
            except asyncio.TimeoutError:
                result.error = f"Timeout after {node.timeout_seconds}s"
                result.state = TaskState.RETRYING
            except Exception as e:
                result.error = str(e)
                if attempt < retry_policy.max_retries:
                    result.state = TaskState.RETRYING
                    delay = retry_policy.get_delay(attempt)
                    self.logger.warning("Node '%s' attempt %d failed, retrying in %.1fs: %s",
                                       node.id, attempt + 1, delay, e)
                    await asyncio.sleep(delay)
                else:
                    result.state = TaskState.FAILED
                    self.logger.error("Node '%s' failed after %d attempts: %s",
                                     node.id, attempt + 1, e)

        result.finished_at = datetime.now()

    def _topological_sort(self, nodes: Dict[str, WorkflowNode]) -> List[List[str]]:
        """拓扑排序 - 返回按层级分组的执行顺序"""
        in_degree = {nid: 0 for nid in nodes}
        for nid, node in nodes.items():
            for dep in node.depends_on:
                if dep in in_degree:
                    in_degree[nid] += 1

        layers = []
        remaining = set(nodes.keys())

        while remaining:
            # 找出入度为0的节点
            batch = [nid for nid in remaining if in_degree[nid] == 0]
            if not batch:
                # 有环，强制打断
                batch = [remaining.pop()]
                self.logger.warning("Cycle detected, forcing node: %s", batch[0])

            layers.append(batch)
            for nid in batch:
                remaining.discard(nid)
                # 更新依赖此节点的入度
                for other_nid, other_node in nodes.items():
                    if nid in other_node.depends_on:
                        in_degree[other_nid] -= 1

        return layers

    def get_runs(self, workflow_id: Optional[str] = None,
                limit: int = 20) -> List[Dict]:
        """获取运行历史"""
        runs = self._runs
        if workflow_id:
            runs = [r for r in runs if r.workflow_id == workflow_id]
        return [r.to_dict() for r in runs[-limit:]]

    def get_stats(self) -> Dict[str, Any]:
        """获取引擎统计"""
        return {
            "registered_workflows": len(self._workflows),
            "total_runs": len(self._runs),
            "templates": len(self._templates),
            "recent_runs": [r.to_dict() for r in self._runs[-5:]],
        }


# === 预置工作流模板 ===

def create_alert_workflow() -> List[WorkflowNode]:
    """创建告警处理工作流模板"""
    return [
        WorkflowNode(
            id="trigger", name="告警触发",
            node_type=NodeType.TRIGGER,
        ),
        WorkflowNode(
            id="classify", name="告警分类",
            node_type=NodeType.TRANSFORM,
            handler=lambda ctx, cfg: {"level": "warning"},
            depends_on=["trigger"],
        ),
        WorkflowNode(
            id="notify", name="发送通知",
            node_type=NodeType.ACTION,
            handler=lambda ctx, cfg: {"sent": True},
            depends_on=["classify"],
        ),
        WorkflowNode(
            id="log", name="记录日志",
            node_type=NodeType.ACTION,
            handler=lambda ctx, cfg: {"logged": True},
            depends_on=["classify"],
        ),
    ]


def create_moderation_workflow() -> List[WorkflowNode]:
    """创建内容审核工作流模板"""
    return [
        WorkflowNode(
            id="receive", name="接收消息",
            node_type=NodeType.TRIGGER,
        ),
        WorkflowNode(
            id="analyze", name="情感分析",
            node_type=NodeType.ACTION,
            handler=lambda ctx, cfg: {"sentiment": "neutral"},
            depends_on=["receive"],
        ),
        WorkflowNode(
            id="check_sensitive", name="敏感词检测",
            node_type=NodeType.ACTION,
            handler=lambda ctx, cfg: {"has_sensitive": False},
            depends_on=["receive"],
        ),
        WorkflowNode(
            id="decide", name="审核决策",
            node_type=NodeType.CONDITION,
            condition=lambda ctx: not ctx.get("check_sensitive", {}).get("has_sensitive", False),
            depends_on=["analyze", "check_sensitive"],
        ),
        WorkflowNode(
            id="approve", name="通过",
            node_type=NodeType.ACTION,
            depends_on=["decide"],
        ),
        WorkflowNode(
            id="reject", name="拦截",
            node_type=NodeType.ACTION,
            depends_on=["decide"],
        ),
    ]
