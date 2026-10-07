# Install instructions for an AI agent

You are an AI agent (Claude Code in the Claude Desktop app, or similar) and the user asked you to install the
skill **sales-prospecting**. The user does not use a terminal: do everything yourself with your shell tool,
show them what you run, and explain results in simple Arabic. macOS or Linux. (Windows: see README, manual install.)

Prerequisite: `python3` 3.9 or newer. Check with `python3 --version`. If it is missing on macOS, a system dialog
will offer to install the Command Line Tools: tell the user to accept it, wait, then retry.

## Install (run as one command)

```bash
set -e
TMP="$(mktemp -d)"
curl -fsSL -o "$TMP/skill.zip" https://github.com/AbdullahDarras/ai-sales-prospecting-skill/archive/refs/heads/main.zip
unzip -q "$TMP/skill.zip" -d "$TMP"
SRC="$TMP/ai-sales-prospecting-skill-main/skills/sales-prospecting"
DEST="$HOME/.claude/skills/sales-prospecting"
mkdir -p "$HOME/.claude/skills"
if [ -e "$DEST" ] && ! grep -q "^name: sales-prospecting" "$DEST/SKILL.md" 2>/dev/null; then
  echo "REFUSING: $DEST exists and is not this skill. Ask the user what to do."; exit 1
fi
rm -rf "$DEST"
cp -R "$SRC" "$DEST"
rm -rf "$TMP"
python3 "$DEST/scripts/bootstrap.py"
python3 "$DEST/scripts/sales_cli.py" --workspace "$(mktemp -d)" init | head -20
```

What it does: downloads the repository zip (no git needed), replaces only an earlier copy of this same skill in
`~/.claude/skills/`, prepares an isolated Python environment under `~/.sales-prospecting/venv` (needs internet, one time),
and runs a check. Nothing else on the machine is changed.

## Verify and finish

- Success looks like JSON from the last command listing three segments (`TEC-2`, `VIS-1`, `VIS-3`).
- If `curl` fails: report the exact error (usually no internet). If `bootstrap.py` fails: report its JSON error.
- Do not run anything beyond these steps. Do not send or contact anyone.

Then tell the user, in Arabic:
1. The skill is installed.
2. They must start a **new session** in the Code tab (the current one will not see it).
3. They can then say, for example: "ابحث لي عن 5 كافيهات مستقلة في الرياض وجهّز رسائل التواصل"
   and Claude will ask for their name and company name (used in the message signature).
