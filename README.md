# 暴躁因子-Blastogene

社群运营管理工具 - 飞书群消息监控、数据分析、告警通知、Web看板

## 功能特性

- **实时消息监控** - 飞书Webhook事件驱动，实时接收群消息
- **SQLite存储** - 轻量级本地存储，无外部依赖
- **指标聚合** - 消息数量、活跃用户、响应时间、参与度分数
- **智能告警** - 消息突增/骤降、关键词触发、无人响应检测
- **Web看板** - 可视化展示，只读API

## 快速开始

### 1. 安装依赖

```bash
cd ~/.hermes/skills/ops/blastogene
pip install -r requirements.txt
```

### 2. 初始化数据库

```bash
python scripts/init_db.py
```

### 3. 创建配置文件

```bash
python -m blastogene.config --create-default
```

编辑配置文件 `~/.hermes/config/blastogene.yaml`，添加要监控的群组ID。

### 4. 启动事件收集器

```bash
python -m blastogene.collector --port 8080
```

### 5. 启动Web看板

```bash
python -m blastogene.dashboard --port 8081
```

## 架构设计

```
飞书群事件 → Flask接收 → SQLite存储 → 聚合引擎 → 告警路由 → 通知发送
                                    ↓
                              Web看板(只读)
```

## 模块说明

| 模块 | 职责 | 主存储 |
|------|------|--------|
| `storage.py` | 数据库操作、幂等去重 | SQLite |
| `collector.py` | 飞书事件订阅、消息入库 | SQLite |
| `aggregator.py` | 指标聚合、统计计算 | SQLite |
| `alerter.py` | 告警规则、通知路由 | 配置文件 |
| `dashboard.py` | Web看板、只读API | 读SQLite |
| `config.py` | 配置管理、Bitable配置读取 | 配置文件 |

## API接口

### Web看板

- `GET /` - 看板主页
- `GET /api/chats` - 获取群组列表
- `GET /api/stats/<chat_id>` - 获取群组统计
- `GET /api/users/<chat_id>` - 获取活跃用户
- `GET /api/alerts/<chat_id>` - 获取告警列表
- `POST /api/alerts/<chat_id>/acknowledge` - 确认告警
- `GET /api/health` - 健康检查

### 事件收集器

- `POST /webhook/event` - 飞书事件回调
- `GET /webhook/health` - 健康检查
- `GET /webhook/stats` - 统计信息

## 告警规则

默认规则：

| 规则ID | 类型 | 严重程度 | 描述 |
|--------|------|----------|------|
| default_spike | message_spike | warning | 消息量突增50% |
| default_drop | message_drop | warning | 消息量骤降50% |
| default_keyword | keyword_trigger | critical | 关键词触发（广告、刷单等） |
| default_no_response | no_response | warning | 问题等待回复超过1小时 |

## Bitable职责边界

### ✅ 允许

- 配置管理入口（告警规则、监控目标）
- 低频人工录入（手动标记、备注）
- 聚合结果快照展示（日报、周报）

### ❌ 禁止

- 不作为原始消息主存储
- 不作为高频实时查询热路径
- 不作为复杂业务聚合引擎

## 配置示例

```yaml
database:
  path: ~/.hermes/data/blastogene.db
  cleanup_days: 90

monitoring:
  groups:
    - oc_xxxxxxxxxxxxxxxx
    - oc_yyyyyyyyyyyyyyyy
  check_interval: 300

alerts:
  enabled: true
  rules:
    - rule_id: custom_rule
      alert_type: message_spike
      severity: warning
      threshold: 2.0
      check_period: daily
  notify_chat: oc_zzzzzzzzzzzzzzzz

dashboard:
  enabled: true
  port: 8081

collector:
  enabled: true
  port: 8080
  verify_token: your_token_here
```

## 开发指南

### 运行测试

```bash
python scripts/test_blastogene.py
```

### 添加自定义告警规则

```python
from blastogene.alerter import AlertRule, AlertType, AlertSeverity

rule = AlertRule(
    rule_id="custom_rule",
    alert_type=AlertType.MESSAGE_SPIKE,
    severity=AlertSeverity.WARNING,
    threshold=2.0,
    check_period="daily"
)

alert_manager.add_rule(rule)
```

### 查询历史数据

```python
from blastogene.storage import MessageStore
from datetime import datetime, timedelta

store = MessageStore()

# 获取最近24小时的消息
messages = store.get_messages(
    chat_id="oc_xxxxxxxxxxxxxxxx",
    start_time=datetime.now() - timedelta(hours=24),
    limit=1000
)
```

## 限制与边界

- Phase 1仅支持飞书群消息监控
- 历史回补仅限"飞书当前可见窗口内"
- 统计口径标注"接入后累计"
- 不承诺恢复系统接入前全部历史数据

## 路线图

- [x] Phase 1: 核心功能实现
- [ ] Phase 2: 增强分析功能
  - [ ] 用户画像分析
  - [ ] 话题聚类
  - [ ] 情感分析
- [ ] Phase 3: 多平台支持
  - [ ] Telegram群组
  - [ ] Discord服务器
  - [ ] Slack工作区

## 许可证

MIT License

## 作者

AtomCollide
