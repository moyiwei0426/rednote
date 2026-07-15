# Collaboration Data Index

This is the entry point for collaborators. Each delivery follows:

```text
data/<device>/<snapshot>/
```

Read the snapshot `README.md` before using its CSV files. It defines scope,
deduplication, fields, coverage, and collection limitations.

## Available snapshots

| Device | Snapshot | Scope | Main tables | Current scale |
|---|---|---|---|---|
| A | [`20260713_full_recon_comments`](device_a/20260713_full_recon_comments/) | E001-E003 full-recon comments; 22 completed keyword batches | `comments_unified.csv`, `notes_unified.csv`, `actor_commenter_seed.csv` | 18,942 deduplicated comments; 246 notes |
| C | [`20260715_device_c_collection`](device_c/20260715_device_c_collection/) | E008-E010 first-level comments | `device_c_comments_unified.csv`, `device_c_notes_unified.csv` | 21,676 comments; 87 notes |

## Recommended use

1. Use each snapshot's `*_comments_unified.csv` as the primary comment table.
2. Join notes with `event_id` and `note_id`; check the snapshot README for any
   device-specific key or field convention.
3. Use raw or non-deduplicated files only for audit and replay. They can contain
   repeated observations from more than one successful collection batch.
4. Keep device snapshots separate unless a downstream analysis has explicitly
   normalized their schemas and collection scope.

## Data boundary

All snapshots contain only content and IP-region labels publicly available during
collection. Empty IP-region fields mean the platform did not return a label; they
must not be interpreted as a physical location. The repository should remain private,
and collaborators must follow applicable platform rules and data-use requirements.
