"""
配置管理 - 配置文件读取与Bitable配置同步

管理告警规则、监控目标、通知设置等配置
"""

import os
import json
import yaml
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class DatabaseConfig:
    """数据库配置"""
    path: str = "~/.hermes/data/blastogene.db"
    backup_enabled: bool = True
    backup_interval_hours: int = 24
    cleanup_days: int = 90


@dataclass
class MonitoringConfig:
    """监控配置"""
    groups: List[str] = field(default_factory=list)
    check_interval: int = 300  # 5分钟
    realtime_keywords: bool = True


@dataclass
class AlertConfig:
    """告警配置"""
    enabled: bool = True
    rules: List[Dict[str, Any]] = field(default_factory=list)
    notify_chat: str = ""
    notify_users: List[str] = field(default_factory=list)


@dataclass
class DashboardConfig:
    """看板配置"""
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8081
    cors_enabled: bool = True


@dataclass
class CollectorConfig:
    """收集器配置"""
    enabled: bool = True
    host: str = "0.0.0.0"
    port: int = 8080
    verify_token: str = ""
    encrypt_key: str = ""


@dataclass
class BlastogeneConfig:
    """Blastogene主配置"""
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    monitoring: MonitoringConfig = field(default_factory=MonitoringConfig)
    alerts: AlertConfig = field(default_factory=AlertConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    collector: CollectorConfig = field(default_factory=CollectorConfig)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            'database': {
                'path': self.database.path,
                'backup_enabled': self.database.backup_enabled,
                'backup_interval_hours': self.database.backup_interval_hours,
                'cleanup_days': self.database.cleanup_days
            },
            'monitoring': {
                'groups': self.monitoring.groups,
                'check_interval': self.monitoring.check_interval,
                'realtime_keywords': self.monitoring.realtime_keywords
            },
            'alerts': {
                'enabled': self.alerts.enabled,
                'rules': self.alerts.rules,
                'notify_chat': self.alerts.notify_chat,
                'notify_users': self.alerts.notify_users
            },
            'dashboard': {
                'enabled': self.dashboard.enabled,
                'host': self.dashboard.host,
                'port': self.dashboard.port,
                'cors_enabled': self.dashboard.cors_enabled
            },
            'collector': {
                'enabled': self.collector.enabled,
                'host': self.collector.host,
                'port': self.collector.port,
                'verify_token': self.collector.verify_token,
                'encrypt_key': self.collector.encrypt_key
            }
        }


