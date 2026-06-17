"""
因子库语义多样性与新颖性分析

功能概述：
    把因子表达式解析为 AST（抽象语法树），用 Zhang-Shasha 树编辑距离（TED）
    衡量不同因子之间的"语义相似度"，进而得到两个关键指标：

        Φ_intra : 因子库内部多样性（所有 pair-wise TED 的均值）
        Φ_inter : 因子库相对 Alpha158 基准库的新颖性
                  （每个因子到最近 Alpha158 邻居的距离均值）

典型用法:
    python -m utils.calculate_diversity --input ./factors --output result.json

设计要点：
    - 用 zss 库计算 TED，时间复杂度 O(n^2 * m^2)（中等规模因子库可接受）
    - 数字字面量被统一抽象为 `$N`；非行情变量名抽象为 `$VAR`，
      以便不同窗口 / 不同变量名的因子之间可以公平比较
    - Alpha158 基准包含 K-Bar + 5 窗口的 29 类滚动因子
"""

import json
import os
import re
import ast
import math
import warnings
from pathlib import Path
from collections import deque
from itertools import combinations
from typing import Dict, List, Tuple, Optional, Set, Any
from tqdm import tqdm
import numpy as np
from zss import simple_distance, Node

warnings.filterwarnings('ignore')

# ════════════════════════════════════════════════════════════════════════════════
#   Alpha158 基准表达式集
# ════════════════════════════════════════════════════════════════════════════════
#
# 共 9 个 K-Bar + 4 个价格位置因子 + 29 类滚动因子 × 5 窗口 = 158 个

ALPHA158_EXPRESSIONS = {
    # ── K-Bar (9) ──
    "KMID": "(close - open) / open",
    "KLEN": "(high - low) / open",
    "KMID2": "(close - open) / (high - low)",
    "KUP": "(high - max(open, close)) / open",
    "KUP2": "(high - max(open, close)) / (high - low)",
    "KLOW": "(min(open, close) - low) / open",
    "KLOW2": "(min(open, close) - low) / (high - low)",
    "KSFT": "(2 * close - high - low) / open",
    "KSFT2": "(2 * close - high - low) / (high - low)",

    # ── Price Position (4) ──
    "OPEN0": "open / close",
    "HIGH0": "high / close",
    "LOW0": "low / close",
    "VWAP0": "vwap / close",
}

# 29 类滚动因子模板，{N} 由 WINDOWS 替换
ROLLING_TYPES = {
    # Trend
    "ROC":  "close / ts_delay(close, {N}) - 1",
    "MA":   "close / ts_mean(close, {N})",
    "BETA": "ts_slope(close, {N})",
    "RSQR": "ts_rsquare(close, {N})",
    "RESI": "close - ts_linearreg(close, {N})",
    # Volatility
    "STD":  "ts_std(close, {N})",
    "MAX":  "close / ts_max(high, {N})",
    "MIN":  "low / ts_min(low, {N})",
    "QTLU": "ts_quantile(close, 0.8, {N}) / close",
    "QTLD": "ts_quantile(close, 0.2, {N}) / close",
    "RSV":  "(close - ts_min(low, {N})) / (ts_max(high, {N}) - ts_min(low, {N}))",
    # Time Cycle
    "IMAX": "ts_argmax(high, {N}) / {N}",
    "IMIN": "ts_argmin(low, {N}) / {N}",
    "IMXD": "(ts_argmax(high, {N}) - ts_argmin(low, {N})) / {N}",
    # Volume-Price
    "CORR": "ts_corr(close, volume, {N})",
    "CORD": "ts_corr(ts_delta(close, 1), ts_delta(volume, 1), {N})",
    "CNTP": "ts_count(close > ts_delay(close, 1), {N}) / {N}",
    "CNTN": "ts_count(close < ts_delay(close, 1), {N}) / {N}",
    "CNTD": "(ts_count(close > ts_delay(close, 1), {N}) - ts_count(close < ts_delay(close, 1), {N}) / {N}",
    "SUMP": "ts_sum(max(close - ts_delay(close, 1), 0), {N}) / ts_sum(abs(ts_delta(close, 1)), {N})",
    "SUMN": "ts_sum(max(ts_delay(close, 1) - close, 0), {N}) / ts_sum(abs(ts_delta(close, 1)), {N})",
    "SUMD": "(ts_sum(close - ts_delay(close, 1), {N})) / ts_sum(abs(ts_delta(close, 1)), {N})",
    # Volume Volatility
    "VMA":  "volume / ts_mean(volume, {N})",
    "VSTD": "ts_std(volume, {N})",
    # Volume-Weighted
    "WVMA":  "ts_mean(close * volume, {N}) / ts_mean(volume, {N})",
    "VSUMP": "ts_sum(max(volume - ts_delay(volume, 1), 0), {N}) / ts_sum(abs(ts_delta(volume, 1)), {N})",
    "VSUMN": "ts_sum(max(ts_delay(volume, 1) - volume, 0), {N}) / ts_sum(abs(ts_delta(volume, 1)), {N})",
    "VSUMD": "(ts_sum(volume - ts_delay(volume, 1), {N})) / ts_sum(abs(ts_delta(volume, 1)), {N})",
}

