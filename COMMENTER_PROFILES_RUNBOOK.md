# Commenter Public Profile Enrichment

Use this stage after `full-recon-comments` when the study needs anonymized commenter public-post counts, public post text keywords, post type distribution, and AI-related post ratio.

## Recommended Command

```bash
DEVICE_ID=C \
ACCOUNT_ID=account_c \
STAGE=commenter-profiles \
RUN_ID=<same_run_id> \
COMMENTS_PER_NOTE=10000 \
PUBLIC_POST_LIMIT=50 \
COMMENTER_LIMIT=0 \
scripts/xhs_device_run.sh
```

For a pilot run, limit the number of commenters:

```bash
COMMENTER_LIMIT=20 PUBLIC_POST_LIMIT=20 STAGE=commenter-profiles scripts/xhs_device_run.sh
```

## What It Collects

The stage re-reads visible comments for the selected notes, temporarily uses comment payload profile access fields in memory, and then reads each commenter's public profile posts.

It writes only anonymized research outputs. It does not persist raw `user_id`, profile URL, avatar URL, raw nickname, or `xsec_token`.

## New Output Tables

`commenter_profile_summary.csv`

- `commenter_anonymous_hash`
- `event_id`
- `phase_id`
- `source_comment_count`
- `source_note_count`
- `first_comment_time_bj`
- `regions_observed`
- `profile_accessible`
- `public_post_count`
- `public_post_count_bucket`
- `sampled_public_posts_count`
- `post_type_distribution`
- `top_profile_keywords`
- `ai_related_post_ratio`
- `profile_collected_device`
- `profile_collected_account`
- `profile_collected_at_bj`

`commenter_public_posts_sample.csv`

- `commenter_anonymous_hash`
- `event_id`
- `phase_id`
- `public_post_hash`
- `post_type`
- `post_text`
- `post_keywords`
- `post_publish_time_bj`
- `post_publish_date_bj`
- `post_like_count_num`
- `post_comment_count_num`
- `post_collect_count_num`
- `is_ai_related`
- `collected_at_bj`

`actor_commenter_seed.csv` is enriched with:

- `profile_accessible`
- `public_post_count_bucket`
- `sampled_public_posts_count`
- `top_profile_keywords`
- `post_type_distribution`
- `ai_related_post_ratio`

## Privacy Boundary

Allowed in final outputs:

- Anonymous commenter hash
- Public post count bucket
- Sampled public post text
- Extracted public post keywords
- Post type distribution
- AI-related post ratio

Not allowed in final outputs:

- Raw `user_id`
- Profile URL
- Avatar URL
- Raw nickname
- `xsec_token`
- Follow/follower lists
- Like lists
