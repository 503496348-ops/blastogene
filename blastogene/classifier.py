
"""
消息分类模块

核心能力：
- 消息类型分类（咨询/投诉/闲聊/广告/敏感）
- 关键词权重分类
- 正则规则匹配
- 统计特征分类（长度/符号/emoji密度）
- 分类结果缓存与统计
"""

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


logger = logging.getLogger(__name__)


class Category(Enum):
    """消息分类"""
    INQUIRY = "inquiry"           # 咨询提问
    COMPLAINT = "complaint"       # 投诉抱怨
    CHITCHAT = "chitchat"         # 闲聊社交
    ADVERTISEMENT = "ad"          # 广告推广
    SENSITIVE = "sensitive"       # 敏感内容
    COMMAND = "command"           # 命令指令
    FEEDBACK = "feedback"         # 反馈建议
    GREETING = "greeting"         # 打招呼
    UNKNOWN = "unknown"


@dataclass
class ClassificationResult:
    """分类结果"""
    category: Category
    confidence: float             # 0.0 - 1.0
    sub_category: Optional[str] = None
    features: Dict[str, Any] = field(default_factory=dict)
    method: str = "keyword"       # keyword/rule/statistic/ensemble

    def to_dict(self) -> Dict:
        return {
            "category": self.category.value,
            "confidence": round(self.confidence, 3),
            "sub_category": self.sub_category,
            "method": self.method,
            "features": self.features,
        }


@dataclass
class KeywordRule:
    """关键词规则"""
    keywords: List[str]
    category: Category
    weight: float = 1.0
    case_sensitive: bool = False

    def match(self, text: str) -> Tuple[bool, float]:
        check_text = text if self.case_sensitive else text.lower()
        matches = sum(1 for kw in self.keywords
                     if (kw if self.case_sensitive else kw.lower()) in check_text)
        if matches > 0:
            score = min(matches / len(self.keywords), 1.0) * self.weight
            return True, score
        return False, 0.0


@dataclass
class RegexRule:
    """正则规则"""
    pattern: str
    category: Category
    weight: float = 1.0
    description: str = ""

    def __post_init__(self):
        self._compiled = re.compile(self.pattern, re.IGNORECASE | re.MULTILINE)

    def match(self, text: str) -> Tuple[bool, float]:
        matches = self._compiled.findall(text)
        if matches:
            score = min(len(matches) / 3.0, 1.0) * self.weight
            return True, score
        return False, 0.0


