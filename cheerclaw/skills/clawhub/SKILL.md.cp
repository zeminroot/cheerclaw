---
name: clawhub
description: 🛠️ The skill marketplace. When I lack a capability (e.g., news, web search, image gen), use this to find and install the needed skill from ClawHub.
homepage: https://clawhub.ai
---

# ClawHub - Skill Marketplace

**The way to extend my capabilities.** If I don't have a tool for what you need (news, stock data, translation, etc.), use this skill to search ClawHub and install one.

## When to use

### Primary use case - Fill capability gaps:
- User asks for something I can't do → Search ClawHub for a skill
- User needs news → Search "news" or "headlines"
- User needs stock prices → Search "stock" or "finance"
- User needs translation → Search "translate"

### Also use when user explicitly asks:
- "find a skill for …"
- "search for skills"
- "install a skill"
- "what skills are available?"
- "update my skills"

## Search

```bash
npx --yes clawhub@latest search "web scraping" --limit 5
```

## Install

```bash
npx --yes clawhub@latest install <slug> --workdir <cheerclaw-dir>
```

Replace `<slug>` with the skill name from search results, and `<cheerclaw-dir>` with the path obtained via `Path.home() / ".cheerclaw"`. This places the skill into the `skills/` subdirectory, where CheerClaw loads user skills from. Always include `--workdir`.

## Update

```bash
npx --yes clawhub@latest update --all --workdir <cheerclaw-dir>
```

Use `Path.home() / ".cheerclaw"` for `<cheerclaw-dir>`.

## List installed

```bash
npx --yes clawhub@latest list --workdir <cheerclaw-dir>
```

Use `Path.home() / ".cheerclaw"` for `<cheerclaw-dir>`.

## ⚠️ Critical Rules

1. **NEVER install without user consent** - Always search first, present options, and ask user before installing
2. **CRITICAL**: Always use `--workdir <cheerclaw-dir>` with `Path.home() / ".cheerclaw"` or skills install to wrong location
3. After installing, use `read_skill` tool to load the skill immediately (skills are installed to `Path.home() / ".cheerclaw" / "skills"`, no restart needed)
4. Requires Node.js (`npx` comes with it)
5. No API key needed for search and install
6. Login is only required for publishing

## Example: Handling Capability Gaps

**User:** "今天有什么新闻？"

**My response:**

1. Acknowledge: "我目前没有新闻查询功能..."

2. Search: ```bash
   npx --yes clawhub@latest search "news" --limit 5
   ```

3. Ask for consent: "找到以下技能: [list]。是否为您安装 `xxx-news`？"

4. Install only if user agrees: ```bash
   npx --yes clawhub@latest install <slug> --workdir <cheerclaw-dir>
   ```
   (Use `Path.home() / ".cheerclaw"` for `<cheerclaw-dir>`)

5. Use immediately: "已安装！现在可以使用 `read_skill` 工具加载该技能并为您服务。"
