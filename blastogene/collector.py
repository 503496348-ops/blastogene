"""
事件收集器 - 飞书Webhook事件接收与处理

接收飞书推送的群消息事件，解析后存储到SQLite
"""

import json
import hashlib
import logging
from datetime import datetime
from typing import Dict, Any, Optional, Callable
from flask import Flask, request, jsonify
from dataclasses import dataclass

from .storage import MessageStore, Message

logger = logging.getLogger(__name__)


@dataclass
class EventConfig:
    """事件配置"""
    verify_token: str = ""
    encrypt_key: str = ""
    port: int = 8080
    host: str = "0.0.0.0"
    debug: bool = False


class EventCollector:
    """飞书事件收集器"""
    
    def __init__(
        self,
        store: MessageStore,
        config: Optional[EventConfig] = None,
        on_message: Optional[Callable[[Message], None]] = None
    ):
        """
        初始化事件收集器
        
        Args:
            store: 消息存储实例
            config: 事件配置
            on_message: 消息回调函数
        """
        self.store = store
        self.config = config or EventConfig()
        self.on_message = on_message
        
        self.app = Flask(__name__)
        self._setup_routes()
        
        # 统计
        self.stats = {
            'received': 0,
            'stored': 0,
            'skipped': 0,
            'errors': 0,
            'last_event_time': None
        }
    
    def _setup_routes(self):
        """设置路由"""
        
        @self.app.route('/webhook/event', methods=['POST'])
        def handle_event():
            """处理飞书事件回调"""
            try:
                data = request.get_json()
                
                # 验证请求
                if not self._verify_request(data):
                    return jsonify({'code': 403, 'msg': 'Invalid request'}), 403
                
                # 处理URL验证（首次配置回调时飞书会发送）
                if data.get('type') == 'url_verification':
                    return jsonify({'challenge': data.get('challenge')})
                
                # 处理事件
                event = data.get('event', {})
                event_type = event.get('type')
                
                if event_type == 'message':
                    self._handle_message_event(event)
                elif event_type == 'im.message.receive_v1':
                    self._handle_message_event_v1(event)
                else:
                    logger.info(f"Unhandled event type: {event_type}")
                
                return jsonify({'code': 0, 'msg': 'success'})
                
            except Exception as e:
                logger.error(f"Error handling event: {e}")
                self.stats['errors'] += 1
                return jsonify({'code': 500, 'msg': str(e)}), 500
        
        @self.app.route('/webhook/health', methods=['GET'])
        def health_check():
            """健康检查"""
            return jsonify({
                'status': 'healthy',
                'stats': self.stats,
                'db_stats': self.store.get_database_stats()
            })
        
        @self.app.route('/webhook/stats', methods=['GET'])
        def get_stats():
            """获取统计信息"""
            return jsonify(self.stats)
    
    def _verify_request(self, data: Dict) -> bool:
        """
        验证请求合法性
        
        简化验证：检查token是否匹配
        生产环境应实现完整的签名验证
        """
        if not self.config.verify_token:
            return True  # 未配置token则跳过验证
        
        token = data.get('token') or data.get('header', {}).get('token')
        return token == self.config.verify_token
    
    def _handle_message_event(self, event: Dict):
        """处理消息事件（v1格式）"""
        self.stats['received'] += 1
        self.stats['last_event_time'] = datetime.now().isoformat()
        
        try:
            # 提取消息信息
            message_data = event.get('message', {})
            sender_data = event.get('sender', {})
            
            # 生成消息ID（如果不存在）
            message_id = message_data.get('message_id')
            if not message_id:
                # 使用内容hash作为ID
                content_str = json.dumps(message_data, sort_keys=True)
                message_id = hashlib.md5(content_str.encode()).hexdigest()
            
            # 解析内容
            content = message_data.get('content', '')
            content_type = message_data.get('message_type', 'text')
            
            # 尝试解析JSON内容
            if content_type == 'text' and content:
                try:
                    content_json = json.loads(content)
                    content = content_json.get('text', content)
                except json.JSONDecodeError:
                    pass
            
            # 创建消息对象
            message = Message(
                message_id=message_id,
                chat_id=message_data.get('chat_id', ''),
                chat_type=message_data.get('chat_type', 'group'),
                sender_id=sender_data.get('sender_id', {}).get('open_id', ''),
                sender_type=sender_data.get('sender_type', 'user'),
                content=content,
                content_type=content_type,
                timestamp=datetime.fromtimestamp(
                    int(message_data.get('create_time', datetime.now().timestamp() * 1000)) / 1000
                ),
                raw_event=event
            )
            
            # 存储消息
            stored = self.store.store_message(message)
            
            if stored:
                self.stats['stored'] += 1
                logger.info(f"Stored message: {message_id}")
                
                # 调用回调
                if self.on_message:
                    self.on_message(message)
            else:
                self.stats['skipped'] += 1
                logger.debug(f"Skipped duplicate message: {message_id}")
                
        except Exception as e:
            logger.error(f"Error handling message event: {e}")
            self.stats['errors'] += 1
    
    def _handle_message_event_v1(self, event: Dict):
        """处理消息事件（v2格式）"""
        self.stats['received'] += 1
        self.stats['last_event_time'] = datetime.now().isoformat()
        
        try:
            # v2格式的消息体
            message = event.get('message', {})
            sender = event.get('sender', {})
            
            message_id = message.get('message_id')
            if not message_id:
                content_str = json.dumps(message, sort_keys=True)
                message_id = hashlib.md5(content_str.encode()).hexdigest()
            
            # 解析内容
            content = message.get('content', '')
            content_type = message.get('message_type', 'text')
            
            if content_type == 'text' and content:
                try:
                    content_json = json.loads(content)
                    content = content_json.get('text', content)
                except json.JSONDecodeError:
                    pass
            
            # 创建消息对象
            msg = Message(
                message_id=message_id,
                chat_id=message.get('chat_id', ''),
                chat_type=message.get('chat_type', 'group'),
                sender_id=sender.get('sender_id', {}).get('open_id', ''),
                sender_type=sender.get('sender_type', 'user'),
                content=content,
                content_type=content_type,
                timestamp=datetime.fromtimestamp(
                    int(message.get('create_time', datetime.now().timestamp() * 1000)) / 1000
                ),
                raw_event=event
            )
            
            # 存储消息
            stored = self.store.store_message(msg)
            
            if stored:
                self.stats['stored'] += 1
                logger.info(f"Stored message: {message_id}")
                
                if self.on_message:
                    self.on_message(msg)
            else:
                self.stats['skipped'] += 1
                logger.debug(f"Skipped duplicate message: {message_id}")
                
        except Exception as e:
            logger.error(f"Error handling message event v1: {e}")
            self.stats['errors'] += 1
    
    def start(self, blocking: bool = True):
        """
        启动事件收集器
        
        Args:
            blocking: 是否阻塞运行
        """
        logger.info(f"Starting event collector on {self.config.host}:{self.config.port}")
        
        if blocking:
            self.app.run(
                host=self.config.host,
                port=self.config.port,
                debug=self.config.debug
            )
        else:
            # 非阻塞模式（用于测试）
            import threading
            thread = threading.Thread(
                target=self.app.run,
                kwargs={
                    'host': self.config.host,
                    'port': self.config.port,
                    'debug': False
                }
            )
            thread.daemon = True
            thread.start()
            return thread
    
    def stop(self):
        """停止事件收集器"""
        # Flask没有内置的停止方法
        # 在生产环境中，应使用WSGI服务器（如gunicorn）并实现优雅关闭
        logger.info("Event collector stopping...")


