"""
因子检索工具（SearchFactorTool）

功能概述：
    在本地 factor 库中检索与查询关键词最相似的 alpha 因子。
    默认使用 scikit-learn 的 TF-IDF 向量化 + 余弦相似度；
    若 sklearn 不可用则降级为 Jaccard 文本相似度。

数据流：
    ┌──────────────────┐   启动   ┌────────────────────┐   查询   ┌────────────┐
    │ factors/*.json   │ ──────→ │ TF-IDF 向量化（缓存）│ ──────→ │ cosine sim │
    └──────────────────┘          └────────────────────┘          └────────────┘
                                          ↓                                 ↓
                                     1~2-gram 词表                     Top-K 因子

设计要点：
    - 启动时一次性把全库因子编码为 TF-IDF 矩阵；查询时只对 query 做 transform
    - 关键词预处理：统一分隔符 → 小写，便于处理 "momentum high, ,21" 这类乱序串
    - 文本构建：把因子名、描述、标签、计算式、中性化方法、参数等拼成单字符串
"""

from typing import Dict, Any, Callable, List, Optional
import json
import os
import numpy as np

from .base import BaseTool

# ── sklearn 可用性检测 ───────────────────────────
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("Warning: scikit-learn not installed. Falling back to text-based matching.")


class SearchFactorTool(BaseTool):
    """基于 TF-IDF 相似度的因子检索工具。"""

    def __init__(self, factor_dir: str = "./factors"):
        """初始化因子检索工具。

        参数:
            factor_dir: 因子 JSON 文件目录。
        """
        self.factor_dir = factor_dir
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.factor_vectors = None
        self.factors: List[Dict] = []
        self.factor_texts: List[str] = []

        # 启动即加载并向量化（一次性开销）
        self._load_factors_and_vectors()

    def get_name(self) -> str:
        """工具注册名。"""
        return "search_factor"

    # ── 文本构建 ───────────────────────────

    def _build_factor_text(self, factor: Dict) -> str:
        """把一个因子的多源信息拼成单字符串（用于向量化）。"""
        text_parts = []

        # 名称与描述
        text_parts.append(factor.get("factor_name", ""))
        text_parts.append(factor.get("description", ""))

        # 元数据：分类与标签
        metadata = factor.get("metadata", {})
        if metadata.get("category"):
            text_parts.append(metadata.get("category"))
        if metadata.get("tags"):
            text_parts.extend(metadata.get("tags", []))

        # 计算式
        calculation = factor.get("calculation", {})
        if calculation.get("expression"):
            text_parts.append(calculation.get("expression"))

        # 中性化方法
        processing = factor.get("processing", {})
        if processing.get("neutralization"):
            text_parts.append(processing.get("neutralization"))

        # 参数
        parameters = factor.get("parameters", {})
        for param_name, param_value in parameters.items():
            if isinstance(param_value, (int, float, str)):
                text_parts.append(f"{param_name}:{param_value}")

        # 统一小写
        return " ".join(text_parts).lower()

    def _parse_keyword_to_text(self, keyword: str) -> str:
        """把不规范关键词归一化为可匹配的文本。

        例如 "momentum high, ,21" -> "momentum high 21"。
        """
        keyword = keyword.strip()
        for sep in [',', ';', '|', '-', '_']:
            keyword = keyword.replace(sep, ' ')
        keyword = ' '.join(keyword.split())
        return keyword.lower()

    # ── 加载与向量化 ───────────────────────────

    def _load_factors_and_vectors(self) -> None:
        """扫描因子目录，构建 TF-IDF 矩阵。失败的文件直接跳过。"""
        self.factors = []
        self.factor_texts = []

        if not os.path.exists(self.factor_dir):
            return

        for file in os.listdir(self.factor_dir):
            if file.endswith(".json"):
                file_path = os.path.join(self.factor_dir, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        factor = json.load(f)
                        self.factors.append(factor)
                        self.factor_texts.append(self._build_factor_text(factor))
                except Exception:
                    continue  # 跳过任何无法解析的因子文件

        if SKLEARN_AVAILABLE and self.factor_texts:
            try:
                self.vectorizer = TfidfVectorizer(
                    max_features=5000,   # 控制词表规模
                    stop_words='english',
                    ngram_range=(1, 2),  # 同时保留 1-gram 与 2-gram
                    min_df=1,
                )
                self.factor_vectors = self.vectorizer.fit_transform(self.factor_texts)
            except Exception as e:
                print(f"Warning: Failed to compute TF-IDF vectors: {e}")
                self.vectorizer = None
                self.factor_vectors = None

    def _compute_tfidf_similarity(self, query_text: str) -> Optional[List[float]]:
        """对 query 做 transform 后与因子矩阵做余弦相似度。"""
        if not SKLEARN_AVAILABLE or not self.vectorizer or self.factor_vectors is None:
            return None
        try:
            query_vector = self.vectorizer.transform([query_text])
            similarities = cosine_similarity(query_vector, self.factor_vectors).flatten()
            return similarities.tolist()
        except Exception as e:
            print(f"Warning: Similarity computation failed: {e}")
            return None

    def _compute_text_score(self, factor_text: str, query_text: str) -> float:
        """降级方案：基于词集合的 Jaccard 相似度。"""
        if not factor_text or not query_text:
            return 0.0
        query_tokens = set(query_text.split())
        factor_tokens = set(factor_text.split())
        if not query_tokens:
            return 0.0
        intersection = len(query_tokens & factor_tokens)
        union = len(query_tokens | factor_tokens)
        return intersection / union if union > 0 else 0.0

    # ── 工具实现工厂 ───────────────────────────

    def get_implementation(self) -> Callable:
        def search_factor(keyword: str, threshold: float = 0.1) -> str:
            """用关键词检索最相关的 alpha 因子。

            参数:
                keyword:   检索关键词，如 "momentum high volatility"。
                threshold: 相似度阈值（0~1，默认 0.1）。

            返回值:
                命中因子列表（含相似度分数）的 JSON 字符串。
            """
            try:
                if not self.factors:
                    return json.dumps({
                        "query": keyword,
                        "count": 0,
                        "message": "No factors found in directory",
                        "results": [],
                    }, indent=2, ensure_ascii=False)

                # 归一化关键词
                query_text = self._parse_keyword_to_text(keyword)

                # 计算每个因子的相似度
                if SKLEARN_AVAILABLE and self.factor_vectors is not None:
                    similarities = self._compute_tfidf_similarity(query_text)
                    if similarities is not None:
                        scores = similarities
                    else:
                        scores = [self._compute_text_score(t, query_text) for t in self.factor_texts]
                else:
                    scores = [self._compute_text_score(t, query_text) for t in self.factor_texts]

                # 收集高于阈值的命中项
                results = []
                for i, factor in enumerate(self.factors):
                    score = scores[i]
                    if score >= threshold:
                        factor_copy = factor.copy()
                        factor_copy["_score"] = round(score, 4)
                        factor_copy["_similarity_method"] = "tfidf" if SKLEARN_AVAILABLE else "text"
                        results.append(factor_copy)

                # 按分数降序
                results.sort(key=lambda x: x["_score"], reverse=True)

                response = {
                    "query": keyword,
                    "normalized_query": query_text,
                    "count": len(results),
                    "similarity_method": "tfidf" if SKLEARN_AVAILABLE else "text",
                    "threshold": threshold,
                    "total_factors": len(self.factors),
                    "results": results,
                }
                return json.dumps(response, indent=2, ensure_ascii=False)

            except FileNotFoundError as e:
                return json.dumps({"error": str(e), "query": keyword}, indent=2, ensure_ascii=False)
            except Exception as e:
                return json.dumps({
                    "error": f"Error searching factors: {str(e)}",
                    "query": keyword,
                }, indent=2, ensure_ascii=False)

        return search_factor

    # ── 公开重载方法（外部调用） ───────────────────────────

    def reload_factors(self) -> str:
        """重新扫描因子目录并重建向量索引（在外部新增因子后使用）。"""
        self._load_factors_and_vectors()
        return json.dumps({
            "status": "reloaded",
            "factor_count": len(self.factors),
            "vectors_computed": self.factor_vectors is not None,
            "method": "tfidf" if SKLEARN_AVAILABLE else "text",
        }, indent=2, ensure_ascii=False)

    def get_description(self, producer: str = "OpenAI") -> Dict[str, Any]:
        """返回 OpenAI 工具描述 schema。"""
        if producer in ("OpenAI", "MiniMax"):
            return {
                "type": "function",
                "name": self.get_name(),
                "description": (
                    "Search alpha factors using TF-IDF vector similarity. "
                    "Uses scikit-learn's TF-IDF vectorizer to understand natural language queries "
                    "like 'momentum high volatility' or 'mean reversion with volume'. "
                    "Returns factors ranked by relevance score. "
                    "Supports irregular keyword strings (e.g., 'momentum high, ,21') "
                    "by automatically normalizing them. Requires scikit-learn for optimal performance."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": (
                                "Search keyword or phrase (e.g., 'momentum high volatility', "
                                "'mean reversion 20 days', 'volume price trend')"
                            ),
                        },
                        "threshold": {
                            "type": "number",
                            "description": (
                                "Minimum similarity score (0 to 1, default 0.1). "
                                "Higher values return only very similar factors."
                            ),
                        },
                    },
                    "required": ["keyword"],
                },
            }
        raise ValueError(f"Unsupported producer: {producer}")
