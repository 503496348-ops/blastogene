"""Generic notification cards for orchestration events."""
from __future__ import annotations

from urllib.parse import urlparse

ALLOWED_DETAIL_SCHEMES = {"https"}


def validate_detail_url(url: str | None) -> bool:
    if not url:
        return True
    parsed = urlparse(url)
    return parsed.scheme in ALLOWED_DETAIL_SCHEMES and bool(parsed.netloc)


def build_community_ops_alert_card(title: str, status: str, content: str, detail_url: str | None = None) -> dict:
    if not validate_detail_url(detail_url):
        raise ValueError("detail_url must be an absolute https URL")
    elements = [{"tag": "div", "text": {"tag": "lark_md", "content": content}}]
    if detail_url:
        elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": "查看详情"},
                "url": detail_url,
                "type": "primary",
            }],
        })
    return {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": title}, "template": _template_for_status(status)},
            "elements": elements,
        },
    }


def _template_for_status(status: str) -> str:
    return {
        "healthy": "green",
        "degraded": "yellow",
        "attention_required": "red",
        "completed": "green",
    }.get(status, "blue")
