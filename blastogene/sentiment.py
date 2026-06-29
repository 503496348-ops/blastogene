"""
消息情感分析与敏感词检测模块

基于词典的轻量级中文NLP分析，无ML依赖。

核心能力:
1. 消息情感分析 - 词级情感得分 + 否定词处理 + 程度副词加权
2. 敏感词检测 - Aho-Corasick高效多模匹配
3. 文本预处理 - 中文分词 + 停用词过滤 + 文本清洗
"""

import re
import logging
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger(__name__)


# ============================================================
# Aho-Corasick 多模匹配引擎
# ============================================================

class AhoCorasickNode:
    """Aho-Corasick自动机节点"""
    __slots__ = ['children', 'fail', 'output', 'depth']

    def __init__(self):
        self.children: Dict[str, 'AhoCorasickNode'] = {}
        self.fail: Optional['AhoCorasickNode'] = None
        self.output: List[str] = []
        self.depth: int = 0


class AhoCorasick:
    """
    Aho-Corasick多模式匹配算法

    用于高效地在文本中同时搜索多个敏感词。
    时间复杂度: O(n + m + z)，n=文本长度，m=模式总长度，z=匹配数

    无外部依赖，纯Python实现。
    """

    def __init__(self):
        self.root = AhoCorasickNode()
        self._built = False

    def add_word(self, word: str, category: str = ""):
        """添加模式词"""
        if not word:
            return
        node = self.root
        for char in word:
            if char not in node.children:
                node.children[char] = AhoCorasickNode()
                node.children[char].depth = node.depth + 1
            node = node.children[char]
        tag = category if category else word
        if tag not in node.output:
            node.output.append(tag)
        self._built = False

    def build(self):
        """构建失败指针（BFS）"""
        queue = deque()
        # 第一层子节点的fail指向root
        for child in self.root.children.values():
            child.fail = self.root
            queue.append(child)

        while queue:
            current = queue.popleft()
            for char, child in current.children.items():
                queue.append(child)
                fail_node = current.fail
                while fail_node and char not in fail_node.children:
                    fail_node = fail_node.fail
                child.fail = fail_node.children[char] if fail_node and char in fail_node.children else self.root
                if child.fail == child:
                    child.fail = self.root
                child.output = child.output + child.fail.output

        self._built = True

    def search(self, text: str) -> List[Tuple[int, str]]:
        """
        搜索文本中的所有匹配

        Returns:
            [(结束位置, 匹配词/类别), ...]
        """
        if not self._built:
            self.build()

        results = []
        node = self.root
        for i, char in enumerate(text):
            while node and char not in node.children:
                node = node.fail
            if not node:
                node = self.root
                continue
            node = node.children[char]
            for pattern in node.output:
                results.append((i, pattern))
        return results

    @property
    def pattern_count(self) -> int:
        """已添加的模式数量"""
        count = 0
        queue = deque([self.root])
        while queue:
            node = queue.popleft()
            count += len(node.output)
            for child in node.children.values():
                queue.append(child)
        return count


# ============================================================
# 情感分析引擎
# ============================================================

class SentimentLevel(str, Enum):
    """情感等级"""
    VERY_NEGATIVE = "very_negative"  # 很负面 [-1, -0.6)
    NEGATIVE = "negative"           # 负面 [-0.6, -0.2)
    NEUTRAL = "neutral"             # 中性 [-0.2, 0.2)
    POSITIVE = "positive"           # 正面 [0.2, 0.6)
    VERY_POSITIVE = "very_positive" # 很正面 [0.6, 1]


@dataclass
class SentimentResult:
    """情感分析结果"""
    score: float                    # 情感得分 [-1, 1]
    level: SentimentLevel           # 情感等级
    positive_words: List[str]       # 正面词
    negative_words: List[str]       # 负面词
    negation_count: int             # 否定词数量
    confidence: float               # 置信度 [0, 1]

    def to_dict(self) -> Dict:
        return {
            'score': round(self.score, 3),
            'level': self.level.value,
            'positive_words': self.positive_words,
            'negative_words': self.negative_words,
            'negation_count': self.negation_count,
            'confidence': round(self.confidence, 3)
        }


