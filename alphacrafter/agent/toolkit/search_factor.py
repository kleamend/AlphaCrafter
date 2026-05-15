from typing import Dict, Any, Callable, List, Optional
import json
import os
from pathlib import Path
import numpy as np

from .base import BaseTool

try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    print("Warning: scikit-learn not installed. Falling back to text-based matching.")


class SearchFactorTool(BaseTool):
    """Tool for searching alpha factors using TF-IDF vector similarity."""

    def __init__(self, factor_dir: str = "./factors"):
        """
        Initialize the search factor tool with TF-IDF based similarity.

        Args:
            factor_dir: Directory containing factor JSON files
        """
        self.factor_dir = factor_dir
        self.vectorizer = None
        self.factor_vectors = None
        self.factors = []
        self.factor_texts = []
        
        # Load factors and precompute vectors
        self._load_factors_and_vectors()

    def get_name(self) -> str:
        return "search_factor"

    def _build_factor_text(self, factor: Dict) -> str:
        """
        Build a comprehensive text representation of a factor.
        """
        text_parts = []
        
        # Factor name and description
        text_parts.append(factor.get("factor_name", ""))
        text_parts.append(factor.get("description", ""))
        
        # Factor category and tags
        metadata = factor.get("metadata", {})
        if metadata.get("category"):
            text_parts.append(metadata.get("category"))
        if metadata.get("tags"):
            text_parts.extend(metadata.get("tags", []))
        
        # Calculation expression
        calculation = factor.get("calculation", {})
        if calculation.get("expression"):
            text_parts.append(calculation.get("expression"))
        
        # Processing information
        processing = factor.get("processing", {})
        if processing.get("neutralization"):
            text_parts.append(processing.get("neutralization"))
        
        # Parameters
        parameters = factor.get("parameters", {})
        for param_name, param_value in parameters.items():
            if isinstance(param_value, (int, float, str)):
                text_parts.append(f"{param_name}:{param_value}")
        
        # Join all parts with spaces
        return " ".join(text_parts).lower()

    def _parse_keyword_to_text(self, keyword: str) -> str:
        """
        Parse and normalize keyword string into search text.
        Handles irregular strings like "momentum high, ,21"
        """
        # Clean the keyword
        keyword = keyword.strip()
        
        # Replace commas and other separators with spaces
        for sep in [',', ';', '|', '-', '_']:
            keyword = keyword.replace(sep, ' ')
        
        # Remove extra whitespace
        keyword = ' '.join(keyword.split())
        
        return keyword.lower()

    def _load_factors_and_vectors(self) -> None:
        """Load all factor files and precompute TF-IDF vectors."""
        self.factors = []
        self.factor_texts = []
        
        if not os.path.exists(self.factor_dir):
            return
        
        # Read all factor files
        for file in os.listdir(self.factor_dir):
            if file.endswith(".json"):
                file_path = os.path.join(self.factor_dir, file)
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        factor = json.load(f)
                        self.factors.append(factor)
                        self.factor_texts.append(self._build_factor_text(factor))
                except Exception:
                    continue  # skip bad files
        
        # Compute TF-IDF vectors if we have factors and sklearn is available
        if SKLEARN_AVAILABLE and self.factor_texts:
            try:
                self.vectorizer = TfidfVectorizer(
                    max_features=5000,
                    stop_words='english',
                    ngram_range=(1, 2),
                    min_df=1
                )
                self.factor_vectors = self.vectorizer.fit_transform(self.factor_texts)
            except Exception as e:
                print(f"Warning: Failed to compute TF-IDF vectors: {e}")
                self.vectorizer = None
                self.factor_vectors = None

    def _compute_tfidf_similarity(self, query_text: str) -> List[float]:
        """
        Compute TF-IDF similarity between query and all factors.
        """
        if not SKLEARN_AVAILABLE or not self.vectorizer or self.factor_vectors is None:
            return None
        
        try:
            # Transform query using the same vectorizer
            query_vector = self.vectorizer.transform([query_text])
            
            # Compute cosine similarity
            similarities = cosine_similarity(query_vector, self.factor_vectors).flatten()
            
            return similarities.tolist()
            
        except Exception as e:
            print(f"Warning: Similarity computation failed: {e}")
            return None

    def _compute_text_score(self, factor_text: str, query_text: str) -> float:
        """
        Fallback text-based scoring when TF-IDF is not available.
        """
        if not factor_text or not query_text:
            return 0.0
        
        # Simple token matching
        query_tokens = set(query_text.split())
        factor_tokens = set(factor_text.split())
        
        if not query_tokens:
            return 0.0
        
        # Jaccard similarity
        intersection = len(query_tokens & factor_tokens)
        union = len(query_tokens | factor_tokens)
        
        return intersection / union if union > 0 else 0.0

    def get_implementation(self) -> Callable:
        def search_factor(keyword: str, threshold: float = 0.1) -> str:
            """
            Search alpha factors using TF-IDF vector similarity.
            
            Args:
                keyword: Search keyword/phrase (e.g., "momentum high volatility", "mean reversion 20 days")
                threshold: Minimum similarity score (0~1, default 0.1)
                
            Returns:
                JSON string of matched factors with similarity scores
            """
            try:
                if not self.factors:
                    return json.dumps({
                        "query": keyword,
                        "count": 0,
                        "message": "No factors found in directory",
                        "results": []
                    }, indent=2, ensure_ascii=False)
                
                # Parse and normalize keyword
                query_text = self._parse_keyword_to_text(keyword)
                
                # Compute similarity scores
                if SKLEARN_AVAILABLE and self.factor_vectors is not None:
                    similarities = self._compute_tfidf_similarity(query_text)
                    if similarities is not None:
                        scores = similarities
                    else:
                        # Fallback to text-based scoring
                        scores = [self._compute_text_score(t, query_text) for t in self.factor_texts]
                else:
                    # Fallback to text-based scoring
                    scores = [self._compute_text_score(t, query_text) for t in self.factor_texts]
                
                # Build results with scores
                results = []
                for i, factor in enumerate(self.factors):
                    score = scores[i]
                    
                    if score >= threshold:
                        factor_copy = factor.copy()
                        factor_copy["_score"] = round(score, 4)
                        factor_copy["_similarity_method"] = "tfidf" if SKLEARN_AVAILABLE else "text"
                        results.append(factor_copy)
                
                # Sort by score descending
                results.sort(key=lambda x: x["_score"], reverse=True)
                
                # Add search metadata
                response = {
                    "query": keyword,
                    "normalized_query": query_text,
                    "count": len(results),
                    "similarity_method": "tfidf" if SKLEARN_AVAILABLE else "text",
                    "threshold": threshold,
                    "total_factors": len(self.factors),
                    "results": results
                }
                
                return json.dumps(response, indent=2, ensure_ascii=False)
                
            except FileNotFoundError as e:
                return json.dumps({
                    "error": str(e),
                    "query": keyword
                }, indent=2, ensure_ascii=False)
            except Exception as e:
                return json.dumps({
                    "error": f"Error searching factors: {str(e)}",
                    "query": keyword
                }, indent=2, ensure_ascii=False)
        
        return search_factor

    def reload_factors(self) -> str:
        """
        Reload factors from disk and recompute vectors.
        Useful when new factors are added.
        """
        self._load_factors_and_vectors()
        return json.dumps({
            "status": "reloaded",
            "factor_count": len(self.factors),
            "vectors_computed": self.factor_vectors is not None,
            "method": "tfidf" if SKLEARN_AVAILABLE else "text"
        }, indent=2, ensure_ascii=False)

    def get_description(self, producer: str = "OpenAI") -> Dict[str, Any]:
        """Return tool description based on the producer."""
        if producer == "OpenAI":
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
                            "description": "Search keyword or phrase (e.g., 'momentum high volatility', 'mean reversion 20 days', 'volume price trend')"
                        },
                        "threshold": {
                            "type": "number",
                            "description": "Minimum similarity score (0 to 1, default 0.1). Higher values return only very similar factors."
                        }
                    },
                    "required": ["keyword"]
                }
            }
        else:
            raise ValueError(f"Unsupported producer: {producer}")