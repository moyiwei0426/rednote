# rednote

This repository contains a Xiaohongshu/RedNote data collection kit expanded as a browsable project directory.

- Collection engine: `MediaCrawler/`
- Device and event configs: `configs/`
- GitHub-ready exported data: `github_data/`
- Distribution and merge scripts: `scripts/`
- Optional collection seed files: `seed_data/`
- Package guide: `XHS_DISTRIBUTED_COLLECTION_PACKAGE.md`
- GitHub sync guide: `GITHUB_SYNC_RUNBOOK.md`

## Full comment collection

For studies that need comment timelines and commenter public IP regions, use the new
`full-recon-comments` stage. It collects notes and then immediately fetches as many
visible first-level comments as possible for each note, reducing repeat visits to the
same note URLs.

See `FULL_RECON_COMMENTS_RUNBOOK.md` for the recommended low-frequency command and
data field locations.
