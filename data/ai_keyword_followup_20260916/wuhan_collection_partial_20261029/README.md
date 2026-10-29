# Wuhan AI-keyword collection — research-text delivery

- Snapshot: `2026-10-29T18:08:08+08:00` (Asia/Shanghai)
- Run: `AIKF-INT-20260927-WH-AI-LOCAL-ONLY`
- Frozen targets: **2,915**
- Public post bodies collected: **2,614**
- Deduplicated public comments: **83,586** = 40,318 top-level + 43,268 replies
- Target outcomes: `{"completed_without_accessible_content": 247, "content_collected": 2614, "login_expired": 1, "missing_terminal_status": 53}`
- Content notes missing top-level pagination evidence: **0**
- Content notes with incomplete latest pagination: **0**

`notes_unified.csv`, `comments_unified.csv` and `pagination_status.csv` use the same research-text schema as the existing Chengdu and Guangzhou deliveries. The worklist preserves every selected target and the completion file leaves login-expired/not-started work explicitly unresolved. `empty` ledger outcomes are represented as `completed_without_accessible_content`; they are not counted as posts with collected text.

The export contains public research text only. It excludes browser profiles, cookies, signed URLs/access tokens, media URLs, crawler logs, proxy/egress details, account/device identifiers, nicknames and raw author/commenter IDs. Textual PII patterns are redacted; author/commenter linkage is HMAC-SHA256 pseudonymized with a per-export key that is not stored in Git. `remaining_tasks.csv` contains only targets with a non-terminal ledger state; completed tasks are not included there.
