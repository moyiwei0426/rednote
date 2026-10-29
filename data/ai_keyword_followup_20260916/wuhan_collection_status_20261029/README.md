# Wuhan local-only collection status

Snapshot of the 2,915 Wuhan-local-only selected-note comment-reply tasks. Statuses are reconciled per task against the latest local ledger entry and the worklist order used to assign phase chunks.

| Latest task status | Tasks |
| --- | ---: |
| `ok` | 2,614 |
| `empty` | 247 |
| `login_expired` | 1 |
| `not_started` | 53 |
| Total | 2,915 |

The 54 outstanding tasks are F006 chunks 413–466. Chunk 413 needs a valid Wuhan browser login before retry; chunks 414–466 have no ledger attempt. Use `remaining_note_ids.csv` to identify them and `task_status.csv` for the full status list.

This public snapshot contains note IDs and collection-task metadata only. It excludes signed note URLs, xsec tokens, browser profiles, cookies, proxies, credentials, logs, note bodies, and comment/reply contents. A successful empty result is preserved as `empty` and is distinct from an unprocessed task.