WINDOWS = [5, 10, 20, 30, 60]

# 把模板展开为 29 * 5 = 145 个滚动因子
for rtype, expr_template in ROLLING_TYPES.items():
    for w in WINDOWS:
        name = f"{rtype}_{w}"
        ALPHA158_EXPRESSIONS[name] = expr_template.replace("{N}", str(w))


# ════════════════════════════════════════════════════════════════════════════════
#   分词 / 预处理
# ════════════════════════════════════════════════════════════════════════════════

# 内置时序 / 数学 / 截面函数白名单
TS_FUNCTIONS = {
    'ts_delay', 'ts_delta', 'ts_mean', 'ts_std', 'ts_max', 'ts_min',
    'ts_sum', 'ts_corr', 'ts_cov', 'ts_slope', 'ts_rsquare', 'ts_linearreg',
    'ts_quantile', 'ts_argmax', 'ts_argmin', 'ts_count', 'ts_rank',
    'ts_product', 'ts_skew', 'ts_kurt', 'ts_median', 'ts_mad',
}

MATH_FUNCTIONS = {
    'abs', 'log', 'sign', 'sqrt', 'exp', 'pow', 'sin', 'cos', 'tan',
    'max', 'min', 'rank', 'floor', 'ceil', 'round', 'clip', 'if', 'iff',
}

CS_FUNCTIONS = {
    'winsorize', 'winsor', 'rank_pct', 'rank_pctl', 'normalize',
    'zscore', 'standardize', 'demean', 'neutralize', 'regress_neutralize',
    'sector_neutralize', 'cap', 'floor_pct', 'scale',
}

# 后处理关键词（只影响分布、不改变逻辑，分析时剥除以保留核心信号）
POSTPROCESS_KEYWORDS = CS_FUNCTIONS | {
    'daily', 'cross', 'section', 'cross-sectional', 'cross_sectional',
    'per', 'stock', 'each', 'day',
}


def extract_core_expression(raw_text: str) -> str:
    """从冗长的因子描述中抽取核心数学表达式。

    策略:
      0. 单行无杂质直接 clean
      1. 匹配 `factor = ...` 模式
      2. 取链式赋值的最后一段
      3. 兜底返回 clean 后的全文
    """
    text = raw_text.strip()

    # 策略 0：单行清晰表达式直接返回
    if '\n' not in text and '=' not in text and not any(kw in text.lower() for kw in ['factor', 'compute', 'then']):
        return clean_expression(text)

    # 策略 1：匹配 "factor = ..."
    factor_match = re.search(
        r'(?:^|\n|;)\s*factor\s*[:=]\s*(.+?)(?:\n|;|$|\.\s*Daily|\.\s*Cross)',
        text, re.IGNORECASE
    )
    if factor_match:
        return clean_expression(factor_match.group(1))

    # 策略 2：链式赋值取最后一段
    segments = re.split(r'[;\n]+', text)
    segments = [s.strip() for s in segments if s.strip()]
    code_segments = [s for s in segments if '=' in s or any(op in s for op in ['+', '-', '*', '/', '(', ')'])]

    if code_segments:
        last = code_segments[-1]
        if '=' in last:
            last = last.split('=', 1)[-1].strip()
        return clean_expression(last)

    # 策略 3：兜底
    return clean_expression(text)