@dataclass
class SensitiveWordMatch:
    """敏感词匹配结果"""
    word: str           # 匹配的词
    category: str       # 类别
    position: int       # 位置
    context: str        # 上下文

    def to_dict(self) -> Dict:
        return {
            'word': self.word,
            'category': self.category,
            'position': self.position,
            'context': self.context
        }


@dataclass
class AnalysisResult:
    """综合分析结果"""
    sentiment: SentimentResult
    sensitive_words: List[SensitiveWordMatch]
    keywords: List[str]
    message_length: int
    has_links: bool
    has_mention: bool
    has_image: bool

    def to_dict(self) -> Dict:
        return {
            'sentiment': self.sentiment.to_dict(),
            'sensitive_words': [sw.to_dict() for sw in self.sensitive_words],
            'keywords': self.keywords,
            'message_length': self.message_length,
            'has_links': self.has_links,
            'has_mention': self.has_mention,
            'has_image': self.has_image,
            'risk_level': self._risk_level()
        }

    def _risk_level(self) -> str:
        """计算风险等级"""
        if len(self.sensitive_words) >= 3:
            return 'critical'
        if len(self.sensitive_words) >= 1:
            return 'warning'
        if self.sentiment.level in (SentimentLevel.VERY_NEGATIVE,):
            return 'warning'
        return 'normal'


# ============================================================
# 内置词典（轻量版，无外部文件依赖）
# ============================================================

# 情感词典 - 正面词 (word: score)
POSITIVE_LEXICON = {
    # 强正面 (0.6-1.0)
    '优秀': 0.9, '出色': 0.85, '卓越': 0.9, '精彩': 0.85, '完美': 0.95,
    '厉害': 0.8, '强大': 0.8, '棒': 0.75, '好': 0.6, '赞': 0.7,
    '感谢': 0.7, '谢谢': 0.65, '支持': 0.6, '喜欢': 0.7, '开心': 0.75,
    '高兴': 0.7, '满意': 0.7, '推荐': 0.65, '专业': 0.7, '高效': 0.75,
    '创新': 0.7, '突破': 0.7, '进步': 0.65, '成功': 0.75, '解决': 0.6,
    '有用': 0.6, '方便': 0.6, '快速': 0.6, '稳定': 0.6, '可靠': 0.65,
    # 中等正面 (0.3-0.6)
    '不错': 0.5, '可以': 0.4, '还行': 0.3, '挺好': 0.5, '加油': 0.5,
    '期待': 0.5, '欢迎': 0.5, '分享': 0.4, '学习': 0.4, '交流': 0.4,
    '合作': 0.5, '共创': 0.5, '成长': 0.5, '价值': 0.5, '优化': 0.5,
}

# 情感词典 - 负面词 (word: abs_score)
NEGATIVE_LEXICON = {
    # 强负面 (0.6-1.0)
    '垃圾': 0.9, '骗子': 0.95, '骗人': 0.9, '诈骗': 0.95, '恶心': 0.85,
    '废物': 0.85, '白痴': 0.9, '傻逼': 0.95, '滚': 0.8, '去死': 0.95,
    '垃圾': 0.9, '坑人': 0.85, '黑心': 0.85, '无耻': 0.85, '可恶': 0.8,
    '愤怒': 0.75, '失望': 0.7, '糟糕': 0.75, '可怕': 0.7, '恐怖': 0.75,
    # 中等负面 (0.3-0.6)
    '差': 0.5, '烂': 0.6, '慢': 0.4, '贵': 0.4, '难': 0.4,
    '问题': 0.3, '错误': 0.5, '失败': 0.6, 'bug': 0.5, '崩溃': 0.6,
    '卡顿': 0.5, '延迟': 0.4, '故障': 0.5, '投诉': 0.5, '不满': 0.5,
    '无聊': 0.4, '烦': 0.5, '累': 0.3, '难用': 0.5, '复杂': 0.3,
}

# 否定词典
NEGATION_WORDS = {
    '不', '没', '没有', '不是', '非', '未', '无', '别', '莫', '勿',
    '不要', '不能', '不会', '不该', '不可', '不必', '未曾', '未必',
    '绝非', '并非', '从未', '尚未', '毫无', '毫无', '切勿',
}

