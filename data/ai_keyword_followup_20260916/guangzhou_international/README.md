# Guangzhou international RedNote collection snapshot

Snapshot cutoff: `2026-09-16T23:02:56+08:00`

Run: `AIKF-INT-20260909-full-comments`

This directory is a sanitized, in-progress snapshot of the Guangzhou international RedNote AI-keyword follow-up. It is a continuation dataset and is physically separated from the earlier domestic baseline. The target contains 2,630 globally selected notes across phases F001–F006. At this cutoff, 631 note batches were resolved and 1,999 remained.

## Snapshot inventory

| File | Rows | Purpose |
| --- | ---: | --- |
| `worklist_sanitized.csv` | 2,630 | Stable target list without signed URLs |
| `batch_progress_sanitized.csv` | 655 | Latest status per lane, phase, and chunk |
| `notes_sanitized.csv` | 623 | Deduplicated landed-note metadata |
| `comments_sanitized.csv` | 28,435 | Deduplicated first- and second-level comment relationships |
| `pagination_status_sanitized.csv` | 13,645 | Latest top-level and reply pagination evidence |
| `manifest.json` | 1 | Machine-readable cutoff, counts, QA, and privacy boundary |

Resolved batches comprise 607 `ok` rows and 24 `skipped_unavailable` rows. The unresolved snapshot statuses are 14 `captcha`, 9 `failed`, and 1 `login_expired`. These are retryable or deferred collection states, not completion claims.

## Counting and relationship rules

- Notes are deduplicated by `note_id`.
- Comments are deduplicated by `(note_id, comment_id)`.
- A reply is linked through `parent_comment_id`; the parent must share the same `note_id`.
- The snapshot contains 64 dangling parent relationships. They are retained as explicit partial evidence because their parent rows had not landed by the cutoff; no parent record was invented.
- Pagination contains 13,631 `complete`, 13 `incomplete`, and 1 `running` latest records at the cutoff.

## Privacy and security boundary

The export excludes cookies, browser profiles, credentials, account/device identifiers, proxy and IP details, local paths, crawler logs, `xsec_token`, signed URLs, nicknames, locations, and media URLs. Raw post and comment text is not published; SHA-256 digests preserve equality and deduplication checks without exposing the original text. Actor identifiers are also represented only as SHA-256 digests.

## Completion boundary

This is a checkpoint for cross-device continuity and audit, not the final Guangzhou dataset. Collection continues after the cutoff. A final export must be regenerated after all target batches and pagination relationships are reconciled.
