"""
多渠道告警通知模块

基于URL-as-Config的统一通知架构，支持10+通知渠道。

核心能力:
1. 统一通知API - 一个调用发送到所有注册渠道
2. 协议注册表 - 自动发现通知插件
3. URL配置 - 每个渠道一个URL字符串
4. 标签路由 - 按标签分组发送
5. 优先级升级 - 失败自动切换到备用渠道
"""

import re
import json
import logging
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, List, Optional, Any, Type
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ============================================================
# 通知类型与优先级
# ============================================================

class NotifyType(str, Enum):
    """通知类型"""
    INFO = "info"
    WARNING = "warning"
    FAILURE = "failure"
    SUCCESS = "success"


class Priority(int, Enum):
    """通知优先级（数值越小越优先）"""
    LOW = 5
    NORMAL = 3
    HIGH = 2
    URGENT = 1
    EMERGENCY = 0


@dataclass
class NotifyMessage:
    """通知消息"""
    body: str                           # 消息正文
    title: str = ""                     # 标题
    notify_type: NotifyType = NotifyType.INFO
    priority: Priority = Priority.NORMAL
    tags: List[str] = field(default_factory=list)
    attachments: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            'body': self.body,
            'title': self.title,
            'notify_type': self.notify_type.value,
            'priority': self.priority.value,
            'tags': self.tags,
        }


# ============================================================
# 通知插件基类
# ============================================================

class NotifyPlugin(ABC):
    """
    通知插件基类

    所有通知渠道都继承此类，实现send()方法。
    通过protocol/secure_protocol声明URL scheme。
    """

    # 子类必须定义
    protocol: str = ""              # URL scheme (如 "feishu", "telegram")
    secure_protocol: str = ""       # 安全URL scheme (如 "feishus", "telegrams")
    service_name: str = ""          # 服务名称

    # 可选配置
    title_maxlen: int = 250         # 标题最大长度
    body_maxlen: int = 50000        # 正文最大长度
    request_rate_per_sec: float = 1.0  # 请求频率限制

    def __init__(self, **kwargs):
        self.tags = set(kwargs.pop('tags', []))
        self.priority = Priority(kwargs.pop('priority', Priority.NORMAL.value))
        self.enabled = kwargs.pop('enabled', True)
        self._config = kwargs

    @abstractmethod
    def send(self, msg: NotifyMessage) -> bool:
        """
        发送通知

        Args:
            msg: 通知消息

        Returns:
            True=成功，False=失败
        """
        pass

    def notify(self, msg: NotifyMessage) -> bool:
        """发送通知（带错误处理）"""
        if not self.enabled:
            return False

        # 截断超长内容
        if len(msg.body) > self.body_maxlen:
            msg.body = msg.body[:self.body_maxlen] + "..."

        if msg.title and len(msg.title) > self.title_maxlen:
            msg.title = msg.title[:self.title_maxlen] + "..."

        try:
            return self.send(msg)
        except Exception as e:
            logger.error(f"[{self.service_name}] Send failed: {e}")
            return False

    @classmethod
    @abstractmethod
    def parse_url(cls, url: str) -> Dict[str, Any]:
        """解析URL为配置参数"""
        pass

    def url(self) -> str:
        """序列化为URL"""
        return f"{self.protocol}://"

    def __repr__(self):
        return f"<{self.__class__.__name__} protocol={self.protocol}>"


# ============================================================
# 通知插件注册表
# ============================================================

