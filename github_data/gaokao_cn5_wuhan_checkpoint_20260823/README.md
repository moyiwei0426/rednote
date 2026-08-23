# 武汉设备高考数据停止点存档

本目录是武汉设备 `GK2026D1` 采集任务在 2026-08-23 停止后的可续采检查点。

## 当前进度

- 任务清单：199 篇帖子
- 完整采集：96 篇
- 部分采集：1 篇（chunk 097）
- 尚未采集：102 篇
- 完整数据：96 条帖子记录、7,227 条去重评论
- 评论层级：2,661 条一级评论、4,566 条二级回复
- chunk 097 部分数据：1 条帖子记录、639 条去重评论

## 文件说明

- `notes_public_full.csv`：96 个完整批次的帖子公开数据。
- `comments_public_full.csv`：96 个完整批次的全部已采公开评论及层级关系。
- `partial_notes_public_full.csv`：chunk 097 的部分帖子数据，不计入完整样本。
- `partial_comments_public_full.csv`：chunk 097 的部分评论，续采后按 `comment_id` 去重合并。
- `collection_worklist_status.csv`：199 篇帖子逐篇状态，是后续续采的唯一进度依据。
- `comment_pagination_status.csv`：完整批次及部分批次的分页质量记录。
- `checkpoint_manifest.json`：数据量、字段边界及文件校验值。

## 续采规则

从 `chunk_097` 对应的帖子重新采集。该帖从评论第一页开始，完成后按 `comment_id` 与
`partial_comments_public_full.csv` 去重合并；然后按照工作清单依次处理 `chunk_098` 至
`chunk_199`。不得把 `partial` 状态直接改为 `complete`，必须以分页完成状态为准。

## 数据边界

本检查点不做研究字段脱敏，保留公开昵称、公开 IP 属地、正文、评论文本、时间、点赞数、
帖子及评论 ID 和父子评论关系。为防止账号凭证泄露，GitHub 包不包含 Cookie、浏览器登录
目录、采集日志或 `xsec_token`；帖子链接统一为不含查询令牌的固定链接。

