# Guangzhou AI keyword collection — research-text delivery

- Cutoff: `2026-09-27T14:59:52+08:00`
- Run: `AIKF-INT-20260909-full-comments`
- Platform/region: RedNote international / Guangzhou

This directory replaces the earlier hash-only Guangzhou snapshot as the analysis-ready delivery. It retains public post titles, descriptions, tags, top-level comments and replies, while removing access credentials and direct identity fields. It remains a continuation dataset and is kept separate from the earlier domestic baseline.

## Inventory

- Frozen targets: **2,630**
- Content collected: **2,521**
- Structurally complete reuse: **1**
- Completed without accessible content: **108**
- Deduplicated landed notes: **2,522**
- Deduplicated comments: **79,427** = 39,583 top-level + 39,844 replies
- Latest pagination records: **42,105**, all `complete`
- Dangling observed parent relationships: **122**; retained and flagged, never invented

`notes_unified.csv` and `comments_unified.csv` contain the public text required for downstream text analysis. Blank comment text is retained: image-only rows are labeled `image_only`, while truly empty rows are labeled `empty`.

## Privacy boundary

The export excludes cookies, session/browser state, signed URLs and `xsec_token`, media CDN URLs, proxy and egress details, device/account identifiers, crawler logs, nicknames and raw creator identifiers. Stable author/commenter linkage uses HMAC-SHA256; its private key is not in this repository. Detected phone numbers, email addresses, ID/bank-card numbers, contact handles, URLs and @mentions are replaced only at the fragment level and counted in `quality_summary.json`.

## Counting rules and known limitations

- Notes are unique by `note_id`; comments by `(note_id, comment_id)`; pagination by `(note_id, kind, root_comment_id)`.
- The 108 inaccessible targets remain in `worklist.csv` and `collection_completion.csv`; no text is invented for them.
- A dangling parent means a reply named a parent that was absent from the landed rows. The observed reply is retained with `dangling_parent=true`.
- Public location is already province/country-level in the source and is retained at that granularity.
- See `docs/RESEARCH_TEXT_PRESERVING_SANITIZATION_PROMPT_ZH.md` for the reusable export standard.
