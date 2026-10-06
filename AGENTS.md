# Instructions for AI agents (Codex, Gemini CLI, Cursor, and any agent that reads AGENTS.md)

This repository ships one skill: **sales-prospecting**.

When the user asks to prospect leads, find ideal customers (ICP), validate or qualify a lead list, draft cold
outreach, or export leads for a sales team, read `skills/sales-prospecting/SKILL.md` and follow it exactly.
It is a standard Agent Skill (`SKILL.md` + `references/` + `scripts/`), so agents with native skill support
should install the folder `skills/sales-prospecting` instead (see README).

Hard rules, always: never invent contact data, every stored fact needs its source URL, never send messages
yourself (a human approves first), and never put prices in outreach.

Working on this repo itself: run `pytest` from the repo root (Python 3.11+, `pip install pyyaml openpyxl fastapi uvicorn pytest httpx`).
