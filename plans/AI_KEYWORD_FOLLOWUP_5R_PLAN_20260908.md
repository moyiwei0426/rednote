# AI 关键词后续时间补充：五地搜索 + 一次集中深采

## 1. 任务标识与范围

- 任务 ID：`AIKF-20260908`。
- 数据集 ID：`xhs_ai_keyword_followup_20260705_20260908`。
- 时间窗：北京时间 `2026-07-05 00:00:00` 至 `2026-09-08 23:59:59`，首日紧接旧任务的 `2026-07-04` 上界，不重叠。
- 五地搜索：广州、上海、北京、武汉、成都各启动 **一次** 搜索会话；每次会话串行跑完基于官方发布日期冻结的 6 个事件关键词。
- 集中深采：五地搜索全部结束后，对全局去重的帖子只启动 **一次** 深采任务；深采地点由当次出口、CDP 与登录均预检通过的设备确定，不把同一帖子交给五地重复请求。

这里的“一次”是一次可审计的任务会话/任务链，而不是单个 HTTP 请求。搜索和评论均有分页；评论会话需在同一任务目录保留断点、台账和原始 JSONL。若验证码、登录失效或平台不可访问造成缺口，保留缺口并在质量表标注，不将无证据的数据写成完整。

## 2. 与旧任务的明确区分

| 维度 | 旧首轮 | 本次后续补充 |
| --- | --- | --- |
| 正式方案 | `xhs_core_event_collection_plan.md` | 本文件 |
| 实际运行 | `runs/xhs_ai_hot_30_20260424_20260703/` | `runs/xhs_ai_keyword_followup/AIKF-20260908/` |
| 时间窗 | 方案上界 `2026-07-04`；实际运行名为 `20260424_20260703` | `2026-07-05`–`2026-09-08` |
| 主题策略 | 30 个候选主题、三阶段筛选 | 6 个延续关键词、五地一次搜索后集中深采 |
| 已知落地状态 | 81 篇去重笔记、600 条去重一级评论；仅 6/30 主题有笔记，因验证码暂停 | 新任务，初始状态均为 `planned`，不得把旧行数计入 |
| 地区层 | 无五地搜索曝光关系 | 保留五地 `note_region_exposures.csv`，再全局去重 |
| 存储与合并 | `ai_hot_30_*` 文件名 | 全部使用 `followup` 前缀；只产出关联表，不覆盖旧 CSV/JSONL |

旧计划同时规定了“事件相关性/非营销”筛选与笔记、评论字段标准；这些规则和字段在本任务中复用。旧任务中未完成或 `pending_retry` 的主题不迁入本任务，避免把“新时间段补充”误写为“旧缺口补抓”。

## 3. 由发布事件冻结关键词（不做关键词侦察）

关键词登记在 `configs/xhs_ai_keyword_followup_20260705_20260908.csv`。先以厂商公开发布日期和正式产品名称冻结事件表，再以该名称作为平台采集关键词；不运行“先搜平台热词、再决定关键词”的独立侦察阶段。平台内查询仍是内容采集步骤，而不是关键词发现步骤。

| ID | 发布事件 | 发布日 | 采集关键词 | 保留条件 |
| --- | --- | --- | --- |
| F001 | GPT-5.6 | 2026-07-09 | `GPT-5.6` | 明确讨论该模型或其可用性、价格、能力变化 |
| F002 | Kimi K3 | 2026-07-16 | `Kimi K3` | 明确讨论该模型或其使用变化 |
| F003 | DeepSeek-V4-Pro GA | 2026-08-13 | `DeepSeek V4 Pro` | 明确讨论该版本的能力、价格或应用变化 |
| F004 | DeepSeek-V4-Flash-Vision-Exp | 2026-08-21 | `DeepSeek V4 Flash Vision` | 明确讨论该版本的能力或应用变化 |
| F005 | Claude Fable 5.1 / Mythos 5.1 | 2026-09-01 | `Claude Fable 5.1` | 明确讨论该模型能力或可用性变化 |
| F006 | GPT-6 Astra | 2026-09-03 | `GPT-6 Astra` | 明确讨论该模型能力或可用性变化 |

每个事件的采集窗口从其发布日开始，不早于旧数据截止日；当前计划的观察上界为 `2026-09-08`。如以“评论接近冻结”为深采门槛，使用发布日后约 70 天：F001 最早可于 `2026-09-17` 深采，F006 最早可于 `2026-11-12` 深采。关键词已冻结，不因平台热词而临时添加、删除或替换。

## 4. 运行目录与产物隔离

