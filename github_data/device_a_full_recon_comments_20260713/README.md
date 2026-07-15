# Device A Full-Recon Comments Export

导出日期：2026-07-13

来源：设备 A 的 `full-recon-comments` 任务。E001、E002、E003 共 22 个关键词批次均已完成，且每个完成批次都存在非空评论输出。

## 推荐读取顺序

1. `comments_unified.csv`：主分析表。按 `comment_id` 去重后的评论事件，共 18,942 条。
2. `notes_unified.csv`：关联的笔记表，共 246 条。用 `event_id`、`phase_id`、`note_id` 与评论表连接。
3. `actor_commenter_seed.csv`：匿名评论者聚合种子表，共 16,569 条，用于下游画像或 agent 分析。
4. `event_phase_summary.csv`：三个事件阶段的质量与覆盖概览。
5. `keyword_collection_summary.csv`：22 个关键词批次的完成状态与输出位置。

## 其他文件

- `comments_raw_latest_ok.csv`：每个关键词最新成功批次的原始评论记录，共 31,653 条；可能含同一评论在不同抓取范围中的重复记录。需要保留原始采集粒度时使用。
- `export_summary.csv`：本次导出指标汇总。

## 关键字段

`comments_unified.csv` 的核心字段：

- `event_id`、`phase_id`：事件和阶段标识。
- `note_id`、`comment_id`、`parent_comment_id`：笔记、评论和父评论关联键。
- `comment_text`、`comment_time`、`comment_date_bj`：评论正文与北京时间。
- `comment_like_count`：评论获赞数。
- `commenter_region`：平台公开展示的评论者 IP 属地文本；为空表示未公开或未返回，不代表真实地址。
- `commenter_anonymous_hash`：由采集到的评论者标识生成的不可逆匿名键，用于跨表关联，不是平台用户 ID。

`notes_unified.csv` 包含笔记标题、正文、作者公开 IP 属地、互动计数、发布时间、关键词和事件阶段信息。`actor_commenter_seed.csv` 保留匿名评论者在事件/阶段中的评论次数、时间范围、公开属地汇总及互动聚合，不包含原始平台账号链接。

## 数据边界

数据仅覆盖采集时可公开访问的笔记与评论。已删除、私密、平台隐藏或因访问限制未返回的内容不在其中。请将本仓库保持为私有仓库，并遵守平台规则及适用的数据使用要求。
