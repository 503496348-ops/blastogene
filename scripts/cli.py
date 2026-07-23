#!/usr/bin/env python3
"""Blastogene — 暴躁因子社群运维 CLI"""
import argparse, json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def cmd_monitor(args):
    """Start message monitoring."""
    from blastogene.storage import MessageStore
    store = MessageStore()
    print(json.dumps({"store": type(store).__name__, "status": "monitoring_started"}, ensure_ascii=False, indent=2))

def cmd_alert(args):
    """Send test alert."""
    from blastogene.alerter import AlertManager, create_alert_manager
    manager = create_alert_manager()
    print(json.dumps({"alert_manager": type(manager).__name__, "status": "ok"}, ensure_ascii=False, indent=2))

def cmd_stats(args):
    """Show monitoring statistics."""
    from blastogene.aggregator import MetricsAggregator
    agg = MetricsAggregator()
    print(json.dumps({"aggregator": type(agg).__name__, "status": "ok"}, ensure_ascii=False, indent=2))

def cmd_analyze(args):
    """Analyze message sentiment."""
    from blastogene.sentiment import analyze_message, get_analyzer
    text = args.text or ''
    result = analyze_message(text)
    print(json.dumps({"text": text[:100], "result": str(result)[:300], "status": "ok"}, ensure_ascii=False, indent=2))

def cmd_init_db(args):
    """Initialize database."""
    from scripts.init_db import main as init_main
    init_main()
    print(json.dumps({"status": "db_initialized"}, ensure_ascii=False))


def cmd_info(args):
    """Show product info."""
    print(json.dumps({"product": "Blastogene", "type": "社群运维工具", "status": "ok"}, ensure_ascii=False, indent=2))
def main():
    p = argparse.ArgumentParser(description='Blastogene 暴躁因子社群运维工具')
    sub = p.add_subparsers(dest='command')

    sub.add_parser('monitor', help='启动消息监控')

    a = sub.add_parser('alert', help='发送测试告警')
    a.add_argument('--type', default='test')

    sub.add_parser('stats', help='查看监控统计')

    an = sub.add_parser('analyze', help='分析消息情感')
    an.add_argument('--text', required=True, help='消息文本')

    sub.add_parser('init-db', help='初始化数据库')
    sub.add_parser('info', help='产品信息')

    args = p.parse_args()
    if args.command == 'monitor': cmd_monitor(args)
    elif args.command == 'alert': cmd_alert(args)
    elif args.command == 'stats': cmd_stats(args)
    elif args.command == 'analyze': cmd_analyze(args)
    elif args.command == 'init-db': cmd_init_db(args)
    elif args.command == 'info': cmd_info(args)
    else: p.print_help()

if __name__ == '__main__':
    main()