def clean_expression(expr: str) -> str:
    """清洗表达式：小写、规范化空白、剥离后处理关键词、去多余括号。"""
    expr = expr.strip().lower()

    # 移除类似 "then cross-sectional winsorize" 之类的后缀
    for kw in sorted(POSTPROCESS_KEYWORDS, key=len, reverse=True):
        expr = re.sub(rf'(?:daily|then|and|,)?\s*{kw}\s*(?:\([^)]*\))?', '', expr)

    expr = re.sub(r'\s+', ' ', expr).strip()
    expr = re.sub(r'[.,;]\s*(?:then|and|or)?\s*$', '', expr)
    expr = re.sub(r'\s+if\s+.+$', '', expr)
    expr = re.sub(r'\s+', ' ', expr).strip()

    # 反复去除外层多余括号
    while expr.startswith('(') and expr.endswith(')'):
        depth = 0
        balanced = True
        for i, c in enumerate(expr):
            if c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
            if depth == 0 and i < len(expr) - 1:
                balanced = False
                break
        if balanced:
            expr = expr[1:-1].strip()
        else:
            break
    return expr


# ════════════════════════════════════════════════════════════════════════════════
#   AST 解析器
# ════════════════════════════════════════════════════════════════════════════════

NUMBER = 'NUMBER'
VARIABLE = 'VARIABLE'
OPERATOR = 'OPERATOR'
FUNCTION = 'FUNCTION'
LPAREN = 'LPAREN'
RPAREN = 'RPAREN'
COMMA = 'COMMA'


def tokenize(expr: str) -> List[Tuple[str, str]]:
    """把表达式字符串切成 (类型, 值) token 列表。"""
    tokens = []
    i = 0
    n = len(expr)

    while i < n:
        c = expr[i]
        if c.isspace():
            i += 1
            continue

        # 数字（含小数）
        if c.isdigit() or (c == '.' and i + 1 < n and expr[i + 1].isdigit()):
            j = i
            while j < n and (expr[j].isdigit() or expr[j] == '.'):
                j += 1
            tokens.append((NUMBER, expr[i:j]))
            i = j
            continue

        # 标识符（变量或函数名）
        if c.isalpha() or c == '_':
            j = i
            while j < n and (expr[j].isalnum() or expr[j] == '_'):
                j += 1
            word = expr[i:j]
            # 向前看是否有 '(' 以判断函数 vs 变量
            k = j
            while k < n and expr[k].isspace():
                k += 1
            if k < n and expr[k] == '(':
                tokens.append((FUNCTION, word))
            else:
                tokens.append((VARIABLE, word))
            i = j
            continue

        # 运算符（含多字符比较符）
        if c in '+-*/^<>=!':
            if i + 1 < n and expr[i:i + 2] in ('<=', '>=', '==', '!='):
                tokens.append((OPERATOR, expr[i:i + 2]))
                i += 2
            else:
                tokens.append((OPERATOR, c))
                i += 1
            continue

        if c == '(':
            tokens.append((LPAREN, '('))
        elif c == ')':
            tokens.append((RPAREN, ')'))
        elif c == ',':
            tokens.append((COMMA, ','))
        i += 1

    return tokens


