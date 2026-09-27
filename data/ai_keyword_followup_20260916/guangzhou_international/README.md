# Guangzhou international RedNote final collection

Final cutoff: `2026-09-27T13:28:35+08:00`

Run: `AIKF-INT-20260909-full-comments`

This directory is the sanitized final delivery of the Guangzhou international RedNote AI-keyword follow-up. It is a continuation dataset and remains physically separated from the earlier domestic baseline. All 2,630 selected targets across phases F001–F006 are closed.

## Final inventory

| File | Rows | Purpose |
| --- | ---: | --- |
| `worklist_sanitized.csv` | 2,630 | Stable target list without signed URLs |
| `batch_progress_sanitized.csv` | 2,630 | One effective terminal status per phase and original chunk |
| `notes_sanitized.csv` | 2,522 | Deduplicated landed-note metadata |
| `comments_sanitized.csv` | 79,427 | Deduplicated first- and second-level comment relationships |
| `pagination_status_sanitized.csv` | 42,105 | Latest top-level and reply pagination evidence |
| `manifest.json` | 1 | Machine-readable counts, QA, closure, and privacy boundary |

The 2,630 targets comprise 2,521 `ok`, one `ok_structural_reuse`, and 108 `skipped_unavailable` rows. The structural-reuse row had complete top-level and reply pagination on disk despite an older login-expired ledger result. Platform-unavailable rows are retained as explicit terminal outcomes and do not claim landed post or comment content.

## Counting and relationship rules

- Progress is merged across devices by `(phase_id, chunk)` so the late A/B split of F006 is counted once.
- Notes are deduplicated by `note_id`.
- Comments are deduplicated by `(note_id, comment_id)`.
- A reply is linked through `parent_comment_id`; the parent must share the same `note_id`.
- The final export contains 122 dangling parent relationships. They are retained as observed public relationship evidence because the referenced parent row was absent from the landed response; no parent record was invented.
- All 42,105 latest pagination records have status `complete`; no `running` or `incomplete` pagination state remains.

## Privacy and security boundary

The export excludes cookies, browser profiles, credentials, account/device identifiers, proxy and IP details, local paths, crawler logs, `xsec_token`, signed URLs, nicknames, locations, and media URLs. Raw post and comment text is not published; SHA-256 digests preserve equality and deduplication checks without exposing the original text. Actor identifiers are also represented only as SHA-256 digests.

## Completion boundary

This is the final Guangzhou international delivery for the frozen 2,630-note target list. Completion means every target is represented by successful complete pagination, a structurally complete reusable pagination artifact, or a confirmed platform-unavailable terminal result.
