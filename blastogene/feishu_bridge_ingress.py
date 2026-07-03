"""Feishu/Lark bridge ingress policy for community operations."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal

MessageKind = Literal["dm", "group", "topic", "comment"]
Decision = Literal["accept", "ignore", "invite-required"]

@dataclass(frozen=True)
class BridgeMessage:
    kind: MessageKind
    chat_id: str
    sender_id: str
    text: str
    mentioned_bot: bool = False
    thread_id: str | None = None

@dataclass(frozen=True)
class IngressPolicy:
    owner_id: str
    allowed_users: frozenset[str] = frozenset()
    allowed_chats: frozenset[str] = frozenset()
    admins: frozenset[str] = frozenset()
    require_mention_in_group: bool = True

class FeishuBridgeIngress:
    def decide(self, msg: BridgeMessage, policy: IngressPolicy) -> Decision:
        if msg.sender_id == policy.owner_id or msg.sender_id in policy.admins:
            if msg.kind in {"group", "topic"} and policy.require_mention_in_group and not msg.mentioned_bot:
                return "ignore"
            return "accept"
        if msg.kind == "dm":
            return "accept" if msg.sender_id in policy.allowed_users else "ignore"
        if msg.kind in {"group", "topic"}:
            if msg.chat_id not in policy.allowed_chats:
                return "invite-required" if msg.mentioned_bot else "ignore"
            if policy.require_mention_in_group and not msg.mentioned_bot:
                return "ignore"
            return "accept"
        if msg.kind == "comment":
            return "accept" if msg.mentioned_bot else "ignore"
        return "ignore"
