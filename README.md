# rednote

This repository contains a Xiaohongshu/RedNote data collection kit expanded as a browsable project directory.

- Collection engine: `MediaCrawler/`
- Device and event configs: `configs/`
- Collaboration-ready device data: `data/` (start at `data/README.md`)
- Legacy GitHub-ready exports: `github_data/`
- Distribution and merge scripts: `scripts/`
- Optional collection seed files: `seed_data/`
- Package guide: `XHS_DISTRIBUTED_COLLECTION_PACKAGE.md`
- GitHub sync guide: `GITHUB_SYNC_RUNBOOK.md`

## Data for collaborators

All current device snapshots use one convention:

```text
data/<device>/<snapshot>/
```

Open [`data/README.md`](data/README.md) first. It lists every available device
snapshot, collection scope, row counts, recommended tables, and privacy boundary.
Use the per-snapshot `README.md` before reading a CSV. `github_data/` is retained
only for earlier compatibility exports; new device-level deliveries belong in `data/`.

## Full comment collection

For studies that need comment timelines and commenter public IP regions, use the new
`full-recon-comments` stage. It collects notes and then immediately fetches as many
visible first-level comments as possible for each note, reducing repeat visits to the
same note URLs.

See `FULL_RECON_COMMENTS_RUNBOOK.md` for the recommended low-frequency command and
data field locations.

## Commenter public profile enrichment

Use `commenter-profiles` after comment collection when the study needs anonymized
commenter public-post counts, public post text keywords, post type distribution, and
AI-related post ratio. The stage uses profile access fields only in memory and writes
anonymized outputs:

- `commenter_profile_summary.csv`
- `commenter_public_posts_sample.csv`
- enriched `actor_commenter_seed.csv`

See `COMMENTER_PROFILES_RUNBOOK.md` for the command, output fields, and privacy boundary.
