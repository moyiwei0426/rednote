# 小红书 2026 高考基线事件采集方案

## 1. 基线定位

高考基线不作为 AI 模型事件，而作为“全民生活周期事件”的对照组。目标是给 agent 模拟提供一组非技术热点的传播基准：同步爆发、强地域覆盖、强情绪表达、家庭/教育决策参与。

统一标识：

- `event_id`: `B001`
- `event_name`: `2026高考`
- `event_type`: `baseline_national_life_event`
- `phase_id`: `B001_P1` 至 `B001_P5`

## 2. 阶段划分

| phase_id | 阶段 | 时间窗口 | 采集重点 |
|---|---|---|---|
| B001_P1 | 备考祝福预热 | 2026-05-24 至 2026-06-06 | 高考加油、陪考、倒计时 |
| B001_P2 | 开考现场 | 2026-06-07 至 2026-06-10 | 开考、考场、家长陪考、结束 |
| B001_P3 | 考题讨论 | 2026-06-07 至 2026-06-12 | 作文、数学、考后吐槽 |
| B001_P4 | 查分晒分 | 2026-06-23 至 2026-06-27 | 查分、分数线、晒分 |
| B001_P5 | 志愿填报 | 2026-06-27 至 2026-07-04 | 志愿、选专业、报考决策 |

## 3. 高互动代表性采样

采集不是随机抓取，而是“高互动优先 + 阶段代表性 + 内容多样性”。

### 3.1 采集入口

每个阶段按关键词搜索，小红书搜索排序使用现有 `popularity_descending` 配置，优先取热度较高内容。

每个关键词建议：

- 侦察：30 条笔记。
- 深采：120-150 条笔记。
- 每条笔记评论：30-80 条一级评论。

### 3.2 后处理筛选

采完后统一计算代表性分数：

```text
representative_score = 点赞数 + 3 * 评论数 + 2 * 收藏数 + 2 * 分享数
```

每个阶段优先保留：

- 分数 Top 笔记。
- 评论数高的讨论型笔记。
- 有地区评论覆盖的笔记。
- 非营销内容。
- 不同内容类型：祝福、陪考、考题、晒分、志愿、经验、争议、营销。

### 3.3 反偏置规则

只按点赞 Top 会导致样本被官方号、教育营销号或单一爆款垄断。因此最终样本需满足：

- 每个阶段至少 100 条代表性笔记。
- 每个阶段营销内容比例单独标记，不直接删除。
- 每个阶段保留普通用户内容。
- 每个阶段保留高评论低点赞的讨论型内容。
- 地区信息不足的阶段需要补采。

## 4. 第一轮基线采集边界

第一轮先只采“行为事件层”，不采主页画像。

原因：

- 当前目标是给 AI agent 做基线研究，最重要的是让 agent 学到高考事件里的时间、地域、情绪、互动与内容类型分布。
- 笔记和评论本身已经能形成匿名行为轨迹：`creator_hash`、`commenter_anonymous_hash`、时间、地区、点赞、回复关系。
- 主页画像会显著增加请求量和风控风险，且会把研究从“传播行为”推向“个体身份刻画”。

第一轮保留：

- 高互动笔记。
- 评论文本。
- 评论时间。
- 评论地区。
- 评论点赞数。
- 匿名哈希。
- 是否回复与父评论。
- 笔记互动量与代表性分数。

第一轮不采：

- 发帖作者主页公开统计。
- 发帖作者历史公开作品。
- 评论者主页画像。
- 关注列表、粉丝列表、点赞列表。
- 原始身份标识。

但仍然保留 `commenter_anonymous_hash`。这不是“真人画像”，而是 agent 模拟所需的匿名行为体键，用来聚合“同一个匿名评论者在同一阶段是否多次出现、平均评论点赞、首次出现时间、地区是否变化”等行为特征。

## 5. 数据结构统一

高考基线沿用 AI 事件采集结构。

### 5.1 笔记统一表

字段：

