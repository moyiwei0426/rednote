# Shanghai GK2026D1 deep-collection checkpoint

This package is the Shanghai mandatory deep-collection checkpoint for the
`GK2026D1` event (`2026高考第一天`). It contains the public post body, all
public first-level comments, all public second-level replies returned by the
platform, and pagination evidence for the 35 Shanghai-mandatory notes.

## Collection summary

- Complete worklist items: 35/35
- Public notes: 35
- Public comments: 8174
- First-level comments: 3534
- Second-level replies: 4640
- Pagination evidence rows: 3579
- Incomplete pagination rows: 0
- Public comment IP region present: 8170/8174
- Public note IP region present: 0/35; the platform did not return author
  region in these note responses.

Files contain public post, comment, relationship, and pagination evidence only.
Cookies, browser profiles, local paths, proxy secrets, xsec tokens, and raw
browser/session data are excluded.

## Files

- `notes_public_full.csv`: one row per collected note.
- `comments_public_full.csv`: one row per collected first-level comment or
  second-level reply.
- `comment_pagination_status.csv`: one row per completed note/comment pagination
  request state.
- `collection_worklist_status.csv`: one row per planned Shanghai-mandatory note,
  including completion and row counts.
- `checkpoint_manifest.json`: machine-readable row counts, hashes, and boundary
  metadata for the checkpoint.
- `COLLECTION_STATUS.md`: human-readable completion and validation summary.

## Column guide

### `notes_public_full.csv`

- `chunk_index`: queue chunk number used for checkpoint resume.
- `collection_status`: final collection state for the note; `complete` means
  body and comments were collected successfully.
- `event_id`, `event_name`, `phase_id`, `phase_name`: event and phase labels.
- `note_id`: public note identifier.
- `note_url`: public note URL without retained session secrets.
- `type`: note media type returned by the platform, such as normal or video.
- `title`: note title.
- `desc`: note body text.
- `time`: note publish time as platform epoch milliseconds.
- `last_update_time`: platform last-update time as epoch milliseconds.
- `creator_hash`: hashed author identifier used for analysis joins.
- `nickname`: public author nickname as returned.
- `liked_count`, `collected_count`, `comment_count`, `share_count`: public
  engagement counters returned by the platform.
- `image_list`: comma-separated public media URLs returned by the platform.
- `tag_list`: comma-separated public topic tags.
- `source_keyword`: source keyword when available from collection context.
- `public_ip_location`: public coarse IP region for the author when returned.
  This maps to `author_region` in the normalized core structure. Blank means
  the platform did not return a public author region; it is not inferred.
- `last_modify_ts`: local export/update timestamp in epoch milliseconds.

### `comments_public_full.csv`

- `chunk_index`: queue chunk number of the parent note.
- `collection_status`: final collection state for the parent note.
- `event_id`: event label.
- `note_id`: parent note identifier.
- `comment_id`: public comment identifier.
- `parent_comment_id`: parent first-level comment id for second-level replies;
  blank for first-level comments.
- `create_time`: comment publish time as platform epoch milliseconds.
- `content`: public comment text.
- `creator_hash`: hashed commenter identifier used for analysis joins.
- `nickname`: public commenter nickname as returned.
- `like_count`: public comment like count.
- `sub_comment_count`: number of replies declared on the first-level comment
  when returned.
- `pictures`: comma-separated public comment image URLs, if any.
- `public_ip_location`: public coarse IP region for the commenter when returned.
  This maps to `commenter_region` in the normalized core structure. Blank means
  the platform did not return a public commenter region; it is not inferred.
- `last_modify_ts`: local export/update timestamp in epoch milliseconds.

Use `note_id:comment_id` as the stable comment key. A blank
`parent_comment_id` indicates `top_level`; a non-blank `parent_comment_id`
indicates `reply`.

### `comment_pagination_status.csv`

- `recorded_at`: time when pagination status was recorded.
- `kind`: pagination type, usually note-level or root-comment-level comments.
- `note_id`: parent note identifier.
- `root_comment_id`: first-level comment id for reply pagination; blank for
  note-level comment pagination.
- `status`: pagination status. `complete` means the crawler reached the platform
  endpoint for that pagination path.
- `stop_reason`: explicit stop reason returned by the collector.
- `pages`: number of pages fetched for this pagination path.
- `observed_comments`: number of comments observed on this path.
- `declared_comments`: public platform-declared count when available.
- `collection_egress_region`: configured region of the collection exit.
- `collection_egress_id`: non-secret label for the collection exit.
- `collection_account_id`: logical collection account label.
- `collection_cdp_port`: local CDP port used by the collector.
- `chunk_index`, `collection_status`, `event_id`: checkpoint join fields.
- `unlimited`: whether unlimited pagination mode was enabled.
- `error`: error text if pagination failed; blank for successful rows.

### `collection_worklist_status.csv`

- `chunk_index`: queue chunk number.
- `collection_status`: final item status.
- `event_id`, `event_name`, `phase_id`, `phase_name`: event and phase labels.
- `note_id`, `note_url`: planned note identity and URL.
- `source_regions`: search region(s) that surfaced this note.
- `source_keywords`: source keyword(s) that surfaced this note.
- `assignment_hash`: stable assignment hash for de-duplication and work split.
- `note_records`: number of exported note rows.
- `comment_records`: number of exported comment rows.
- `top_level_comments`: number of first-level comments exported for the note.
- `reply_comments`: number of second-level replies exported for the note.
- `pagination_status`: aggregate pagination state for the note.
- `resume_action`: next action if incomplete; blank/no action for complete rows.