# 程度副词典 (word: multiplier)
DEGREE_WORDS = {
    '非常': 2.0, '极其': 2.5, '特别': 2.0, '格外': 2.0, '十分': 2.0,
    '万分': 2.5, '极其': 2.5, '相当': 1.8, '很': 1.5, '太': 1.8,
    '超': 1.8, '超级': 2.0, '巨': 1.8, '贼': 1.8, '老': 1.5,
    '挺': 1.3, '较': 1.2, '比较': 1.3, '稍微': 0.7, '略': 0.7,
    '有点': 0.8, '有些': 0.8, '一点': 0.7, '略微': 0.7,
}

# 敏感词分类词典
SENSITIVE_WORD_CATEGORIES = {
    'spam': {
        '广告', '刷单', '兼职', '赚钱', '加微信', '加我', '免费领',
        '优惠券', '返利', '薅羊毛', '日赚', '月入', '躺赚', '暴富',
        '代理', '分销', '招商', '加盟', '贷款', '套现', '信用卡代还',
    },
    'scam': {
        '诈骗', '骗子', '骗人', '传销', '资金盘', '庞氏', '割韭菜',
        '杀猪盘', '刷单诈骗', '投资诈骗', '网络诈骗', '非法集资',
    },
    'inappropriate': {
        '色情', '裸聊', '约炮', '成人', '黄片', '黄色', '性爱',
        '赌博', '博彩', '赌球', '网赌', '老虎机', '百家乐',
    },
    'harassment': {
        '傻逼', '去死', '滚', '废物', '白痴', '智障', '脑残',
        '贱人', '婊子', '狗', '猪', '垃圾人',
    },
}

# 停用词
STOP_WORDS = {
    '的', '了', '在', '是', '我', '有', '和', '就', '不', '人',
    '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去',
    '你', '会', '着', '没有', '看', '好', '自己', '这', '他', '她',
    '它', '们', '那', '些', '吗', '吧', '啊', '呢', '哈', '呀',
    '哦', '嗯', '呃', '额', '这个', '那个', '什么', '怎么', '为什么',
    '可以', '可能', '应该', '已经', '还是', '或者', '但是', '然后',
    '因为', '所以', '如果', '虽然', '不过', '而且', '并且', '以及',
}


# ============================================================
# 中文分词器（无jieba依赖版）
# ============================================================

class SimpleTokenizer:
    """
    简易中文分词器

    基于正则+最长匹配的轻量分词，无外部依赖。
    对于更精确的分词，可选安装jieba。
    """

    def __init__(self, user_dict: Optional[Set[str]] = None):
        self.user_dict = user_dict or set()
        self._try_jieba = True
        self._jieba = None

    def _load_jieba(self):
        """尝试加载jieba"""
        if self._try_jieba:
            try:
                import jieba as _jieba
                _jieba.setLogLevel(logging.WARNING)
                for word in self.user_dict:
                    _jieba.add_word(word)
                self._jieba = _jieba
            except ImportError:
                self._jieba = None
            self._try_jieba = False

    def tokenize(self, text: str) -> List[str]:
        """分词"""
        self._load_jieba()

        if self._jieba:
            return list(self._jieba.cut(text))

        # 回退：正则分词
        # 英文单词 + 中文字符 + 数字
        tokens = re.findall(r'[a-zA-Z]+|[0-9]+|[\u4e00-\u9fff]', text)
        # 合并连续中文字符为2-4字词（简单最长匹配）
        result = []
        i = 0
        while i < len(tokens):
            if re.match(r'[\u4e00-\u9fff]', tokens[i]):
                # 尝试匹配用户词典中的长词
                matched = False
                for length in range(min(4, len(tokens) - i), 1, -1):
                    candidate = ''.join(tokens[i:i+length])
                    if candidate in self.user_dict:
                        result.append(candidate)
                        i += length
                        matched = True
                        break
                if not matched:
                    result.append(tokens[i])
                    i += 1
            else:
                result.append(tokens[i])
                i += 1
        return result


# ============================================================
# 消息分析器
# ============================================================