- `event_id`
- `event_name`
- `phase_id`
- `phase_name`
- `event_type`
- `source_keyword`
- `note_id`
- `note_url_public`
- `title`
- `desc`
- `tag_list`
- `publish_time_bj`
- `publish_date_bj`
- `creator_hash`
- `nickname`
- `public_ip_location`
- `liked_count_num`
- `collected_count_num`
- `comment_count_num`
- `share_count_num`
- `representative_score`
- `representative_rank_in_phase`
- `is_representative_sample`
- `is_marketing`
- `content_type`
- `collected_device`
- `collected_account`
- `collected_at_bj`

### 5.2 评论统一表

字段：

- `event_id`
- `phase_id`
- `note_id`
- `comment_id`
- `parent_comment_id`
- `comment_text`
- `comment_time`
- `comment_date_bj`
- `comment_like_count`
- `commenter_region`
- `commenter_anonymous_hash`
- `is_reply`
- `sub_comment_count`
- `note_is_representative_sample`
- `collected_device`
- `collected_account`
- `collected_at_bj`

### 5.3 匿名行为种子表

字段：

- `actor_hash`
- `event_id`
- `phase_id`
- `actor_role`
- `comment_count_in_phase`
- `first_seen_time_bj`
- `regions_observed`
- `avg_comment_like`
- `max_comment_like`
- `dominant_comment_type`
- `sentiment_tendency`
- `knowledge_behavior_type`
- `sample_reason`

这张表由评论表聚合生成，不需要额外访问用户主页。它是 agent baseline 的轻量行为种子表，不是个人主页画像表。

## 6. 运行命令

第一轮只跑 `B001_P2` 和 `B001_P5`：

```bash
python3 xhs_distributed_runner.py \
  --manifest configs/xhs_gaokao_baseline_firstpass_manifest.csv \
  --run-root runs/xhs_baseline_events \
  --run-id gaokao_2026_firstpass \
  --device-id A \
  --account-id account_a \
  --stage recon
```

第一轮评论试采：

```bash
python3 xhs_distributed_runner.py \
  --manifest configs/xhs_gaokao_baseline_firstpass_manifest.csv \
  --run-root runs/xhs_baseline_events \
  --run-id gaokao_2026_firstpass \
  --device-id A \
  --account-id account_a \
  --stage pilot-comments
```

第一轮合并和代表性筛选：

```bash
python3 xhs_unified_export.py \
  --run-dir runs/xhs_baseline_events/gaokao_2026_firstpass \
  --manifest configs/xhs_gaokao_baseline_firstpass_manifest.csv \
  --output-dir runs/xhs_baseline_events/gaokao_2026_firstpass/merged \
  --representative-notes-per-phase 100
```

完整五阶段采集如下。

侦察阶段：

```bash
python3 xhs_distributed_runner.py \
  --manifest configs/xhs_gaokao_baseline_manifest.csv \
  --run-root runs/xhs_baseline_events \
  --run-id gaokao_2026_baseline \
  --device-id A \
  --account-id account_a \
  --stage recon
```

评论试采：

```bash
python3 xhs_distributed_runner.py \
  --manifest configs/xhs_gaokao_baseline_manifest.csv \
  --run-root runs/xhs_baseline_events \
  --run-id gaokao_2026_baseline \
  --device-id A \
  --account-id account_a \
  --stage pilot-comments
```

深采：

```bash
python3 xhs_distributed_runner.py \
  --manifest configs/xhs_gaokao_baseline_manifest.csv \
  --run-root runs/xhs_baseline_events \
  --run-id gaokao_2026_baseline \
  --device-id A \
  --account-id account_a \
  --stage deep-comments
```

合并并生成代表性样本：

```bash
python3 xhs_unified_export.py \
  --run-dir runs/xhs_baseline_events/gaokao_2026_baseline \
  --manifest configs/xhs_gaokao_baseline_manifest.csv \
  --output-dir runs/xhs_baseline_events/gaokao_2026_baseline/merged \
  --representative-notes-per-phase 120
```
