# Workflow and states

```
discovered -> enriched -> verified -> scored -> drafted -> pending_approval -> approved -> (sent: out of scope)
                 |            |          |
              discarded   undecided  out_of_icp        rejected | stuck | blocked
```

| State | Meaning | Next |
|---|---|---|
| discovered | Name + source found, nothing else | `enrich-brief` |
| enriched | Facts stored with sources | `verify` |
| verified | Verification score computed (>= 50) | `score-brief` |
| discarded | Verification < 50: evidence too thin | none (kept locally) |
| scored | Fit judged and above thresholds | `draft-brief` |
| out_of_icp | Hard exclusion (size, closed, government) or model exclusion | none |
| undecided | Middle scores, conflicting evidence, no channel, or reviewer objection | human `review`, then `promote` |
| pending_approval | Draft passed automatic checks | human `approve` / `reject` |
| approved | Human approved the final message and channel | sending is not implemented here |

Thresholds (provisional, uncalibrated): ready = verification >= 75 and fit >= 70; discard below 50.
Invalid stage order is refused by the CLI and nothing changes.