class ExpressionParser:
    """递归下降解析器：tokens -> zss.Node 形式的 AST。

    优先级: comparison < addition < multiplication < unary < primary
    """

    def __init__(self, tokens: List[Tuple[str, str]]):
        self.tokens = tokens
        self.pos = 0
        self.n = len(tokens)

    def peek(self) -> Optional[Tuple[str, str]]:
        if self.pos < self.n:
            return self.tokens[self.pos]
        return None

    def consume(self) -> Tuple[str, str]:
        token = self.tokens[self.pos]
        self.pos += 1
        return token

    def expect(self, token_type: str) -> Tuple[str, str]:
        token = self.consume()
        if token[0] != token_type:
            raise ValueError(f"Expected {token_type}, got {token}")
        return token

    def parse(self) -> Node:
        """入口：解析整条表达式。"""
        node = self.parse_comparison()
        if self.pos < self.n:
            # 残留 token：尝试当作隐式函数组合
            pass
        return node

    def parse_comparison(self) -> Node:
        """最低优先级：比较运算。"""
        left = self.parse_addition()
        while self.peek() and self.peek()[0] == OPERATOR and self.peek()[1] in ('<', '>', '<=', '>=', '==', '!='):
            op = self.consume()[1]
            right = self.parse_addition()
            left = Node(op)
            left.addkid(self._ensure_node(left) if False else self._ensure_node(left))
            left.addkid(self._ensure_node(right))
        return left

    def parse_addition(self) -> Node:
        """加减。"""
        left = self.parse_multiplication()
        while self.peek() and self.peek()[0] == OPERATOR and self.peek()[1] in ('+', '-'):
            op = self.consume()[1]
            right = self.parse_multiplication()
            node = Node(op)
            node.addkid(self._ensure_node(left))
            node.addkid(self._ensure_node(right))
            left = node
        return left

    def parse_multiplication(self) -> Node:
        """乘除。"""
        left = self.parse_unary()
        while self.peek() and self.peek()[0] == OPERATOR and self.peek()[1] in ('*', '/'):
            op = self.consume()[1]
            right = self.parse_unary()
            node = Node(op)
            node.addkid(self._ensure_node(left))
            node.addkid(self._ensure_node(right))
            left = node
        return left

    def parse_unary(self) -> Node:
        """一元运算与函数调用。"""
        if self.peek() and self.peek()[0] == OPERATOR and self.peek()[1] == '-':
            self.consume()
            operand = self.parse_unary()
            node = Node('neg')
            node.addkid(self._ensure_node(operand))
            return node
        if self.peek() and self.peek()[0] == FUNCTION:
            return self.parse_function_call()
        return self.parse_primary()

    def parse_function_call(self) -> Node:
        """解析 func(arg1, arg2, ...)。"""
        func_name = self.consume()[1]
        self.expect(LPAREN)
        node = Node(func_name)
        if self.peek() and self.peek()[0] != RPAREN:
            node.addkid(self.parse_comparison())
            while self.peek() and self.peek()[0] == COMMA:
                self.consume()
                node.addkid(self.parse_comparison())
        self.expect(RPAREN)
        return node

    def parse_primary(self) -> Node:
        """基础 token：数字、变量、括号表达式。"""
        if self.peek() is None:
            return Node('nil')

        if self.peek()[0] == NUMBER:
            val = self.consume()[1]
            # 所有数字字面量统一抽象为 $N（窗口/常量无差别）
            try:
                float(val)
                return Node('$N')
            except ValueError:
                return Node(val)

        if self.peek()[0] == VARIABLE:
            var_name = self.consume()[1]
            # 行情变量保留语义；其它抽象为 $VAR
            canonical_vars = {
                'close', 'high', 'low', 'open', 'volume', 'vwap',
                'returns', 'ret', 'value', 'price', 'amount', 'turnover',
            }
            if var_name in canonical_vars:
                return Node(var_name)
            return Node('$VAR')

        if self.peek()[0] == LPAREN:
            self.consume()
            node = self.parse_comparison()
            self.expect(RPAREN)
            return node

        return Node('nil')

    def _ensure_node(self, obj) -> Node:
        if isinstance(obj, Node):
            return obj
        return Node(str(obj))


def expression_to_tree(expr: str) -> Optional[Node]:
    """把表达式字符串转 AST；解析失败时退化为 RAW 节点。"""
    expr = expr.strip()
    if not expr:
        return None
    try:
        tokens = tokenize(expr)
        if not tokens:
            return None
        parser = ExpressionParser(tokens)
        return parser.parse()
    except Exception:
        return Node(f'RAW:{expr[:50]}')


def compute_ted(tree1: Node, tree2: Node) -> float:
    """两棵树之间的归一化树编辑距离（Zhang-Shasha）。"""
    if tree1 is None or tree2 is None:
        return 1.0
    try:
        distance = simple_distance(tree1, tree2)
        size1 = _tree_size(tree1)
        size2 = _tree_size(tree2)
        total = size1 + size2
        if total == 0:
            return 0.0
        return distance / total
    except Exception:
        return 1.0


