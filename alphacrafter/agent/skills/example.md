---
name: example
description: This is an example of skill that demonstrates the skill registration system.
---

# Example Skill Documentation

This skill serves as a demonstration of how to create and register skills in the system.

## Purpose
Show developers how to properly structure a skill markdown file that will be automatically discovered and registered by the SkillFactory.

## Features Demonstrated
-  Frontmatter metadata parsing
-  Automatic class generation
-  Dynamic method binding
-  Factory pattern integration

## How It Works
When this file is placed in the `skills/` directory:
1. The `SkillFactory.initialize()` method scans all `.md` files
2. Parses the frontmatter between the `---` markers
3. Extracts `name`, `description`, and uses the remaining content as `details`
4. Dynamically creates a class named `ExampleSkill` (converted from "example")
5. Registers the class in the factory's `_skills` dictionary

## Registration Process
```python
# This happens automatically in skills/__init__.py

from skills import ExampleSkill
```



