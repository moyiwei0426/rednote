# 北京必采任务同步记录

## 本次修改

- 同步日期：2026-08-24；
- 地区：北京；
- 事件：`GK2026D1`（2026 高考第一天）；
- 清单：`remaining_mandatory_notes_beijing.csv`；
- 采集方式：单篇串行、一体化采集正文、一级评论和二级回复；
- 完整边界：`chunk_020`；
- 下一步：北京必采任务无需续跑，五区协作库只保留尚未完成的北京共享帖子。

## 验收结果

- 20/20 篇帖子 ledger 最新状态均为 `ok`；
- 20 条帖子正文，`note_id` 无重复；
- 385 条公开评论，`comment_id` 无重复；
- 一级评论 227 条，二级回复 158 条；
- 247 条分页记录全部为 `complete / endpoint_exhausted`；
- 评论到帖子外键、二级回复到一级父评论关系均通过；
- CAPTCHA、验证码、失败和部分完成记录均为 0；
- 数据包不含 Cookie、浏览器目录、本地路径、代理密钥、完整出口 IP 或查询令牌。

## 文件修改

- 新增 `notes_public_full.csv`；
- 新增 `comments_public_full.csv`；
- 新增 `comment_pagination_status.csv`；
- 新增 `collection_worklist_status.csv`；
- 新增 `checkpoint_manifest.json`；
- 新增本 `COLLECTION_STATUS.md` 和字段说明 `README.md`。

各 CSV 的字节数和 SHA-256 见 `checkpoint_manifest.json`。