def create_collector(
    db_path: str = None,
    verify_token: str = "",
    port: int = 8080,
    on_message: Optional[Callable[[Message], None]] = None
) -> EventCollector:
    """
    创建事件收集器实例
    
    Args:
        db_path: 数据库路径
        verify_token: 验证token
        port: 监听端口
        on_message: 消息回调函数
    
    Returns:
        EventCollector实例
    """
    store = MessageStore(db_path)
    config = EventConfig(
        verify_token=verify_token,
        port=port
    )
    return EventCollector(store, config, on_message)


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Blastogene Event Collector')
    parser.add_argument('--port', type=int, default=8080, help='Listen port')
    parser.add_argument('--host', default='0.0.0.0', help='Listen host')
    parser.add_argument('--db', default=None, help='Database path')
    parser.add_argument('--token', default='', help='Verify token')
    parser.add_argument('--debug', action='store_true', help='Debug mode')
    
    args = parser.parse_args()
    
    # 配置日志
    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 创建并启动收集器
    collector = create_collector(
        db_path=args.db,
        verify_token=args.token,
        port=args.port,
        on_message=lambda msg: logger.info(f"New message from {msg.sender_id}: {msg.content[:50]}...")
    )
    
    collector.config.host = args.host
    collector.config.debug = args.debug
    
    print(f"Starting Blastogene Event Collector on {args.host}:{args.port}")
    collector.start(blocking=True)