class ConfigManager:
    """配置管理器"""
    
    def __init__(self, config_path: str = None):
        """
        初始化配置管理器
        
        Args:
            config_path: 配置文件路径
        """
        if config_path is None:
            config_path = str(Path.home() / ".hermes" / "config" / "blastogene.yaml")
        
        self.config_path = Path(config_path)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.config = BlastogeneConfig()
        
        # 加载配置
        self.load_config()
    
    def load_config(self) -> BlastogeneConfig:
        """
        加载配置文件
        
        Returns:
            配置对象
        """
        if not self.config_path.exists():
            logger.info(f"Config file not found, using defaults: {self.config_path}")
            return self.config
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            
            if not data:
                return self.config
            
            # 解析数据库配置
            if 'database' in data:
                db_config = data['database']
                self.config.database = DatabaseConfig(
                    path=db_config.get('path', self.config.database.path),
                    backup_enabled=db_config.get('backup_enabled', self.config.database.backup_enabled),
                    backup_interval_hours=db_config.get('backup_interval_hours', self.config.database.backup_interval_hours),
                    cleanup_days=db_config.get('cleanup_days', self.config.database.cleanup_days)
                )
            
            # 解析监控配置
            if 'monitoring' in data:
                mon_config = data['monitoring']
                self.config.monitoring = MonitoringConfig(
                    groups=mon_config.get('groups', []),
                    check_interval=mon_config.get('check_interval', 300),
                    realtime_keywords=mon_config.get('realtime_keywords', True)
                )
            
            # 解析告警配置
            if 'alerts' in data:
                alert_config = data['alerts']
                self.config.alerts = AlertConfig(
                    enabled=alert_config.get('enabled', True),
                    rules=alert_config.get('rules', []),
                    notify_chat=alert_config.get('notify_chat', ''),
                    notify_users=alert_config.get('notify_users', [])
                )
            
            # 解析看板配置
            if 'dashboard' in data:
                dash_config = data['dashboard']
                self.config.dashboard = DashboardConfig(
                    enabled=dash_config.get('enabled', True),
                    host=dash_config.get('host', '0.0.0.0'),
                    port=dash_config.get('port', 8081),
                    cors_enabled=dash_config.get('cors_enabled', True)
                )
            
            # 解析收集器配置
            if 'collector' in data:
                coll_config = data['collector']
                self.config.collector = CollectorConfig(
                    enabled=coll_config.get('enabled', True),
                    host=coll_config.get('host', '0.0.0.0'),
                    port=coll_config.get('port', 8080),
                    verify_token=coll_config.get('verify_token', ''),
                    encrypt_key=coll_config.get('encrypt_key', '')
                )
            
            logger.info(f"Loaded config from {self.config_path}")
            return self.config
            
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            return self.config
    
    def save_config(self):
        """保存配置到文件"""
        try:
            data = self.config.to_dict()
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
            
            logger.info(f"Saved config to {self.config_path}")
            
        except Exception as e:
            logger.error(f"Error saving config: {e}")
            raise
    
    def update_config(self, updates: Dict[str, Any]):
        """
        更新配置
        
        Args:
            updates: 更新数据
        """
        # 深度合并配置
        self._deep_merge(self.config.to_dict(), updates)
        
        # 重新加载配置对象
        self.config = BlastogeneConfig()
        self.load_config()
        
        # 保存
        self.save_config()
    
    def _deep_merge(self, base: Dict, updates: Dict):
        """深度合并字典"""
        for key, value in updates.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value
    
    def get_config(self) -> BlastogeneConfig:
        """获取配置对象"""
        return self.config
    
    def get_database_path(self) -> str:
        """获取数据库路径（展开~）"""
        return os.path.expanduser(self.config.database.path)
    
    def get_monitoring_groups(self) -> List[str]:
        """获取监控群组列表"""
        return self.config.monitoring.groups
    
    def add_monitoring_group(self, chat_id: str):
        """添加监控群组"""
        if chat_id not in self.config.monitoring.groups:
            self.config.monitoring.groups.append(chat_id)
            self.save_config()
            logger.info(f"Added monitoring group: {chat_id}")
    
    def remove_monitoring_group(self, chat_id: str) -> bool:
        """移除监控群组"""
        if chat_id in self.config.monitoring.groups:
            self.config.monitoring.groups.remove(chat_id)
            self.save_config()
            logger.info(f"Removed monitoring group: {chat_id}")
            return True
        return False
    
    def get_alert_rules(self) -> List[Dict[str, Any]]:
        """获取告警规则"""
        return self.config.alerts.rules
    
    def add_alert_rule(self, rule: Dict[str, Any]):
        """添加告警规则"""
        # 检查是否已存在
        rule_id = rule.get('rule_id')
        for existing_rule in self.config.alerts.rules:
            if existing_rule.get('rule_id') == rule_id:
                # 更新现有规则
                self.config.alerts.rules.remove(existing_rule)
                break
        
        self.config.alerts.rules.append(rule)
        self.save_config()
        logger.info(f"Added alert rule: {rule_id}")
    
    def remove_alert_rule(self, rule_id: str) -> bool:
        """移除告警规则"""
        for rule in self.config.alerts.rules:
            if rule.get('rule_id') == rule_id:
                self.config.alerts.rules.remove(rule)
                self.save_config()
                logger.info(f"Removed alert rule: {rule_id}")
                return True
        return False
    
    def export_config(self) -> str:
        """导出配置为JSON字符串"""
        return json.dumps(self.config.to_dict(), indent=2, ensure_ascii=False)
    
    def import_config(self, json_str: str):
        """从JSON字符串导入配置"""
        try:
            data = json.loads(json_str)
            self.update_config(data)
            logger.info("Imported config from JSON")
        except Exception as e:
            logger.error(f"Error importing config: {e}")
            raise