def _tree_size(node: Node) -> int:
    """统计树中节点总数（含根）。"""
    if node is None:
        return 0
    count = 1
    for child in node.children:
        count += _tree_size(child)
    return count


# ════════════════════════════════════════════════════════════════════════════════
#   主计算
# ════════════════════════════════════════════════════════════════════════════════

def load_factor_expressions(factor_dir: str) -> List[Tuple[str, str]]:
    """加载一个因子库目录下所有 JSON 中的核心表达式。

    返回:
        [(factor_id, core_expression), ...]
    """
    factor_dir = Path(factor_dir)
    factors = []

    for fpath in factor_dir.rglob('*.json'):
        try:
            content = None
            # 尝试多种编码（兼容中文环境）
            for encoding in ['utf-8', 'gbk', 'gb2312', 'utf-8-sig', 'latin-1']:
                try:
                    with open(fpath, 'r', encoding=encoding) as f:
                        content = f.read()
                    break
                except (UnicodeDecodeError, UnicodeError):
                    continue
            if content is None:
                print(f"  [WARN] Cannot decode {fpath} with any encoding")
                continue

            data = json.loads(content)
            factor_id = data.get('factor_id', fpath.stem)
            calc = data.get('calculation', {})
            raw_expr = calc.get('expression', '')
            if not raw_expr:
                continue
            core_expr = extract_core_expression(raw_expr)
            if core_expr and core_expr.strip():
                factors.append((factor_id, core_expr))
        except (json.JSONDecodeError, KeyError, IOError) as e:
            print(f"  [WARN] Skipping {fpath}: {e}")
            continue

    return factors


def build_reference_trees(ref_expressions: Dict[str, str]) -> Dict[str, Node]:
    """把参考表达式字典（name -> expr）全部解析为 AST。"""
    trees = {}
    for name, expr in ref_expressions.items():
        tree = expression_to_tree(expr)
        if tree is not None:
            trees[name] = tree
    return trees


def compute_intra_diversity(
    factor_exprs: List[Tuple[str, str]],
    verbose: bool = True,
) -> Dict[str, Any]:
    """计算因子库的内部多样性 Φ_intra（pair-wise TED 均值）。

    返回:
        {
          'phi_intra', 'n_factors', 'n_valid', 'n_pairs',
          'failed_parse', 'distances' (min/max/median/...),
          'most_similar_pair', 'most_different_pair',
        }
    """
    n = len(factor_exprs)

    if n < 2:
        return {
            'phi_intra': float('nan'),
            'n_factors': n,
            'n_pairs': 0,
            'error': 'Need at least 2 factors',
        }

    if verbose:
        print(f"  Building ASTs for {n} factors...")

    trees = {}
    failed = []
    for fid, expr in tqdm(factor_exprs, desc="  Building ASTs", disable=not verbose):
        tree = expression_to_tree(expr)
        if tree is not None:
            trees[fid] = tree
        else:
            failed.append(fid)

    valid_ids = list(trees.keys())
    n_valid = len(valid_ids)
    if verbose and failed:
        print(f"  [WARN] {len(failed)} factors failed to parse: {failed[:5]}...")

    if n_valid < 2:
        return {
            'phi_intra': float('nan'),
            'n_factors': n,
            'n_valid': n_valid,
            'n_pairs': 0,
            'failed_parse': failed,
            'error': 'Need at least 2 valid factors',
        }

    n_pairs = n_valid * (n_valid - 1) // 2
    if verbose:
        print(f"  Computing {n_pairs} pairwise tree edit distances...")

    distances = []
    pair_details = []
    pairs = list(combinations(range(n_valid), 2))

    for i, j in tqdm(pairs, desc="  Computing pairwise distances", disable=not verbose):
        id_i, tree_i = valid_ids[i], trees[valid_ids[i]]
        id_j, tree_j = valid_ids[j], trees[valid_ids[j]]
        d = compute_ted(tree_i, tree_j)
        distances.append(d)
        pair_details.append({
            'factor_i': id_i,
            'factor_j': id_j,
            'distance': round(d, 4),
        })

    distances = np.array(distances)
    phi_intra = float(np.mean(distances))
    min_idx = int(np.argmin(distances))
    max_idx = int(np.argmax(distances))

    return {
        'phi_intra': round(phi_intra, 4),
        'n_factors': n,
        'n_valid': n_valid,
        'n_pairs': n_pairs,
        'failed_parse': failed,
        'distances': {
            'min': round(float(distances[min_idx]), 4),
            'max': round(float(distances[max_idx]), 4),
            'median': round(float(np.median(distances)), 4),
            'p25': round(float(np.percentile(distances, 25)), 4),
            'p75': round(float(np.percentile(distances, 75)), 4),
        },
        'most_similar_pair': pair_details[min_idx],
        'most_different_pair': pair_details[max_idx],
    }