class MessageClassifier:
    """消息分类器 - 多策略融合"""

    def __init__(self):
        self._keyword_rules: List[KeywordRule] = []
        self._regex_rules: List[RegexRule] = []
        self._stats: Dict[str, int] = defaultdict(int)
        self._cache: Dict[str, ClassificationResult] = {}
        self._cache_max = 1000

        # 初始化默认规则
        self._init_default_rules()

    def _init_default_rules(self):
        """初始化默认分类规则"""
        # 咨询类关键词
        self.add_keyword_rule(
            keywords=["怎么", "如何", "为什么", "什么", "哪里", "请问", "咨询",
                      "了解", "价格", "费用", "多少钱", "怎么用", "教程"],
            category=Category.INQUIRY, weight=1.0,
        )
        # 投诉类关键词
        self.add_keyword_rule(
            keywords=["投诉", "不满", "差评", "垃圾", "骗", "退款", "举报",
                      "太差", "坑", "骗子", "无语", "失望"],
            category=Category.COMPLAINT, weight=1.2,
        )
        # 广告类关键词
        self.add_keyword_rule(
            keywords=["优惠", "促销", "打折", "免费领", "扫码", "加微信",
                      "代理", "兼职", "赚钱", "日入", "月入"],
            category=Category.ADVERTISEMENT, weight=1.1,
        )
        # 命令类关键词
        self.add_keyword_rule(
            keywords=["/help", "/start", "/menu", "/status", "/config",
                      "帮助", "菜单", "功能"],
            category=Category.COMMAND, weight=1.5,
        )
        # 打招呼
        self.add_keyword_rule(
            keywords=["你好", "hi", "hello", "嗨", "早上好", "晚上好",
                      "在吗", "在不在"],
            category=Category.GREETING, weight=1.3,
        )

        # 正则规则
        self.add_regex_rule(
            pattern=r"(https?://|www\.|\.com|\.cn|点击|链接)",
            category=Category.ADVERTISEMENT, weight=0.8,
            description="URL/链接检测",
        )
        self.add_regex_rule(
            pattern=r"[!！]{2,}|[?？]{3,}|[。]{3,}",
            category=Category.COMPLAINT, weight=0.5,
            description="情绪符号检测",
        )

    def add_keyword_rule(self, keywords: List[str], category: Category,
                        weight: float = 1.0, case_sensitive: bool = False):
        """添加关键词规则"""
        self._keyword_rules.append(KeywordRule(
            keywords=keywords, category=category,
            weight=weight, case_sensitive=case_sensitive,
        ))

    def add_regex_rule(self, pattern: str, category: Category,
                      weight: float = 1.0, description: str = ""):
        """添加正则规则"""
        self._regex_rules.append(RegexRule(
            pattern=pattern, category=category,
            weight=weight, description=description,
        ))

    def classify(self, text: str, use_cache: bool = True) -> ClassificationResult:
        """分类消息"""
        if not text or not text.strip():
            return ClassificationResult(category=Category.UNKNOWN, confidence=0.0)

        # 缓存检查
        cache_key = text[:100]
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key]

        # 多策略分类
        scores: Dict[Category, float] = defaultdict(float)
        features: Dict[str, Any] = {"text_length": len(text)}

        # 1. 关键词匹配
        for rule in self._keyword_rules:
            matched, score = rule.match(text)
            if matched:
                scores[rule.category] += score
                features[f"kw_{rule.category.value}"] = True

        # 2. 正则匹配
        for rule in self._regex_rules:
            matched, score = rule.match(text)
            if matched:
                scores[rule.category] += score
                features[f"rx_{rule.category.value}"] = True

        # 3. 统计特征
        stat_category, stat_score = self._statistical_classify(text)
        if stat_category != Category.UNKNOWN:
            scores[stat_category] += stat_score * 0.3  # 统计特征权重较低
            features["stat_category"] = stat_category.value

        # 选择最高分
        if not scores:
            result = ClassificationResult(
                category=Category.CHITCHAT, confidence=0.3,
                features=features, method="default",
            )
        else:
            best_category = max(scores, key=scores.get)
            total_score = sum(scores.values())
            confidence = scores[best_category] / total_score if total_score > 0 else 0
            result = ClassificationResult(
                category=best_category,
                confidence=min(confidence, 1.0),
                features=features,
                method="ensemble",
            )

        # 更新统计
        self._stats[result.category.value] += 1

        # 缓存
        if use_cache:
            if len(self._cache) >= self._cache_max:
                # 清理旧缓存
                keys = list(self._cache.keys())
                for k in keys[:len(keys) // 2]:
                    del self._cache[k]
            self._cache[cache_key] = result

        return result

    def _statistical_classify(self, text: str) -> Tuple[Category, float]:
        """基于统计特征的分类"""
        length = len(text)
        exclamation = text.count("!") + text.count("！")
        question = text.count("?") + text.count("？")
        emoji_count = len(re.findall(r"[😀-🙏]", text))
        url_count = len(re.findall(r"https?://", text))

        # 短文本+问号 → 咨询
        if length < 50 and question > 0:
            return Category.INQUIRY, 0.6

        # 多感叹号 → 投诉
        if exclamation >= 3:
            return Category.COMPLAINT, 0.5

        # 含URL → 广告
        if url_count > 0:
            return Category.ADVERTISEMENT, 0.4

        # 超短文本 → 打招呼
        if length < 10:
            return Category.GREETING, 0.5

        return Category.UNKNOWN, 0.0

    def get_stats(self) -> Dict[str, Any]:
        """获取分类统计"""
        total = sum(self._stats.values())
        return {
            "total_classified": total,
            "category_distribution": dict(self._stats),
            "rules_count": {
                "keyword": len(self._keyword_rules),
                "regex": len(self._regex_rules),
            },
            "cache_size": len(self._cache),
        }

    def reset_stats(self):
        """重置统计"""
        self._stats.clear()