# 默认配置模板
DEFAULT_CONFIG_TEMPLATE = """
# Blastogene 配置文件
# 详见 SKILL.md

database:
  path: ~/.hermes/data/blastogene.db
  backup_enabled: true
  backup_interval_hours: 24
  cleanup_days: 90

monitoring:
  groups:
    # 在此添加要监控的群组ID
    # - oc_xxxxxxxxxxxxxxxx
    # - oc_yyyyyyyyyyyyyyyy
  check_interval: 300  # 检查间隔（秒）
  realtime_keywords: true

alerts:
  enabled: true
  rules:
    - rule_id: default_spike
      alert_type: message_spike
      severity: warning
      threshold: 1.5
      comparison: gt
      check_period: daily
    
    - rule_id: default_drop
      alert_type: message_drop
      severity: warning
      threshold: 0.5
      comparison: lt
      check_period: daily
    
    - rule_id: default_keyword
      alert_type: keyword_trigger
      severity: critical
      keywords:
        - 广告
        - 刷单
        - 兼职
        - 赚钱
        - 加微信
    
    - rule_id: default_no_response
      alert_type: no_response
      severity: warning
      threshold: 3600  # 3600秒 = 1小时
      comparison: gt
      check_period: hourly
  
  notify_chat: ""  # 告警通知群组ID
  notify_users: []  # 告警通知用户ID列表

dashboard:
  enabled: true
  host: 0.0.0.0
  port: 8081
  cors_enabled: true

collector:
  enabled: true
  host: 0.0.0.0
  port: 8080
  verify_token: ""  # 飞书Webhook验证Token
  encrypt_key: ""   # 飞书事件加密密钥
"""


def create_default_config(config_path: str = None):
    """
    创建默认配置文件
    
    Args:
        config_path: 配置文件路径
    """
    if config_path is None:
        config_path = str(Path.home() / ".hermes" / "config" / "blastogene.yaml")
    
    config_path = Path(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    if config_path.exists():
        logger.warning(f"Config file already exists: {config_path}")
        return
    
    with open(config_path, 'w', encoding='utf-8') as f:
        f.write(DEFAULT_CONFIG_TEMPLATE)
    
    logger.info(f"Created default config: {config_path}")


def get_config_manager(config_path: str = None) -> ConfigManager:
    """
    获取配置管理器实例
    
    Args:
        config_path: 配置文件路径
    
    Returns:
        ConfigManager实例
    """
    return ConfigManager(config_path)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Blastogene Config Manager')
    parser.add_argument('--create-default', action='store_true', help='Create default config')
    parser.add_argument('--show', action='store_true', help='Show current config')
    parser.add_argument('--add-group', help='Add monitoring group')
    parser.add_argument('--remove-group', help='Remove monitoring group')
    parser.add_argument('--export', action='store_true', help='Export config as JSON')
    parser.add_argument('--import-json', help='Import config from JSON')
    
    args = parser.parse_args()
    
    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    if args.create_default:
        create_default_config()
        print("Created default config file")
    else:
        manager = get_config_manager()
        
        if args.show:
            print("\nCurrent Configuration:")
            print(manager.export_config())
        
        elif args.add_group:
            manager.add_monitoring_group(args.add_group)
            print(f"Added group: {args.add_group}")
        
        elif args.remove_group:
            if manager.remove_monitoring_group(args.remove_group):
                print(f"Removed group: {args.remove_group}")
            else:
                print(f"Group not found: {args.remove_group}")
        
        elif args.export:
            print(manager.export_config())
        
        elif args.import_json:
            manager.import_config(args.import_json)
            print("Imported config from JSON")
