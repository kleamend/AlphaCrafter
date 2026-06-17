"""
技能加载与动态注册模块

功能概述：
    自动扫描同目录下的所有 `*.md` 文件，把每个文件解析为一个 Skill 类。
    文件格式约定：

        ---
        name: factor-mining
        description: 如何挖掘 alpha 因子
        ---
        (Markdown 详细说明...)

    文件名本身不影响加载，name 取自 frontmatter。

设计要点：
    - 模块导入时即扫描 + 缓存，避免每次新建 Agent 时都重新解析
    - 通过自定义 MetaPathFinder + Loader，实现 `from skills import FactorMiningSkill`
      这样的动态导入，便于上层代码统一使用
    - 每个 Skill 的 name / description / details 来自 frontmatter + 正文，
      与 BaseSkill 的三个抽象方法一一对应
"""

import os
import re
import sys
import importlib.abc
import importlib.machinery
from pathlib import Path
from types import ModuleType
from typing import Dict, Optional, Type
from .base import BaseSkill

# ── 缓存 ───────────────────────────
# 解析后的 markdown 字典 / 生成的 Skill 类都缓存起来，避免重复 IO
_skill_cache: Dict[str, dict] = {}
_skill_classes: Dict[str, Type[BaseSkill]] = {}


# ════════════════════════════════════════════════════════════════════════════════
#   Markdown 解析
# ════════════════════════════════════════════════════════════════════════════════

def _parse_markdown_file(file_path: Path) -> Optional[dict]:
    """解析一个 markdown 文件，提取 frontmatter 与正文。

    约定格式:
        ---
        name: xxx
        description: xxx
        ---
        (Markdown 正文)
    """
    try:
        content = file_path.read_text(encoding='utf-8')

        # 简单 YAML-like 解析（不需要完整 PyYAML 依赖）
        frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
        match = re.match(frontmatter_pattern, content, re.DOTALL)
        if not match:
            return None

        frontmatter_text = match.group(1)
        details = match.group(2).strip()

        frontmatter = {}
        for line in frontmatter_text.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                frontmatter[key.strip()] = value.strip()

        return {
            'name': frontmatter.get('name', ''),
            'description': frontmatter.get('description', ''),
            'details': details,
            'file_path': file_path,
        }
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return None


# ════════════════════════════════════════════════════════════════════════════════
#   Skill 类的动态生成
# ════════════════════════════════════════════════════════════════════════════════

def _generate_skill_class(skill_data: dict) -> Type[BaseSkill]:
    """根据解析出的 frontmatter + 详情生成 BaseSkill 子类。

    使用 type() 动态创建类，避免为每个 markdown 文件手写 Python 类。
    """
    # 名字 -> 帕斯卡命名 + Skill 后缀
    base_name = skill_data['name'].replace('-', '_').replace(' ', '_')
    class_name = ''.join(word.capitalize() for word in base_name.split('_')) + 'Skill'

    skill_class = type(
        class_name,
        (BaseSkill,),
        {
            '_name': skill_data['name'],
            '_description': skill_data['description'],
            '_details': skill_data['details'],
            '_file_path': skill_data['file_path'],
            'get_name': lambda self: self._name,
            'get_description': lambda self: self._description,
            'get_details': lambda self: self._details,
            '__repr__': lambda self: f"<Skill: {self._name}>",
            '__module__': 'skills',  # 让 repr 显示来自 skills 模块
        },
    )
    return skill_class


def _scan_skill_files() -> Dict[str, Type[BaseSkill]]:
    """扫描目录下所有 markdown 并生成对应 Skill 类。"""
    skills_dir = Path(__file__).parent
    md_files = skills_dir.glob("*.md")

    classes = {}
    for md_file in md_files:
        skill_data = _parse_markdown_file(md_file)
        if skill_data and skill_data['name']:
            skill_class = _generate_skill_class(skill_data)
            class_name = skill_class.__name__
            classes[class_name] = skill_class
            _skill_cache[class_name] = skill_data

    return classes


# ── 模块导入时即完成全部扫描 ───────────────────────────
_skill_classes = _scan_skill_files()


# ════════════════════════════════════════════════════════════════════════════════
#   动态导入支持
# ════════════════════════════════════════════════════════════════════════════════
#
# 通过自定义 MetaPathFinder + Loader，使以下写法能直接生效：
#
#     from skills import FactorMiningSkill
#
# 这避免了硬编码的 __init__ 导出列表，新增/删除 markdown 即可改变可用技能。

class SkillFinder(importlib.abc.MetaPathFinder):
    """拦截 `skills.*` 的导入请求，把它们指向动态生成的 Skill 类。"""

    def find_spec(self, fullname, path, target=None):
        if fullname.startswith('skills.'):
            class_name = fullname.split('.')[-1]
            if class_name in _skill_classes:
                loader = SkillLoader(class_name)
                return importlib.machinery.ModuleSpec(fullname, loader)
        return None


class SkillLoader(importlib.abc.Loader):
    """根据类名返回包含 Skill 类的"模块对象"。

    同时暴露 get_<classname> 函数用于快速获取单例。
    """

    def __init__(self, class_name: str):
        self.class_name = class_name

    def create_module(self, spec):
        """构造一个模块对象并把 Skill 类挂上去。"""
        module = ModuleType(spec.name)
        skill_class = _skill_classes.get(self.class_name)
        if skill_class:
            setattr(module, self.class_name, skill_class)

            # 额外暴露一个 get_xxx() 工厂方法
            def get_instance():
                return skill_class()
            setattr(module, f'get_{self.class_name.lower()}', get_instance)
        return module

    def exec_module(self, module):
        """占位：动态模块无需执行额外代码。"""
        pass


# 将自定义 Finder 插到最前，优先于默认 loader
sys.meta_path.insert(0, SkillFinder())


def __getattr__(name):
    """模块级属性访问钩子，支持直接 `from skills import XXXSkill`。

    若 name 是已注册类名则返回类本身；否则尝试按去掉 'Skill' 后缀的方式匹配。
    """
    if name in _skill_classes:
        return _skill_classes[name]
    for class_name, skill_class in _skill_classes.items():
        if name.lower() == class_name.replace('skill', '').lower():
            return skill_class
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = ['BaseSkill']
