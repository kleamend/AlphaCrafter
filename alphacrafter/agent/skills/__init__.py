import os
import re
import sys
import importlib.abc
import importlib.machinery
from pathlib import Path
from types import ModuleType
from typing import Dict, Optional, Type
from .base import BaseSkill

# Cache for parsed markdown files
_skill_cache: Dict[str, dict] = {}
_skill_classes: Dict[str, Type[BaseSkill]] = {}


def _parse_markdown_file(file_path: Path) -> Optional[dict]:
    """Parse markdown file to extract frontmatter and content"""
    try:
        content = file_path.read_text(encoding='utf-8')
        
        # Parse frontmatter (content between ---)
        frontmatter_pattern = r'^---\s*\n(.*?)\n---\s*\n(.*)$'
        match = re.match(frontmatter_pattern, content, re.DOTALL)
        
        if not match:
            return None
        
        frontmatter_text = match.group(1)
        details = match.group(2).strip()
        
        # Parse YAML-like frontmatter
        frontmatter = {}
        for line in frontmatter_text.split('\n'):
            if ':' in line:
                key, value = line.split(':', 1)
                frontmatter[key.strip()] = value.strip()
        
        return {
            'name': frontmatter.get('name', ''),
            'description': frontmatter.get('description', ''),
            'details': details,
            'file_path': file_path
        }
    except Exception as e:
        print(f"Error parsing {file_path}: {e}")
        return None


def _generate_skill_class(skill_data: dict) -> Type[BaseSkill]:
    """Generate a skill class from parsed data"""
    
    # Generate class name from skill name
    base_name = skill_data['name'].replace('-', '_').replace(' ', '_')
    class_name = ''.join(word.capitalize() for word in base_name.split('_')) + 'Skill'
    
    # Create the class dynamically
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
            '__module__': 'skills'  # Important: set the module to 'skills'
        }
    )
    
    return skill_class


def _scan_skill_files() -> Dict[str, Type[BaseSkill]]:
    """Scan all markdown files and generate classes"""
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


# Load all skills at module initialization
_skill_classes = _scan_skill_files()


# Custom finder for dynamic imports
class SkillFinder(importlib.abc.MetaPathFinder):
    """Custom finder to handle dynamic skill imports"""
    
    def find_spec(self, fullname, path, target=None):
        if fullname.startswith('skills.'):
            # Extract the class name (e.g., 'skills.BasicMathSkill' -> 'BasicMathSkill')
            class_name = fullname.split('.')[-1]
            
            # Check if we have this skill
            if class_name in _skill_classes:
                # Create a spec for this module
                loader = SkillLoader(class_name)
                return importlib.machinery.ModuleSpec(fullname, loader)
        
        return None


class SkillLoader(importlib.abc.Loader):
    """Custom loader that returns a module containing the skill class"""
    
    def __init__(self, class_name: str):
        self.class_name = class_name
    
    def create_module(self, spec):
        """Create a new module"""
        module = ModuleType(spec.name)
        
        # Add the skill class to the module
        skill_class = _skill_classes.get(self.class_name)
        if skill_class:
            setattr(module, self.class_name, skill_class)
            
            # Also add an instance getter for convenience
            def get_instance():
                return skill_class()
            setattr(module, f'get_{self.class_name.lower()}', get_instance)
        
        return module
    
    def exec_module(self, module):
        """Execute the module (nothing to do here)"""
        pass


# Install the custom finder
sys.meta_path.insert(0, SkillFinder())


# Define what's available in the module
def __getattr__(name):
    """
    Handle attribute access for skill classes.
    This allows: from skills import BasicMathSkill
    """
    # Check if it's a skill class
    if name in _skill_classes:
        return _skill_classes[name]
    
    # Check if it's a skill name (without 'Skill' suffix)
    for class_name, skill_class in _skill_classes.items():
        if name.lower() == class_name.replace('skill', '').lower():
            return skill_class
    
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


__all__ = [
    'BaseSkill'
]