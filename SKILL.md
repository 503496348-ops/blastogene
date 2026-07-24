---
name: blastogene
description: "社群运维工具 — 消息监控、情感分析、告警管理、指标聚合"
license: MIT
metadata:
  author: 503496348-ops
  version: 1.0.0
triggers:
  - "社群"
  - "监控"
  - "情感分析"
  - "告警"
  - "群消息"
  - "社群运维"
---

# Blastogene — 暴躁因子社群运维

群聊消息实时监控 + 情感/敏感词分析 + 自动告警 + 指标聚合。

## 核心能力

| 命令 | 说明 |
|------|------|
| `blastogene monitor` | 启动消息监控 |
| `blastogene analyze --text <text>` | 分析消息情感 |
| `blastogene alert` | 发送测试告警 |
| `blastogene stats` | 查看监控统计 |
| `blastogene init-db` | 初始化数据库 |

## 快速开始

```bash
# 分析消息情感
python3 scripts/cli.py analyze --text "这个功能太棒了！"

# 启动监控
python3 scripts/cli.py monitor

# 初始化数据库
python3 scripts/cli.py init-db
```

## 架构

- `blastogene/sentiment.py` — Aho-Corasick 情感/敏感词分析引擎
- `blastogene/alerter.py` — AlertManager 告警管理
- `blastogene/aggregator.py` — MetricsAggregator 指标聚合
- `blastogene/storage.py` — MessageStore 存储层
- `blastogene/notifier.py` — 通知推送

## 测试

```bash
python3 -m pytest tests/ -q
```