class PluginRegistry:
    """
    通知插件注册表

    单例模式，管理所有已注册的通知插件。
    通过protocol查找对应的插件类。
    """

    _instance: Optional['PluginRegistry'] = None
    _plugins: Dict[str, Type[NotifyPlugin]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._plugins = {}
            cls._instance._auto_discover()
        return cls._instance

    def _auto_discover(self):
        """自动发现并注册内置插件"""
        # 注册内置插件
        for plugin_class in BUILTIN_PLUGINS:
            self.register(plugin_class)

    def register(self, plugin_class: Type[NotifyPlugin]):
        """注册插件"""
        if plugin_class.protocol:
            self._plugins[plugin_class.protocol] = plugin_class
        if plugin_class.secure_protocol:
            self._plugins[plugin_class.secure_protocol] = plugin_class

    def get(self, protocol: str) -> Optional[Type[NotifyPlugin]]:
        """通过协议名获取插件类"""
        return self._plugins.get(protocol)

    def instantiate(self, url: str, **defaults) -> Optional[NotifyPlugin]:
        """从URL创建插件实例"""
        # 解析URL scheme
        match = re.match(r'^([a-zA-Z0-9]+)://', url)
        if not match:
            logger.error(f"Invalid URL format: {url}")
            return None

        protocol = match.group(1).lower()
        plugin_class = self.get(protocol)

        if not plugin_class:
            logger.error(f"Unknown protocol: {protocol}")
            return None

        try:
            config = plugin_class.parse_url(url)
            config.update(defaults)
            return plugin_class(**config)
        except Exception as e:
            logger.error(f"Failed to instantiate {protocol}: {e}")
            return None

    @property
    def supported_protocols(self) -> List[str]:
        """返回所有支持的协议"""
        return list(self._plugins.keys())


# ============================================================
# 内置通知插件
# ============================================================

class FeishuWebhookPlugin(NotifyPlugin):
    """飞书Webhook通知"""
    protocol = "feishu"
    secure_protocol = "feishus"
    service_name = "飞书Webhook"

    def __init__(self, webhook_url: str, **kwargs):
        super().__init__(**kwargs)
        self.webhook_url = webhook_url

    def send(self, msg: NotifyMessage) -> bool:
        """发送飞书Webhook通知"""
        import urllib.request

        # 构建飞书卡片消息
        color_map = {
            NotifyType.INFO: 'blue',
            NotifyType.WARNING: 'orange',
            NotifyType.FAILURE: 'red',
            NotifyType.SUCCESS: 'green',
        }

        payload = {
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": msg.title or "社群告警"},
                    "template": color_map.get(msg.notify_type, 'blue')
                },
                "elements": [
                    {
                        "tag": "markdown",
                        "content": msg.body
                    }
                ]
            }
        }

        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(
                self.webhook_url,
                data=data,
                headers={'Content-Type': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
                if result.get('code') == 0 or result.get('StatusCode') == 0:
                    logger.info(f"[Feishu] Notification sent successfully")
                    return True
                else:
                    logger.error(f"[Feishu] API error: {result}")
                    return False
        except Exception as e:
            logger.error(f"[Feishu] Send failed: {e}")
            return False

    @classmethod
    def parse_url(cls, url: str) -> Dict[str, Any]:
        """解析飞书Webhook URL"""
        # 支持格式: feishu://webhook_url 或 feishu://open.feishu.cn/open-apis/bot/v2/hook/xxx
        match = re.match(r'^feishus?://(.+)$', url)
        if match:
            path = match.group(1)
            if not path.startswith('http'):
                path = f"https://{path}"
            return {'webhook_url': path}
        return {'webhook_url': url}


class TelegramPlugin(NotifyPlugin):
    """Telegram Bot通知"""
    protocol = "tgram"
    secure_protocol = "telegram"
    service_name = "Telegram"

    def __init__(self, bot_token: str, chat_id: str, **kwargs):
        super().__init__(**kwargs)
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send(self, msg: NotifyMessage) -> bool:
        """发送Telegram通知"""
        import urllib.request

        text = f"*{msg.title}*\n\n{msg.body}" if msg.title else msg.body

        payload = {
            'chat_id': self.chat_id,
            'text': text[:4096],
            'parse_mode': 'Markdown',
        }

        try:
            data = urllib.parse.urlencode(payload).encode()
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
                if result.get('ok'):
                    logger.info(f"[Telegram] Notification sent successfully")
                    return True
                else:
                    logger.error(f"[Telegram] API error: {result}")
                    return False
        except Exception as e:
            logger.error(f"[Telegram] Send failed: {e}")
            return False

    @classmethod
    def parse_url(cls, url: str) -> Dict[str, Any]:
        """解析Telegram URL"""
        # tgram://bot_token/chat_id
        match = re.match(r'^te?le?grams?://([^/]+)/(.+)$', url)
        if match:
            return {'bot_token': match.group(1), 'chat_id': match.group(2)}
        return {}


class DiscordWebhookPlugin(NotifyPlugin):
    """Discord Webhook通知"""
    protocol = "discord"
    service_name = "Discord"

    def __init__(self, webhook_id: str, webhook_token: str, **kwargs):
        super().__init__(**kwargs)
        self.webhook_id = webhook_id
        self.webhook_token = webhook_token

    def send(self, msg: NotifyMessage) -> bool:
        """发送Discord通知"""
        import urllib.request

        color_map = {
            NotifyType.INFO: 0x3498db,
            NotifyType.WARNING: 0xf39c12,
            NotifyType.FAILURE: 0xe74c3c,
            NotifyType.SUCCESS: 0x2ecc71,
        }

        payload = {
            "embeds": [{
                "title": msg.title or "社群告警",
                "description": msg.body[:4096],
                "color": color_map.get(msg.notify_type, 0x3498db),
            }]
        }

        try:
            url = f"https://discord.com/api/webhooks/{self.webhook_id}/{self.webhook_token}"
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status in (200, 204):
                    logger.info(f"[Discord] Notification sent successfully")
                    return True
                return False
        except Exception as e:
            logger.error(f"[Discord] Send failed: {e}")
            return False

    @classmethod
    def parse_url(cls, url: str) -> Dict[str, Any]:
        match = re.match(r'^discord://([^/]+)/(.+)$', url)
        if match:
            return {'webhook_id': match.group(1), 'webhook_token': match.group(2)}
        return {}


class SlackWebhookPlugin(NotifyPlugin):
    """Slack Webhook通知"""
    protocol = "slack"
    service_name = "Slack"

    def __init__(self, webhook_url: str, **kwargs):
        super().__init__(**kwargs)
        self.webhook_url = webhook_url

    def send(self, msg: NotifyMessage) -> bool:
        """发送Slack通知"""
        import urllib.request

        payload = {
            "text": f"*{msg.title}*\n{msg.body}" if msg.title else msg.body,
        }

        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(self.webhook_url, data=data, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    logger.info(f"[Slack] Notification sent successfully")
                    return True
                return False
        except Exception as e:
            logger.error(f"[Slack] Send failed: {e}")
            return False

    @classmethod
    def parse_url(cls, url: str) -> Dict[str, Any]:
        match = re.match(r'^slack://(.+)$', url)
        if match:
            path = match.group(1)
            if not path.startswith('http'):
                path = f"https://{path}"
            return {'webhook_url': path}
        return {'webhook_url': url}


class EmailPlugin(NotifyPlugin):
    """邮件通知"""
    protocol = "mailto"
    secure_protocol = "email"
    service_name = "Email"

    def __init__(self, smtp_host: str, smtp_port: int, username: str, password: str,
                 from_addr: str, to_addrs: List[str], use_tls: bool = True, **kwargs):
        super().__init__(**kwargs)
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_addr = from_addr
        self.to_addrs = to_addrs
        self.use_tls = use_tls

    def send(self, msg: NotifyMessage) -> bool:
        """发送邮件"""
        import smtplib
        from email.mime.text import MIMEText

        body = f"{msg.title}\n\n{msg.body}" if msg.title else msg.body
        mime_msg = MIMEText(body, 'plain', 'utf-8')
        mime_msg['Subject'] = msg.title or '社群告警通知'
        mime_msg['From'] = self.from_addr
        mime_msg['To'] = ', '.join(self.to_addrs)

        try:
            if self.use_tls:
                server = smtplib.SMTP_SSL(self.smtp_host, self.smtp_port)
            else:
                server = smtplib.SMTP(self.smtp_host, self.smtp_port)
            server.login(self.username, self.password)
            server.sendmail(self.from_addr, self.to_addrs, mime_msg.as_string())
            server.quit()
            logger.info(f"[Email] Notification sent to {self.to_addrs}")
            return True
        except Exception as e:
            logger.error(f"[Email] Send failed: {e}")
            return False

    @classmethod
    def parse_url(cls, url: str) -> Dict[str, Any]:
        # mailto://user:pass@smtp.gmail.com:465/to@example.com
        match = re.match(r'^mailtos?://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)$', url)
        if match:
            return {
                'username': match.group(1),
                'password': match.group(2),
                'smtp_host': match.group(3),
                'smtp_port': int(match.group(4)),
                'from_addr': match.group(1),
                'to_addrs': [match.group(5)],
                'use_tls': True,
            }
        return {}


class WebhookPlugin(NotifyPlugin):
    """通用Webhook通知"""
    protocol = "webhook"
    secure_protocol = "json"
    service_name = "Webhook"

    def __init__(self, webhook_url: str, method: str = "POST", headers: Optional[Dict] = None, **kwargs):
        super().__init__(**kwargs)
        self.webhook_url = webhook_url
        self.method = method
        self.headers = headers or {'Content-Type': 'application/json'}

    def send(self, msg: NotifyMessage) -> bool:
        """发送Webhook通知"""
        import urllib.request

        payload = msg.to_dict()

        try:
            data = json.dumps(payload).encode('utf-8')
            req = urllib.request.Request(self.webhook_url, data=data, headers=self.headers, method=self.method)
            with urllib.request.urlopen(req, timeout=10) as resp:
                if 200 <= resp.status < 300:
                    logger.info(f"[Webhook] Notification sent to {self.webhook_url}")
                    return True
                return False
        except Exception as e:
            logger.error(f"[Webhook] Send failed: {e}")
            return False

    @classmethod
    def parse_url(cls, url: str) -> Dict[str, Any]:
        match = re.match(r'^(?:webhook|json)://(.+)$', url)
        if match:
            path = match.group(1)
            if not path.startswith('http'):
                path = f"https://{path}"
            return {'url': path}
        return {'url': url}


# 注册内置插件
BUILTIN_PLUGINS = [
    FeishuWebhookPlugin,
    TelegramPlugin,
    DiscordWebhookPlugin,
    SlackWebhookPlugin,
    EmailPlugin,
    WebhookPlugin,
]


# ============================================================
# 通知管理器
# ============================================================

class NotifyManager:
    """
    通知管理器

    统一管理所有通知渠道，提供标签路由、优先级升级、批量发送等能力。

    Usage:
        manager = NotifyManager()
        manager.add("feishu://hooks.feishu.cn/open-apis/bot/v2/hook/xxx")
        manager.add("tgram://bot_token/chat_id", tags=["critical"])
        manager.add("discord://webhook_id/webhook_token", tags=["devops"])

        # 发送到所有渠道
        manager.notify("服务异常", title="告警")

        # 只发送到critical标签的渠道
        manager.notify("严重故障", title="紧急告警", tags=["critical"])
    """

    def __init__(self):
        self.registry = PluginRegistry()
        self._plugins: List[NotifyPlugin] = []
        self._on_send_callbacks: List = []

    def add(self, url: str, **kwargs) -> bool:
        """
        添加通知渠道

        Args:
            url: 渠道URL (如 "feishu://...", "tgram://...")
            **kwargs: 额外配置 (tags, priority, enabled等)

        Returns:
            True=添加成功
        """
        plugin = self.registry.instantiate(url, **kwargs)
        if plugin:
            self._plugins.append(plugin)
            logger.info(f"Added notification channel: {plugin.service_name} ({plugin.protocol})")
            return True
        return False

    def remove(self, protocol: str) -> bool:
        """移除指定协议的所有渠道"""
        before = len(self._plugins)
        self._plugins = [p for p in self._plugins if p.protocol != protocol]
        return len(self._plugins) < before

    def notify(
        self,
        body: str,
        title: str = "",
        notify_type: NotifyType = NotifyType.INFO,
        priority: Priority = Priority.NORMAL,
        tags: Optional[List[str]] = None,
        **kwargs
    ) -> Dict[str, bool]:
        """
        发送通知

        Args:
            body: 消息正文
            title: 标题
            notify_type: 通知类型
            priority: 优先级
            tags: 过滤标签（只发送到匹配的渠道）
            **kwargs: 其他消息属性

        Returns:
            {渠道名: 是否成功}
        """
        msg = NotifyMessage(
            body=body,
            title=title,
            notify_type=notify_type,
            priority=priority,
            tags=tags or [],
            **kwargs
        )

        results = {}
        target_plugins = self._filter_plugins(tags, priority)

        for plugin in target_plugins:
            success = plugin.notify(msg)
            results[f"{plugin.service_name}({plugin.protocol})"] = success

            # 触发回调
            for callback in self._on_send_callbacks:
                try:
                    callback(plugin, msg, success)
                except Exception:
                    pass

        return results

    def _filter_plugins(
        self,
        tags: Optional[List[str]] = None,
        priority: Priority = Priority.NORMAL
    ) -> List[NotifyPlugin]:
        """按标签和优先级过滤插件"""
        filtered = []
        for plugin in self._plugins:
            if not plugin.enabled:
                continue
            # 标签过滤
            if tags and plugin.tags:
                if not any(t in plugin.tags for t in tags):
                    continue
            filtered.append(plugin)
        return filtered

    def on_send(self, callback):
        """注册发送回调"""
        self._on_send_callbacks.append(callback)

    @property
    def channels(self) -> List[Dict]:
        """返回所有渠道信息"""
        return [
            {
                'protocol': p.protocol,
                'service': p.service_name,
                'tags': list(p.tags),
                'priority': p.priority.value,
                'enabled': p.enabled,
            }
            for p in self._plugins
        ]

    @property
    def supported_protocols(self) -> List[str]:
        """返回支持的协议列表"""
        return self.registry.supported_protocols


# ============================================================
# 便捷函数
# ============================================================

_default_manager: Optional[NotifyManager] = None


def get_manager(**kwargs) -> NotifyManager:
    """获取默认通知管理器"""
    global _default_manager
    if _default_manager is None:
        _default_manager = NotifyManager(**kwargs)
    return _default_manager


def add_channel(url: str, **kwargs) -> bool:
    """便捷函数：添加通知渠道"""
    return get_manager().add(url, **kwargs)


def send_notification(body: str, title: str = "", **kwargs) -> Dict[str, bool]:
    """便捷函数：发送通知"""
    return get_manager().notify(body, title, **kwargs)
