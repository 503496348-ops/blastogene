
"""
多平台统一管理模块

核心能力：
- 统一消息接口适配（飞书/Telegram/Discord/微信）
- 平台事件标准化与路由分发
- 多平台状态同步与会话管理
- 插件式平台扩展
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


logger = logging.getLogger(__name__)


class PlatformType(Enum):
    """支持的平台类型"""
    FEISHU = "feishu"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    WECHAT = "wechat"
    WEB = "web"
    CLI = "cli"


class MessageType(Enum):
    """消息类型"""
    TEXT = "text"
    IMAGE = "image"
    FILE = "file"
    AUDIO = "audio"
    VIDEO = "video"
    CARD = "card"        # 飞书卡片
    STICKER = "sticker"
    REACTION = "reaction"
    SYSTEM = "system"


@dataclass
class UnifiedMessage:
    """统一消息格式 - 跨平台消息标准化"""
    message_id: str
    platform: PlatformType
    chat_id: str
    sender_id: str
    sender_name: str
    content: str
    message_type: MessageType = MessageType.TEXT
    timestamp: datetime = field(default_factory=datetime.now)
    raw_event: Optional[Dict] = None          # 原始平台事件
    reply_to: Optional[str] = None            # 被回复的消息ID
    mentions: List[str] = field(default_factory=list)
    media_url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UnifiedResponse:
    """统一响应格式"""
    content: str
    message_type: MessageType = MessageType.TEXT
    reply_to: Optional[str] = None
    media_path: Optional[str] = None
    buttons: Optional[List[Dict]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class PlatformAdapter(ABC):
    """平台适配器抽象基类 - 每个平台实现一个"""

    def __init__(self, platform_type: PlatformType, config: Dict[str, Any]):
        self.platform_type = platform_type
        self.config = config
        self._connected = False
        self._event_handlers: List[Callable] = []
        self.logger = logging.getLogger(f"{__name__}.{platform_type.value}")

    @property
    def is_connected(self) -> bool:
        return self._connected

    @abstractmethod
    async def connect(self) -> bool:
        """连接到平台"""
        pass

    @abstractmethod
    async def disconnect(self):
        """断开连接"""
        pass

    @abstractmethod
    async def send_message(self, response: UnifiedResponse, chat_id: str) -> bool:
        """发送消息到平台"""
        pass

    @abstractmethod
    async def parse_event(self, raw_event: Dict) -> Optional[UnifiedMessage]:
        """将平台原始事件解析为统一消息格式"""
        pass

    def register_handler(self, handler: Callable):
        """注册事件处理器"""
        self._event_handlers.append(handler)

    async def _dispatch_event(self, message: UnifiedMessage):
        """分发事件到所有注册的处理器"""
        for handler in self._event_handlers:
            try:
                await handler(message) if asyncio.iscoroutinefunction(handler) else handler(message)
            except Exception as e:
                self.logger.error(f"Event handler error: {e}")


class TelegramAdapter(PlatformAdapter):
    """Telegram平台适配器"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(PlatformType.TELEGRAM, config)
        self.bot_token = config.get("bot_token", "")
        self.api_base = f"https://api.telegram.org/bot{self.bot_token}"
        self._offset = 0

    async def connect(self) -> bool:
        import urllib.request
        try:
            url = f"{self.api_base}/getMe"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = __import__("json").loads(resp.read().decode())
                if result.get("ok"):
                    self._connected = True
                    self.logger.info("Telegram bot connected: %s", result["result"]["username"])
                    return True
        except Exception as e:
            self.logger.error(f"Telegram connection failed: {e}")
        return False

    async def disconnect(self):
        self._connected = False

    async def send_message(self, response: UnifiedResponse, chat_id: str) -> bool:
        import urllib.request, urllib.parse
        try:
            payload = {
                "chat_id": chat_id,
                "text": response.content[:4096],
                "parse_mode": "Markdown",
            }
            data = urllib.parse.urlencode(payload).encode()
            url = f"{self.api_base}/sendMessage"
            req = urllib.request.Request(url, data=data)
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = __import__("json").loads(resp.read().decode())
                return result.get("ok", False)
        except Exception as e:
            self.logger.error(f"Telegram send failed: {e}")
            return False

    async def parse_event(self, raw_event: Dict) -> Optional[UnifiedMessage]:
        message = raw_event.get("message", {})
        if not message:
            return None
        chat = message.get("chat", {})
        sender = message.get("from", {})
        return UnifiedMessage(
            message_id=str(message.get("message_id", "")),
            platform=PlatformType.TELEGRAM,
            chat_id=str(chat.get("id", "")),
            sender_id=str(sender.get("id", "")),
            sender_name=sender.get("first_name", ""),
            content=message.get("text", ""),
            raw_event=raw_event,
        )


