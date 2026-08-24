# 成都高考第一天深采完成包

本目录是成都地区 `GK2026D1`（2026 高考第一天）必须本区采集清单的完整检查点。

## 完成情况

- 必采帖子：55/55 篇；
- 帖子正文：55 条；
- 公开评论：3,042 条，其中一级评论 2,043 条、二级回复 999 条；
- 评论公开 IP 属地：3,041/3,042 条有值，空值表示平台未展示；
- 评论分页证据：2,098 条，全部为 `complete / endpoint_exhausted`；
- 缺失、部分完成和待恢复帖子：0 篇。

## 文件说明

- `notes_public_full.csv`：55 篇帖子的公开正文、作者、互动量和公开 IP 属地；
- `comments_public_full.csv`：全部公开一级与二级评论，使用 `parent_comment_id` 保留关系；
- `comment_pagination_status.csv`：一级及逐父评论二级分页完成证据；
- `collection_worklist_status.csv`：55 篇帖子逐篇状态和评论数量；
- `checkpoint_manifest.json`：行数、覆盖率、数据边界和 SHA-256。

## 数据边界

仅包含平台公开返回的数据。未上传 Cookie、浏览器登录目录、本地绝对路径、代理密钥、
完整出口 IP 或 `xsec_token`；帖子链接统一移除查询令牌。
