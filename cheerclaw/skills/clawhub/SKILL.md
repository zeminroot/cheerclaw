---
name: clawhub
description: the public skill registry. When I lack a capability (e.g., news, web search), use this to find and install the needed skill from ClawHub.
homepage: https://clawhub.ai
---

# ClawHub

Public skill registry for AI agents. Search by natural language (vector search).

## When to use

Use this skill when the user asks any of:
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

Always ask for user confirmation before installing a skill.** Inform the user about:
- The skill name and its purpose
- Request explicit confirmation to proceed

Once confirmed, run the install command:

```bash
npx --yes clawhub@latest install <slug> --workdir ~/.cheerclaw
```

Replace `<slug>` with the skill name from search results. This places the skill into `~/.cheerclaw/skills/`, where cheerclaw loads skills from. Always include `--workdir`.

## Update

```bash
npx --yes clawhub@latest update --all --workdir ~/.cheerclaw
```

## List installed

```bash
npx --yes clawhub@latest list --workdir ~/.cheerclaw
```

## Notes

- Requires Node.js (`npx` comes with it).
- No API key needed for search and install.
- Login (`npx --yes clawhub@latest login`) is only required for publishing.
- `--workdir ~/.cheerclaw` is critical — without it, skills install to the current directory instead of the clawspace.
- After install, remind the user to start a new session to load the skill.