def compute_inter_novelty(
    factor_exprs: List[Tuple[str, str]],
    ref_trees: Dict[str, Node],
    verbose: bool = True,
) -> Dict[str, Any]:
    """计算因子库相对参考库（默认 Alpha158）的新颖性 Φ_inter。

    定义: 对每个因子，取其到参考库中"最近邻"的 TED，再对所有因子求平均。
    Φ_inter 越大，说明因子越"不寻常"。
    """
    n = len(factor_exprs)
    m = len(ref_trees)

    if n == 0 or m == 0:
        return {
            'phi_inter': float('nan'),
            'n_factors': n,
            'n_refs': m,
            'error': 'Empty factor or reference set',
        }

    if verbose:
        print(f"  Building ASTs for {n} factors...")

    factor_trees = {}
    failed = []
    for fid, expr in tqdm(factor_exprs, desc="  Building ASTs", disable=not verbose):
        tree = expression_to_tree(expr)
        if tree is not None:
            factor_trees[fid] = tree
        else:
            failed.append(fid)

    valid_ids = list(factor_trees.keys())
    n_valid = len(valid_ids)
    if verbose and failed:
        print(f"  [WARN] {len(failed)} factors failed to parse")

    ref_names = list(ref_trees.keys())
    if verbose:
        print(f"  Computing nearest-neighbor distances to {m} reference factors...")

    min_distances = []
    nn_details = []
    for fid in tqdm(valid_ids, desc="  Computing NN distances", disable=not verbose):
        ftree = factor_trees[fid]
        best_dist = 1.0
        best_ref = None
        for rname in ref_names:
            rtree = ref_trees[rname]
            d = compute_ted(ftree, rtree)
            if d < best_dist:
                best_dist = d
                best_ref = rname
        min_distances.append(best_dist)
        nn_details.append({
            'factor_id': fid,
            'nearest_ref': best_ref,
            'distance': round(best_dist, 4),
        })

    min_distances = np.array(min_distances)
    phi_inter = float(np.mean(min_distances))
    most_novel_idx = int(np.argmax(min_distances))
    least_novel_idx = int(np.argmin(min_distances))

    return {
        'phi_inter': round(phi_inter, 4),
        'n_factors': n,
        'n_valid': n_valid,
        'n_refs': m,
        'failed_parse': failed,
        'distances': {
            'min': round(float(min_distances[least_novel_idx]), 4),
            'max': round(float(min_distances[most_novel_idx]), 4),
            'median': round(float(np.median(min_distances)), 4),
            'p25': round(float(np.percentile(min_distances, 25)), 4),
            'p75': round(float(np.percentile(min_distances, 75)), 4),
        },
        'most_novel_factor': nn_details[most_novel_idx],
        'least_novel_factor': nn_details[least_novel_idx],
        'all_nn_details': nn_details,
    }


# ════════════════════════════════════════════════════════════════════════════════
#   顶层 Pipeline
# ════════════════════════════════════════════════════════════════════════════════

