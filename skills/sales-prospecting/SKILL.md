---
name: sales-prospecting
description: Find, verify and qualify ideal customers (ICP) from public web sources, then prepare first-contact outreach for human approval. Evidence-based verification layer (every fact carries a source URL and confidence), segment rules in YAML, Arabic formal-MSA messages without prices, an approval UI, and Excel export for a sales team. Use when the user asks to prospect leads, find ideal customers or an ICP, build or validate a lead list, draft cold outreach, or hand leads to sales. Arabic triggers - ابحث عن عملاء، عملاء مثاليين، قائمة مبيعات، تواصل بارد، تحقق من العملاء.
license: MIT
compatibility: Needs python3 3.9+ (scripts/bootstrap.py prepares an isolated environment with pyyaml, openpyxl, and fastapi+uvicorn for the optional approval UI) and an agent with web search/fetch tools.
---

# Sales prospecting

You are the brain; `scripts/sales_cli.py` is the guard. You search and judge with your own tools, then hand
your findings to the CLI as JSON. The CLI enforces the rules deterministically (sources, scoring, exclusions,
message checks, stage order) and stores everything. **You never send messages.** A human approves first.

## Setup (once per project)

```bash
SALES="python3 <skill_dir>/scripts/sales_cli.py --workspace ./sales-workspace"   # <skill_dir> = folder holding this SKILL.md
$SALES init                                                  # creates ./sales-workspace (db, exports, icp)
# If it says Python packages are missing, run this ONCE, then repeat the command above (it finds the environment by itself):
python3 <skill_dir>/scripts/bootstrap.py                     # isolated environment in ~/.sales-prospecting/venv
$SALES settings set --company "<company>" --sender "<sender name>"   # required: appears in every message signature
$SALES icp list                                              # bundled example segments + your own in ./sales-workspace/icp
```

Ask the user which segment, country and city. If no segment fits, write one with them: read
`references/icp-authoring.md`, save it as `./sales-workspace/icp/<CODE>.yaml`. Everything (queries, exclusions,
team-size limits, channel order, first offer) comes from that file, never from your assumptions.

## Non-negotiable rules

1. **Never invent** a phone, email, name, URL or number. A fact without the exact page URL where you saw it is not stored.
2. **No prices, costs, fees or discounts** in qualification or messages, for any segment.
3. **Human approval before any contact.** Do not send, post or DM. Messages stay drafts until `approve`.
4. Messages are formal Modern Standard Arabic unless the user asks otherwise, and carry an opt-out line.
5. Use only public information. Do not scrape behind logins or bypass anti-bot walls. Say what you could not access.
6. When unsure, the honest answer is `unknown`, not a guess. The CLI downgrades confident scores that lack evidence.

## Workflow (one lead at a time, resumable)

Each `*-brief` command returns `instructions` (what to research) and a JSON `schema` (the exact output shape).
Each `*-apply` command takes your JSON via `--json FILE` (or `-` for stdin). Always follow the returned schema.

| Step | Brief | You do | Apply |
|---|---|---|---|
| 1 Discover | `discover-brief CODE COUNTRY "City" --count N` | 3-5 varied searches; collect names and real source URLs. Shallow only. | `discover-add CODE COUNTRY "City" --count N --json f.json` |
| 2 Enrich | `enrich-brief LEAD_ID` | Open the site, socials, maps, directories. Collect contacts, decision maker, size, activity, concerns, each with its URL. | `enrich-apply LEAD_ID --json f.json` |
| 3 Verify | none (deterministic) | nothing | `verify LEAD_ID` (prints score and per-check notes) |
| 4 Score | `score-brief LEAD_ID` | Judge fit against the ICP using only recorded evidence. | `score-apply LEAD_ID --json f.json` |
| 5 Draft | `draft-brief LEAD_ID` | Write the message from the given observation and rules. | `draft-apply LEAD_ID --json f.json` |
| 6 Approve | n/a | **Human**: `serve` (UI) or `approve LEAD_ID --message @file` / `reject LEAD_ID` | |
| 7 Export | n/a | `export-xlsx [--out file.xlsx]` for the sales team | |

Loop: `next` lists leads and their `next_action`. Process them until none remain, then report counts with `status`.

### Branches you must handle

- `score-brief` returns `status: out_of_icp`: the CLI already excluded it (size limits, closed, government). Move on.
- `score-apply` returns `review_required`: run the adversarial review described in `review_brief`
  (try to prove the verdict wrong), then rerun the same command with `--review-json`.
- `draft-apply` returns `problems`: fix exactly those and resubmit (max 2 attempts, then leave it and report).
- `draft-brief` returns `no_channel`: the lead went to review; report it, do not force a channel.
- Lead ended `undecided`: a human reads `review`, then `promote LEAD_ID` and you draft it (steps 5).
- Lead ended `discarded` (verification below 50) or `out_of_icp`: leave it; it appears in the Excel "excluded" sheet with the reason.
- `UsageLimit` or tool failures: stop cleanly; every apply is idempotent per state, so the next session resumes with `next`.

## Reporting back

Summarise per segment: discovered, discarded, excluded (with reasons), undecided (with the main concerns),
pending approval. Be explicit that nothing passed the automatic thresholds if that is true. Offer `serve` for
review and `export-xlsx` for sharing. Read `references/limitations.md` before promising quality.

## References (load only when needed)

- `references/cli-reference.md`: every command and flag with examples.
- `references/workflow.md`: state machine and what each state means.
- `references/verification.md`: verification weights, thresholds, conflict handling.
- `references/messaging.md`: message structure, forbidden content, automatic checks.
- `references/icp-authoring.md`: how to write a segment YAML (with an interview checklist).
- `references/limitations.md`: what public data cannot give you, and calibration status.
