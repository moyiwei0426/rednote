# 北京高考第一天深采完成包

本目录是北京地区 `GK2026D1`（2026 高考第一天）必须由北京出口采集清单的完整检查点。
每篇帖子在同一批次中完成正文、全部公开一级评论和全部公开二级回复采集。

## 完成情况

- 必采帖子：20/20 篇；
- 帖子正文：20 条；
- 公开评论：385 条，其中一级评论 227 条、二级回复 158 条；
- 评论公开 IP 属地：385/385 条有值；
- 发帖者公开 IP 属地：0/20 条有值，平台未返回时按规则保留空值；
- 评论分页证据：247 条，全部为 `complete / endpoint_exhausted`；
- 缺失、部分完成和待恢复帖子：0 篇。

## 文件说明

### `notes_public_full.csv`

每行代表一篇帖子。

| 字段 | 含义 |
| --- | --- |
| `chunk_index` | 本次北京必采队列中的批次序号 |
| `collection_status` | 采集状态，本包均为 `complete` |
| `event_id` / `event_name` | 事件编号与名称 |
| `phase_id` / `phase_name` | 所属采集阶段编号与名称 |
| `note_id` | 小红书帖子唯一标识 |
| `note_url` | 已移除查询令牌的帖子公开链接 |
| `type` | 帖子类型，如图文或视频 |
| `title` / `desc` | 帖子标题与正文 |
| `time` / `last_update_time` | 平台返回的发布时间与更新时间 |
| `creator_hash` / `nickname` | 脱敏作者标识与公开昵称 |
| `liked_count` | 点赞数 |
| `collected_count` | 收藏数 |
| `comment_count` | 平台展示的评论数 |
| `share_count` | 分享数 |
| `image_list` | 平台返回的公开图片地址列表 |
| `tag_list` | 帖子话题标签 |
| `source_keyword` | 详情响应中的来源关键词；可能为空 |
| `public_ip_location` | 平台公开展示的作者粗粒度 IP 属地；未返回则为空 |
| `last_modify_ts` | 本地记录最后修改时间戳 |

### `comments_public_full.csv`

每行代表一条一级评论或二级回复。

| 字段 | 含义 |
| --- | --- |
| `chunk_index` / `collection_status` | 所属帖子批次与完成状态 |
| `event_id` | 事件编号 |
| `note_id` | 评论所属帖子标识 |
| `comment_id` | 评论唯一标识 |
| `parent_comment_id` | 二级回复对应的一级父评论；一级评论为空 |
| `create_time` | 评论发布时间 |
| `content` | 评论公开文本 |
| `creator_hash` / `nickname` | 脱敏评论者标识与公开昵称 |
| `like_count` | 评论点赞数 |
| `sub_comment_count` | 平台声明的二级回复数量，不单独作为完整性证据 |
| `pictures` | 评论附图地址 |
| `public_ip_location` | 平台公开展示的评论者粗粒度 IP 属地 |
| `last_modify_ts` | 本地记录最后修改时间戳 |

### `comment_pagination_status.csv`

记录每篇帖子一级评论分页和每条一级评论的二级回复分页证据。

| 字段 | 含义 |
| --- | --- |
| `kind` | `top_level` 表示一级评论分页，`reply` 表示某一级评论下的回复分页 |
| `note_id` | 所属帖子标识 |
| `root_comment_id` | 二级分页对应的一级评论标识；一级分页为空 |
| `status` / `stop_reason` | 分页状态与终止原因；完整值为 `complete / endpoint_exhausted` |
| `pages` | 实际请求页数 |
| `observed_comments` | 本次分页观察到的评论数量 |
| `declared_comments` | 平台声明的评论数量 |
| `collection_egress_region` / `collection_egress_id` | 采集出口地区与不含完整 IP 的出口标识 |
| `collection_account_id` / `collection_cdp_port` | 隔离采集账号标识与浏览器调试端口 |
| `chunk_index` / `collection_status` / `event_id` | 队列序号、完成状态与事件编号 |
| `unlimited` | 是否启用无限制分页，本包为真 |
| `error` | 分页错误信息；正常完成时为空 |

### 其他文件

- `collection_worklist_status.csv`：20 篇帖子逐篇状态、来源地区、关键词和评论数量；
- `checkpoint_manifest.json`：全包行数、覆盖率、数据边界及各 CSV 的 SHA-256；
- `COLLECTION_STATUS.md`：本次 GitHub 同步的完成边界和验收摘要。

## 关系与主键

- 帖子主键：`note_id`；
- 评论主键：`comment_id`；
- 评论到帖子：`comments_public_full.note_id -> notes_public_full.note_id`；
- 二级回复到一级评论：`parent_comment_id -> comment_id`，且必须处于同一 `note_id`；
- 同一帖子只保存一次，但其地区与关键词来源保留在 `collection_worklist_status.csv`。

## 数据边界

仅包含平台公开返回的数据。未上传 Cookie、浏览器登录目录、本地绝对路径、代理密钥、
完整出口 IP 或 `xsec_token`；帖子链接统一移除查询令牌。IP 属地仅使用平台公开展示值，
不补全、不地理编码，也不从文本推断。