def analyze_factor_library(
    factor_dir: str,
    output_path: Optional[str] = None,
    verbose: bool = True,
) -> Dict[str, Any]:
    """对单个因子库跑完整的多样性 + 新颖性分析。

    流程:
      1. 加载并抽取核心表达式
      2. 构建 Alpha158 参考 AST
      3. 计算 Φ_intra
      4. 计算 Φ_inter
      5. （可选）落盘 JSON
    """
    print("=" * 60)
    print(f"Semantic Diversity & Novelty Analysis")
    print(f"Factor Library: {factor_dir}")
    print("=" * 60)

    # Step 1
    print("\n[1/4] Loading factor expressions...")
    factor_exprs = load_factor_expressions(factor_dir)
    print(f"  Loaded {len(factor_exprs)} factors")
    if len(factor_exprs) == 0:
        print("  [ERROR] No factors found!")
        return {'error': 'No factors found'}

    if verbose:
        print("  Sample expressions:")
        for fid, expr in factor_exprs[:3]:
            print(f"    [{fid}]: {expr[:100]}...")

    # Step 2
    print("\n[2/4] Building Alpha158 reference trees...")
    ref_trees = build_reference_trees(ALPHA158_EXPRESSIONS)
    print(f"  Built {len(ref_trees)} reference trees (out of {len(ALPHA158_EXPRESSIONS)} expressions)")

    # Step 3
    print("\n[3/4] Computing intra-library semantic diversity (Φ_intra)...")
    intra_results = compute_intra_diversity(factor_exprs, verbose=verbose)
    print(f"  Φ_intra = {intra_results.get('phi_intra', 'N/A')}")

    # Step 4
    print("\n[4/4] Computing inter-library semantic novelty (Φ_inter)...")
    inter_results = compute_inter_novelty(factor_exprs, ref_trees, verbose=verbose)
    print(f"  Φ_inter = {inter_results.get('phi_inter', 'N/A')}")

    results = {
        'library_path': str(Path(factor_dir).resolve()),
        'n_factors_total': len(factor_exprs),
        'n_reference_factors': len(ref_trees),
        'intra_diversity': intra_results,
        'inter_novelty': inter_results,
    }

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        serializable = _make_serializable(results)
        with open(output_path, 'w') as f:
            json.dump(serializable, f, indent=2, default=str)
        print(f"\nResults saved to: {output_path}")

    # 摘要输出
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  Total factors loaded:    {len(factor_exprs)}")
    print(f"  Valid ASTs built:        {intra_results.get('n_valid', 'N/A')}")
    print(f"  Alpha158 reference size: {len(ref_trees)}")
    print()
    print(f"  Φ_intra  (internal diversity):  {intra_results.get('phi_intra', 'N/A')}")
    print(f"  Φ_inter  (external novelty):    {inter_results.get('phi_inter', 'N/A')}")
    print()
    print(f"  Most similar factor pair  (intra): {intra_results.get('most_similar_pair', {})}")
    print(f"  Most different factor pair (intra): {intra_results.get('most_different_pair', {})}")
    print(f"  Most novel factor      (inter):    {inter_results.get('most_novel_factor', {})}")
    print(f"  Least novel factor     (inter):    {inter_results.get('least_novel_factor', {})}")
    print("=" * 60)

    return results


def _make_serializable(obj: Any) -> Any:
    """递归地把 numpy 类型转为 Python 原生类型，方便 JSON 序列化。"""
    if isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {key: _make_serializable(val) for key, val in obj.items()}
    elif isinstance(obj, list):
        return [_make_serializable(item) for item in obj]
    elif isinstance(obj, Path):
        return str(obj)
    return obj


# ════════════════════════════════════════════════════════════════════════════════
#   命令行入口
# ════════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Semantic Diversity & Novelty Analysis for Factor Libraries'
    )
    parser.add_argument(
        '--input', type=str, required=True,
        help='Path to factor library directory containing factor.json files',
    )
    parser.add_argument(
        '--output', type=str, default=None,
        help='Path to save JSON results',
    )
    parser.add_argument(
        '--batch', nargs='+', default=None,
        help='Multiple factor library directories for batch analysis (A1 A2 A3 ...)',
    )
    parser.add_argument(
        '--batch-output-dir', type=str, default=None,
        help='Output directory for batch analysis results',
    )
    parser.add_argument(
        '--quiet', action='store_true',
        help='Suppress verbose output',
    )

    args = parser.parse_args()
    verbose = not args.quiet

    analyze_factor_library(
        args.input,
        output_path=args.output,
        verbose=verbose,
    )
