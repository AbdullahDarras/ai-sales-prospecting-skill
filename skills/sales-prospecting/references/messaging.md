# Messages

Formal Modern Standard Arabic (no dialect). Four parts: greeting by name and title, one real specific observation
about their account or business (with its source URL), the segment's first offer, one light closed question.
Then the opt-out sentence and the two-line signature: `مع التقدير،` / `<sender> | <company>`.

Forbidden: any price, cost, fee, discount or currency; invented observations; claims about results you cannot cite;
bracketed placeholders. Length 250-1200 characters.

`draft-apply` rejects a draft and returns `problems` when: it mentions price words, lacks the opt-out sentence,
lacks the company or sender name, misses the known decision maker's name, cites an observation URL that is not
stored for this lead, is too short or too long, or contains dialect words.
`approve` additionally refuses any message that still contains `[` or `]`.
Sending is a human action (WhatsApp, LinkedIn, Instagram links) or a later integration, never yours.
