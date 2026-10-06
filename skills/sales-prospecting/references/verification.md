# Verification layer

Two separate questions, two scores (0-100): **are the facts true** (verification) and **is it a fit** (fit).

## Verification weights
| Check | Max | Rule |
|---|---|---|
| Existence and activity | 30 | website up 10, maps open 10 (0 and flagged if closed), social post within 60 days 10 |
| Source agreement | 30 | independent source classes agreeing on the name: 1 -> 5, 2 -> 15, 3+ -> 20; phones agreeing across classes +10; conflicting phones -10 (flagged); an official source among them +5 |
| Contacts | 20 | valid mobile 12 (landline 8) by country format; email valid and domain resolves 8 (any provider is fine) |
| Decision maker | 20 | confirmed by 2 source classes 20, one 8, none 0 ("contact only, owner unknown") |

Source classes: `official` (registry, ministry, chamber) > `own_site`, `maps` > `directory` > `social`.
Phone formats checked for SA, QA, KW, OM, AE, JO (a +962 number on a Riyadh lead scores 0 on contacts).

## Fit
You judge fit from recorded evidence only. The CLI then: applies hard exclusions without asking you (closed,
non-private, team size or branch limits), caps the score at 65 when no valid evidence URL or label is `unknown`,
and requires an adversarial review for borderline cases (fit 60-79 or verification 70-79).

## Concerns
Record conflicts and doubts in `concerns` (identity conflicts, same address as a bigger entity, reputation red
flags, number mismatches). They are shown to the human reviewer. They are information, not penalties.