```text
runs/xhs_ai_keyword_followup/AIKF-20260908/
  search/<region>/
    F001/ ... F006/                 # batch_meta、crawler.log、raw search JSONL、分页状态
  deliveries/<region>-search-v1/
  deliveries/five-region-search-v1/
    relations/note_region_exposures.csv
    quality/search_pagination_status.csv
    quality/five_region_comparison.csv
    manifest.json
  worklists/
    note_region_assignments.csv
    selected_notes_global.csv
  deep/global_once/
    batch_ledger.csv
    xhs/jsonl/detail_contents_*.jsonl
    xhs/jsonl/search_comments_*.jsonl
    xhs/jsonl/search_sub_comments_*.jsonl
    quality/pagination_status.jsonl
  merged/
    followup_notes_unified.csv
    followup_comments_unified.csv
    followup_note_region_exposures.csv
    followup_propagation_edges.csv
    followup_event_phase_summary.csv
    followup_quality_summary.csv
    cross_round_note_match.csv
```

`cross_round_note_match.csv` 只记录新旧数据集的 `note_id` 是否相同和匹配原因，不把新数据附加进旧 CSV；它用于证明两轮的隔离与可连接性。

## 5. 执行顺序

### A. 五地预检与事件表冻结

每地先验证实际国内出口、CDP websocket（通过 `/json/version`）、小红书登录状态和 dry-run。浏览器 profile 名称、代理标签或进程存活均不能替代真实出口验证。预检失败的地区不启动平台请求，也不更改系统代理或 GPT/新加坡规则代理。预检通过后，将本文件的 6 行事件表连同官方来源 URL 写入任务元数据；不另行进行关键词侦察。

### B. 五地各一次搜索

每地按 F001–F006 依次运行一次；每个事件只检索其对应的冻结关键词，并按“发布日至 2026-09-08”的事件时间窗过滤。每词保留原始搜索卡、页码、排名、采集时间与终止状态。

- 每地一条 worker，`max_concurrency=1`。
- 页面间隔 30 秒；每 5 页冷却 1,800 秒；关键词间冷却 600 秒。
- 连续两页早于窗口时记录 `two_pages_before_window`；接口自然耗尽时记录 `has_more_false`。
- CAPTCHA/`Verifytype`、登录失效或不可恢复错误时停止该地区搜索并保留已写入证据。是否另开补救任务由后续授权决定，不在本任务内把无完成证据标成成功。

### C. 全局去重和集中深采

1. 合并五地搜索为 `note_region_exposures.csv`。同一 `note_id` 在多个地区或关键词的出现均保留。
2. 对 `note_id` 全局去重，生成 `selected_notes_global.csv`；每帖保留 `source_regions`、`source_keywords` 与代表性 URL。
3. 在唯一一台预检通过的集中深采设备上，对 `selected_notes_global.csv` 中的每篇有效帖子只请求一次：保存详情、全部可访问一级评论，并对有回复入口的一级评论拉取至二级分页结束。
4. 每篇单批、并发 1；页面间隔 15–30 秒、批后冷却 600 秒、评论超过 500 条则冷却 1,200 秒、每 6 篇额外冷却 1,800 秒。
5. 分页异常、空文件、超时或验证码不得仅凭 `ledger=ok` 判完成；部分输出须隔离到 `incomplete_attempts_<timestamp>/`，质量表记录缺口。

## 6. 数据格式与链路验收

笔记和评论沿用旧计划第 8 节字段，并新增以下隔离/地区字段：

- 全表必加：`dataset_id`、`run_id`、`analysis_window_start`、`analysis_window_end`、`collected_at_bj`。
- 笔记必加：`search_regions`、`source_keywords`、`assigned_collection_device`、`is_relevant`、`is_marketing`。
- 评论必加：`source_regions`、`assigned_collection_device`、`comment_level`、`parent_comment_id`。
- 链路表 `followup_propagation_edges.csv`：`edge_type`、`source_id`、`target_id`、`event_time_bj`、`region_id`、`evidence_file`；只允许 `region_to_note`、`note_to_comment`、`comment_to_reply` 三种边。

验收必须同时满足：

1. 五地共 30 条关键词分页状态均有终止证据；中断项单列为缺口。
2. `note_region_exposures.csv` 与 `selected_notes_global.csv` 的去重关系可复算；集中深采不重复请求同一 `note_id`。
3. 详情、一级评论、二级回复的 JSONL、分页质量、`crawler.log` 与 `batch_ledger.csv` 相互一致。
4. 每条评论存在对应笔记；每条回复的 `parent_comment_id` 存在且同属一个 `note_id`。
5. `followup_quality_summary.csv` 分开给出“结构有效性”和“覆盖完整性”，并明确任何 CAPTCHA、登录失效、不可访问帖子及未闭合分页。

## 7. 非目标

- 不改写、覆盖或把 `followup_*` 数据直接追加到旧 `ai_hot_30_*` 文件。
- 不将旧数据的 81 篇笔记/600 条评论算入本任务的采集总量。
- 不采集关注、粉丝、点赞、私信等社会关系；仅保存研究所需的匿名哈希与公开内容/统计字段。
