#!/usr/bin/env python
# -*- coding: utf-8 -*-
'''
@File    :   loader.py
@Author  :   zemin
@Desc    :   记载skills 渐进式加载
'''

import os
import re
import shutil
from pathlib import Path
from typing import Any

# 内置技能目录（项目根目录下的 skills/ 文件夹）
BUILTIN_SKILLS_DIR = Path(__file__).parent.parent / "skills"
# 用户自定义技能目录（~/.cheerclaw/skills）
USER_SKILLS_DIR = Path.home() / ".cheerclaw" / "skills"


class SkillLoader:

    def __init__(self):
        self.user_skills_dir = USER_SKILLS_DIR
        self.builtin_skills_dir = BUILTIN_SKILLS_DIR
        self.user_skills_dir.mkdir(parents=True, exist_ok=True)


    def list_skills(self, filter_unavailable: bool = False) -> list[dict[str, Any]]:
        """列出所有可用技能
        filter_unavailable: 如果为 True，过滤掉依赖不可用的技能
        返回: 技能信息字典列表，包含 name/path/source/description/available
        """
        skills = []
        seen_names = set()

        # 用户自定义技能
        if self.user_skills_dir.exists():
            for skill_dir in self.user_skills_dir.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists():
                        name = skill_dir.name
                        seen_names.add(name)
                        skill_info = self._get_skill_info(name, skill_file, "user")
                        if not filter_unavailable or skill_info["available"]:
                            skills.append(skill_info)

        # 内置技能
        if self.builtin_skills_dir.exists():
            for skill_dir in self.builtin_skills_dir.iterdir():
                if skill_dir.is_dir():
                    name = skill_dir.name
                    if name in seen_names:
                        continue
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists():
                        skill_info = self._get_skill_info(name, skill_file, "builtin")
                        if not filter_unavailable or skill_info["available"]:
                            skills.append(skill_info)

        return skills

    def _get_skill_info(self, name: str, path: Path, source: str) -> dict[str, Any]:
        """获取单个技能信息
        name: 技能名称
        path: 技能文件路径
        source: 来源
        返回: 技能信息字典
        """
        meta = self._parse_frontmatter(path)

        requires = meta.get("requires", {})
        if not isinstance(requires, dict):
            requires = {}

        return {
            "name": name,
            "path": str(path),
            "source": source,
            "description": meta.get("description", name),
            "always": meta.get("always", False),
            "available": self._check_requirements(requires),
            "requires": requires,
        }


    def load_skill(self, name: str) -> str | None:
        """加载技能的完整内容
        name: 技能名称
        返回: 技能内容（包含 frontmatter），找不到返回 None
        """
        # 先查找用户自定义目录
        user_file = self.user_skills_dir / name / "SKILL.md"
        if user_file.exists():
            return user_file.read_text(encoding="utf-8")

        # 再查找内置目录
        builtin_file = self.builtin_skills_dir / name / "SKILL.md"
        if builtin_file.exists():
            return builtin_file.read_text(encoding="utf-8")

        return None

    def load_skills_for_context(self, skill_names: list[str]) -> str:
        """加载指定技能的内容（用于注入上下文）
        skill_names: 技能名称列表
        返回: 格式化的技能内容，多个技能用分隔线隔开
        """
        parts = []
        for name in skill_names:
            content = self.load_skill(name)
            if content:
                parts.append(f"### Skill: {name}\n\n{content}")

        return "\n\n---\n\n".join(parts) if parts else ""

    def get_always_skills(self) -> list[str]:
        """获取标记为 always=true 且可用的技能名称列表
        返回: 技能名称列表
        """
        result = []
        for skill in self.list_skills():
            if skill.get("always"):
                result.append(skill["name"])
        return result

    def get_always_skills_content(self) -> str:
        """加载所有 always=true 的技能内容
        返回: 格式化的技能内容文本
        """
        always_skills = self.get_always_skills()
        return self.load_skills_for_context(always_skills)

    def build_skills_summary(self) -> str:
        """构建技能摘要
        返回 XML 格式的摘要，让 Agent 知道有哪些技能可用
        需要使用该技能时 Agent 可以请求读取特定技能的完整内容
        """
        all_skills = self.list_skills(filter_unavailable=False)
        if not all_skills:
            return ""

        def escape_xml(s: str) -> str:
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        lines = ["<skills>"]
        for s in all_skills:
            name = escape_xml(s["name"])
            desc = escape_xml(s["description"])
            available = "true" if s["available"] else "false"

            lines.append(f'  <skill available="{available}">')
            lines.append(f"    <name>{name}</name>")
            lines.append(f"    <description>{desc}</description>")
            lines.append(f"    <path>{escape_xml(s['path'])}</path>")

            # 如果不可用，显示缺失的依赖
            if not s["available"]:
                missing = self._get_missing_requirements(s.get("requires", {}))
                if missing:
                    lines.append(f"    <missing>{escape_xml(missing)}</missing>")

            lines.append("  </skill>")
        lines.append("</skills>")

        return "\n".join(lines)


    def _parse_frontmatter(self, path: Path) -> dict[str, Any]:
        """解析文件的 YAML Frontmatter
        path: 文件路径
        返回: 元数据字典
        """
        content = path.read_text(encoding="utf-8")
        metadata = {}

        if content.startswith("---"):
            match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            if match:
                yaml_text = match.group(1)
                for line in yaml_text.split("\n"):
                    if ":" in line and not line.strip().startswith("-"):
                        key, value = line.split(":", 1)
                        key = key.strip()
                        value = value.strip().strip('"\'')

                        # 处理 requires 嵌套
                        if key.startswith("requires."):
                            sub_key = key.split(".")[1]
                            if "requires" not in metadata:
                                metadata["requires"] = {}
                            # 解析列表格式 [a, b]
                            if value.startswith("["):
                                items = [v.strip().strip('"\'') for v in value[1:-1].split(",")]
                                metadata["requires"][sub_key] = items
                            else:
                                metadata["requires"][sub_key] = [value] if value else []
                        else:
                            metadata[key] = value

        if "always" in metadata:
            metadata["always"] = str(metadata["always"]).lower() in ("true", "yes", "1")

        return metadata

    def _check_requirements(self, requires: dict) -> bool:
        """检查依赖是否满足
        requires: 依赖字典 {bins: [...], env: [...]}
        返回: 如果满足返回 True
        """
        for b in requires.get("bins", []):
            if not shutil.which(b):
                return False
        for e in requires.get("env", []):
            if not os.environ.get(e):
                return False
        return True

    def _get_missing_requirements(self, requires: dict) -> str:
        """获取未满足的依赖描述
        requires: 依赖字典
        返回: 缺失依赖的描述字符串
        """
        missing = []
        for b in requires.get("bins", []):
            if not shutil.which(b):
                missing.append(f"CLI: {b}")
        for e in requires.get("env", []):
            if not os.environ.get(e):
                missing.append(f"ENV: {e}")
        return ", ".join(missing)