class MessageAnalyzer:
    """
    消息综合分析器

    提供情感分析、敏感词检测、关键词提取、文本特征提取等能力。

    Usage:
        analyzer = MessageAnalyzer()
        result = analyzer.analyze("这个产品太棒了！非常推荐！")
        print(result.sentiment.score)  # 0.85
        print(result.sentiment.level)  # SentimentLevel.VERY_POSITIVE
    """

    def __init__(
        self,
        custom_sensitive_words: Optional[Dict[str, Set[str]]] = None,
        custom_positive_words: Optional[Dict[str, float]] = None,
        custom_negative_words: Optional[Dict[str, float]] = None,
        user_dict: Optional[Set[str]] = None,
    ):
        """
        初始化分析器

        Args:
            custom_sensitive_words: 自定义敏感词 {类别: {词集合}}
            custom_positive_words: 自定义正面词 {词: 得分}
            custom_negative_words: 自定义负面词 {词: 绝对值}
            user_dict: 自定义分词词典
        """
        # 合并词典
        self.positive_lexicon = {**POSITIVE_LEXICON}
        if custom_positive_words:
            self.positive_lexicon.update(custom_positive_words)

        self.negative_lexicon = {**NEGATIVE_LEXICON}
        if custom_negative_words:
            self.negative_lexicon.update(custom_negative_words)

        # 构建Aho-Corasick敏感词检测器
        self.ac = AhoCorasick()
        all_sensitive = {}
        for category, words in SENSITIVE_WORD_CATEGORIES.items():
            all_sensitive[category] = words
        if custom_sensitive_words:
            for category, words in custom_sensitive_words.items():
                if category in all_sensitive:
                    all_sensitive[category] = all_sensitive[category] | words
                else:
                    all_sensitive[category] = words

        for category, words in all_sensitive.items():
            for word in words:
                self.ac.add_word(word, category)
        self.ac.build()

        # 分词器
        all_user_dict = set(self.positive_lexicon.keys()) | set(self.negative_lexicon.keys())
        if user_dict:
            all_user_dict |= user_dict
        self.tokenizer = SimpleTokenizer(user_dict=all_user_dict)

        # URL/mention/图片检测正则
        self._url_pattern = re.compile(r'https?://\S+|www\.\S+')
        self._mention_pattern = re.compile(r'@\w+')
        self._image_pattern = re.compile(r'\[图片\]|\[image\]|!\[.*?\]\(.*?\)')

    def analyze(self, text: str) -> AnalysisResult:
        """
        综合分析消息

        Args:
            text: 消息文本

        Returns:
            AnalysisResult: 综合分析结果
        """
        if not text or not text.strip():
            return AnalysisResult(
                sentiment=SentimentResult(
                    score=0.0, level=SentimentLevel.NEUTRAL,
                    positive_words=[], negative_words=[],
                    negation_count=0, confidence=0.0
                ),
                sensitive_words=[], keywords=[], message_length=0,
                has_links=False, has_mention=False, has_image=False
            )

        # 1. 情感分析
        sentiment = self._analyze_sentiment(text)

        # 2. 敏感词检测
        sensitive_words = self._detect_sensitive(text)

        # 3. 关键词提取
        keywords = self._extract_keywords(text)

        # 4. 文本特征
        has_links = bool(self._url_pattern.search(text))
        has_mention = bool(self._mention_pattern.search(text))
        has_image = bool(self._image_pattern.search(text))

        return AnalysisResult(
            sentiment=sentiment,
            sensitive_words=sensitive_words,
            keywords=keywords,
            message_length=len(text),
            has_links=has_links,
            has_mention=has_mention,
            has_image=has_image
        )

    def _analyze_sentiment(self, text: str) -> SentimentResult:
        """情感分析"""
        tokens = self.tokenizer.tokenize(text)
        # 过滤停用词
        tokens = [t for t in tokens if t not in STOP_WORDS and len(t.strip()) > 0]

        positive_words = []
        negative_words = []
        negation_count = 0
        total_score = 0.0
        scored_count = 0

        i = 0
        while i < len(tokens):
            token = tokens[i]

            # 检查否定词
            if token in NEGATION_WORDS:
                negation_count += 1
                i += 1
                continue

            # 检查程度副词
            degree = 1.0
            if token in DEGREE_WORDS:
                degree = DEGREE_WORDS[token]
                i += 1
                if i >= len(tokens):
                    break
                token = tokens[i]

            # 检查正面词
            if token in self.positive_lexicon:
                score = self.positive_lexicon[token] * degree
                # 检查前面是否有否定词（窗口：前3个词）
                window_start = max(0, i - 3)
                has_negation = any(
                    t in NEGATION_WORDS for t in tokens[window_start:i]
                )
                if has_negation:
                    score = -score * 0.7  # 否定后变为负面，但强度减弱
                    negative_words.append(f"不{token}")
                else:
                    positive_words.append(token)
                total_score += score
                scored_count += 1

            # 检查负面词
            elif token in self.negative_lexicon:
                score = self.negative_lexicon[token] * degree
                window_start = max(0, i - 3)
                has_negation = any(
                    t in NEGATION_WORDS for t in tokens[window_start:i]
                )
                if has_negation:
                    score = score * 0.5  # 否定后减弱但仍偏负面
                    positive_words.append(f"不{token}")
                else:
                    negative_words.append(token)
                total_score -= score
                scored_count += 1

            i += 1

        # 计算最终得分
        if scored_count > 0:
            avg_score = total_score / scored_count
            # sigmoid-like归一化到[-1, 1]
            score = max(-1.0, min(1.0, avg_score))
            confidence = min(1.0, scored_count / max(len(tokens), 1) * 2)
        else:
            score = 0.0
            confidence = 0.0

        # 确定情感等级
        if score < -0.6:
            level = SentimentLevel.VERY_NEGATIVE
        elif score < -0.2:
            level = SentimentLevel.NEGATIVE
        elif score < 0.2:
            level = SentimentLevel.NEUTRAL
        elif score < 0.6:
            level = SentimentLevel.POSITIVE
        else:
            level = SentimentLevel.VERY_POSITIVE

        return SentimentResult(
            score=score,
            level=level,
            positive_words=positive_words,
            negative_words=negative_words,
            negation_count=negation_count,
            confidence=confidence
        )

    def _detect_sensitive(self, text: str) -> List[SensitiveWordMatch]:
        """敏感词检测"""
        matches = self.ac.search(text)
        results = []
        seen = set()

        for position, pattern in matches:
            if pattern in seen:
                continue
            seen.add(pattern)

            # 提取上下文
            start = max(0, position - 10)
            end = min(len(text), position + 10)
            context = text[start:end]

            # 从pattern中提取类别（pattern格式为"类别"或"词"）
            category = pattern
            for cat, words in SENSITIVE_WORD_CATEGORIES.items():
                if pattern in words or pattern == cat:
                    category = cat
                    break

            results.append(SensitiveWordMatch(
                word=pattern,
                category=category,
                position=position,
                context=context
            ))

        return results

    def _extract_keywords(self, text: str, top_k: int = 5) -> List[str]:
        """提取关键词（基于TF的简易版本）"""
        tokens = self.tokenizer.tokenize(text)
        # 过滤停用词和单字
        tokens = [t for t in tokens if t not in STOP_WORDS and len(t) > 1]
        # 统计词频
        from collections import Counter
        counter = Counter(tokens)
        return [word for word, _ in counter.most_common(top_k)]

    def add_sensitive_words(self, words: Set[str], category: str = "custom"):
        """动态添加敏感词"""
        for word in words:
            self.ac.add_word(word, category)
        self.ac._built = False  # 需要重建

    def get_stats(self) -> Dict:
        """获取分析器统计信息"""
        return {
            'positive_lexicon_size': len(self.positive_lexicon),
            'negative_lexicon_size': len(self.negative_lexicon),
            'negation_words_size': len(NEGATION_WORDS),
            'degree_words_size': len(DEGREE_WORDS),
            'sensitive_patterns': self.ac.pattern_count,
        }


# ============================================================
# 便捷函数
# ============================================================

_default_analyzer: Optional[MessageAnalyzer] = None


def get_analyzer(**kwargs) -> MessageAnalyzer:
    """获取默认分析器（单例）"""
    global _default_analyzer
    if _default_analyzer is None:
        _default_analyzer = MessageAnalyzer(**kwargs)
    return _default_analyzer


def analyze_message(text: str, **kwargs) -> AnalysisResult:
    """便捷函数：分析消息"""
    return get_analyzer(**kwargs).analyze(text)


def detect_sensitive(text: str, **kwargs) -> List[SensitiveWordMatch]:
    """便捷函数：检测敏感词"""
    return get_analyzer(**kwargs)._detect_sensitive(text)


def analyze_sentiment(text: str, **kwargs) -> SentimentResult:
    """便捷函数：情感分析"""
    return get_analyzer(**kwargs)._analyze_sentiment(text)
