# CLI reference

Run: `python3 <skill_dir>/scripts/sales_cli.py [--workspace DIR] <command>`. Workspace: `--workspace`, else env
`SALES_WORKSPACE`, else `./sales-workspace`. Output is JSON on stdout; errors are JSON on stderr with exit code 1.
Pass JSON inputs with `--json FILE` (or `-` for stdin).

| Command | Purpose |
|---|---|
| `init` | Create workspace (db, `exports/`, `icp/`) and list segments |
| `settings get` / `settings set --company X --sender Y` | Signature names (required before drafting) |
| `icp list` / `icp show CODE` | Segment rules (queries, exclusions, limits, channel order, offer) |
| `discover-brief CODE COUNTRY CITY [--count N]` | Instructions + schema for discovery (includes already-known names) |
| `discover-add CODE COUNTRY CITY --count N --json F` | Store candidates (needs name + http source URL; skips duplicates and clearly large ones) |
| `next [--state S] [--limit N]` | Leads with their `next_action` (enrich, verify, score, draft, review, approve) |
| `list [--state S] [--code C] [--country K]` | Query leads |
| `show LEAD_ID` | Every field with sources, confidence, and history |
| `enrich-brief LEAD_ID` / `enrich-apply LEAD_ID --json F` | Research and store facts (unsourced facts are dropped) |
| `verify LEAD_ID [--no-dns]` | Deterministic verification score and per-check notes |
| `score-brief LEAD_ID` / `score-apply LEAD_ID --json F [--review-json F]` | Fit judgement; CLI applies exclusions, caps, routing |
| `draft-brief LEAD_ID` / `draft-apply LEAD_ID --json F` | Message instructions; automatic checks on your draft |
| `review` / `promote LEAD_ID` | List undecided leads with concerns; promote one for drafting |
| `approve LEAD_ID --message TEXT\|@FILE [--channel C]` / `reject LEAD_ID [--reason T]` | Human decision |
| `export-xlsx [--out F]` | Arabic RTL workbook: summary, review list, excluded, notes |
| `serve [--port N]` | Approval UI on 127.0.0.1 (Arabic RTL, dark/light) |
| `status` | Counts by state |
| `demo-seed` / `demo-clear` | Fictional sample leads to preview the UI |

Country codes: SA, QA, KW, OM, AE, JO. Channels: whatsapp, instagram, email, linkedin.
