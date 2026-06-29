---
name: blastogene
description: 暴躁因子-Blastogene 社群运营管理工具 - 飞书群消息监控、数据分析、告警通知、Web看板
triggers:
  - 社群监控
  - 群消息分析
  - 社群运营
  - 群活跃度
  - 社群健康度
  - blastogene
version: 1.0.0
author: AtomCollide
tags: [feishu, community, analytics, monitoring, dashboard]
---

# 暴躁因子-Blastogene

社群运营管理工具 - 飞书群消息监控、数据分析、告警通知、Web看板

## 架构设计

```
飞书群事件 → 事件收集器 → SQLite存储 → 聚合引擎 → 告警路由 → 通知发送
                                    ↓
                              Web看板(只读)
```

### 核心原则

1. **原始事件进入SQLite** - Phase 1主存储，轻量无依赖
2. **Bitable只做配置和展示** - 不承担原始消息存储，不做高频查询
3. **Web看板通过API读取** - 读取聚合结果，不直接读Bitable
4. **事件驱动** - 飞书webhook推送，不轮询

## 快速开始

### 1. 安装依赖

```bash
cd ~/.hermes/skills/blastogene
pip install -r requirements.txt
```

### 2. 初始化数据库

```bash
python -m blastogene.init_db
```

### 3. 启动事件收集器

```bash
python -m blastogene.collector --port 8080
```

### 4. 启动Web看板

```bash
python -m blastogene.dashboard --port 8081
```

## 模块说明

| 模块 | 职责 | 主存储 |
|------|------|--------|
| collector.py | 飞书事件订阅、消息入库 | SQLite |
| storage.py | 数据库操作、幂等去重 | SQLite |
| aggregator.py | 指标聚合、统计计算 | SQLite |
| alerter.py | 告警规则、通知路由 | 配置文件 |
| dashboard.py | Web看板、只读API | 读SQLite |
| config.py | 配置管理、Bitable配置读取 | 配置文件 |

## Bitable职责边界

### ✅ 允许
- 配置管理入口（告警规则、监控目标）
- 低频人工录入（手动标记、备注）
- 聚合结果快照展示（日报、周报）

### ❌ 禁止
- 不作为原始消息主存储
- 不作为高频实时查询热路径
- 不作为复杂业务聚合引擎

## 告警规则

默认规则：
- 群消息量突增/骤降（环比变化>50%）
- 关键词触发（广告、违规内容）
- 成员异常退出（短时间内大量退出）
- 无人响应（提问超过N小时无回复）

## 数据流

```
飞书Webhook → Flask接收 → 解析事件 → SQLite写入
                                    ↓
定时任务(cron) → 聚合计算 → 更新统计表
                                    ↓
告警检查 → 飞书消息通知
                                    ↓
Web看板 → 读取统计表 → 可视化展示
```

## 配置示例

```yaml
blastogene:
  database:
    path: ~/.hermes/data/blastogene.db
  monitoring:
    groups:
      - oc_xxxxxxxxxxxxxxxx
      - oc_yyyyyyyyyyyyyyyy
    check_interval: 300  # 5分钟
  alerts:
    rules:
      - type: message_spike
        threshold: 1.5  # 环比增长50%
      - type: message_drop
        threshold: 0.5  # 环比下降50%
    notify_chat: oc_zzzzzzzzzzzzzzzz
  dashboard:
    port: 8081
    host: 0.0.0.0
```

## 限制与边界

- Phase 1仅支持飞书群消息监控
- 历史回补仅限"飞书当前可见窗口内"
- 统计口径标注"接入后累计"
- 不承诺恢复系统接入前全部历史数据