class FeishuAdapter(PlatformAdapter):
    """飞书平台适配器"""

    def __init__(self, config: Dict[str, Any]):
        super().__init__(PlatformType.FEISHU, config)

    async def connect(self) -> bool:
        self._connected = True
        self.logger.info("Feishu adapter ready")
        return True

    async def disconnect(self):
        self._connected = False

    async def send_message(self, response: UnifiedResponse, chat_id: str) -> bool:
        # 通过 lark-cli 发送
        import subprocess
        try:
            cmd = ["lark-cli", "post", "--chat-id", chat_id, "--content", response.content]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            return result.returncode == 0
        except Exception as e:
            self.logger.error(f"Feishu send failed: {e}")
            return False

    async def parse_event(self, raw_event: Dict) -> Optional[UnifiedMessage]:
        event = raw_event.get("event", {})
        msg = event.get("message", {})
        sender = event.get("sender", {}).get("sender_id", {})
        content = msg.get("content", "{}")
        try:
            import json
            content_obj = json.loads(content)
            text = content_obj.get("text", "")
        except Exception:
            text = content
        return UnifiedMessage(
            message_id=msg.get("message_id", ""),
            platform=PlatformType.FEISHU,
            chat_id=msg.get("chat_id", ""),
            sender_id=sender.get("open_id", ""),
            sender_name="",
            content=text,
            raw_event=raw_event,
        )


class PlatformManager:
    """多平台统一管理器 - 核心路由与调度"""

    def __init__(self):
        self._adapters: Dict[PlatformType, PlatformAdapter] = {}
        self._message_log: List[UnifiedMessage] = []
        self._global_handlers: List[Callable] = []
        self.logger = logging.getLogger(__name__)

    def register_adapter(self, adapter: PlatformAdapter):
        """注册平台适配器"""
        self._adapters[adapter.platform_type] = adapter
        adapter.register_handler(self._on_message)
        self.logger.info("Registered platform: %s", adapter.platform_type.value)

    def _on_message(self, message: UnifiedMessage):
        """全局消息处理"""
        self._message_log.append(message)
        for handler in self._global_handlers:
            try:
                handler(message)
            except Exception as e:
                self.logger.error(f"Global handler error: {e}")

    def register_global_handler(self, handler: Callable):
        """注册全局消息处理器"""
        self._global_handlers.append(handler)

    async def connect_all(self) -> Dict[PlatformType, bool]:
        """连接所有平台"""
        results = {}
        for platform_type, adapter in self._adapters.items():
            results[platform_type] = await adapter.connect()
            self.logger.info("Platform %s: %s", platform_type.value,
                           "connected" if results[platform_type] else "failed")
        return results

    async def disconnect_all(self):
        """断开所有平台"""
        for adapter in self._adapters.values():
            await adapter.disconnect()

    async def broadcast(self, response: UnifiedResponse,
                       chat_ids: Dict[PlatformType, str]) -> Dict[PlatformType, bool]:
        """跨平台广播消息"""
        results = {}
        for platform_type, chat_id in chat_ids.items():
            adapter = self._adapters.get(platform_type)
            if adapter and adapter.is_connected:
                results[platform_type] = await adapter.send_message(response, chat_id)
            else:
                results[platform_type] = False
        return results

    async def send(self, platform: PlatformType, response: UnifiedResponse,
                  chat_id: str) -> bool:
        """发送消息到指定平台"""
        adapter = self._adapters.get(platform)
        if not adapter or not adapter.is_connected:
            self.logger.error("Platform %s not available", platform.value)
            return False
        return await adapter.send_message(response, chat_id)

    def get_adapter(self, platform: PlatformType) -> Optional[PlatformAdapter]:
        """获取指定平台适配器"""
        return self._adapters.get(platform)

    def get_connected_platforms(self) -> List[PlatformType]:
        """获取已连接的平台列表"""
        return [pt for pt, adapter in self._adapters.items() if adapter.is_connected]

    def get_message_history(self, platform: Optional[PlatformType] = None,
                           limit: int = 100) -> List[UnifiedMessage]:
        """获取消息历史"""
        messages = self._message_log
        if platform:
            messages = [m for m in messages if m.platform == platform]
        return messages[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """获取平台统计"""
        return {
            "registered": len(self._adapters),
            "connected": len(self.get_connected_platforms()),
            "total_messages": len(self._message_log),
            "platforms": {
                pt.value: {
                    "connected": adapter.is_connected,
                }
                for pt, adapter in self._adapters.items()
            },
        }
