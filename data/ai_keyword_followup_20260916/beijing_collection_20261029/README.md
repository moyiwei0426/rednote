# Beijing AI-keyword collection — research-text delivery

- Snapshot: `2026-10-29T18:07:06+08:00` (Asia/Shanghai)
- Run: `AIKF-INT-20260925-BJ-AI-LOCAL-ONLY`
- Frozen targets: **1,250**
- Public post bodies collected: **1,086**
- Deduplicated public comments: **22,962** = 10,807 top-level + 12,155 replies
- Target outcomes: `{"completed_without_accessible_content": 164, "content_collected": 1086}`
- Content notes missing top-level pagination evidence: **0**
- Content notes with incomplete latest pagination: **0**

`notes_unified.csv`, `comments_unified.csv` and `pagination_status.csv` use the same research-text schema as the existing Chengdu and Guangzhou deliveries. The worklist preserves every selected target and the completion file leaves login-expired/not-started work explicitly unresolved. `empty` ledger outcomes are represented as `completed_without_accessible_content`; they are not counted as posts with collected text.

The export contains public research text only. It excludes browser profiles, cookies, signed URLs/access tokens, media URLs, crawler logs, proxy/egress details, account/device identifiers, nicknames and raw author/commenter IDs. Textual PII patterns are redacted; author/commenter linkage is HMAC-SHA256 pseudonymized with a per-export key that is not stored in Git. `remaining_tasks.csv` contains only targets with a non-terminal ledger state; completed tasks are not included there.
