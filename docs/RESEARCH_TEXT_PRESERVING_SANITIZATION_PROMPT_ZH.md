# 研究型文本保留脱敏：标准提示词

下面的提示词用于把采集结果整理成可提交到 GitHub、可在其他设备继续做文本分析的研究数据。核心原则是：**保留公开文本，删除身份与访问凭据；不得用整段哈希替代标题、正文或评论。**

```text
你是一名研究数据工程师。请对本次公开社交媒体采集结果执行“研究型文本保留脱敏”，生成一个新的公开交付目录。原始目录必须只读，不得覆盖、删除或改写任何原始文件。

一、目标
1. 保留能够支持文本分析、传播链路分析和复核的数据。
2. 删除登录凭据、签名参数、设备信息和可识别个人身份的信息。
3. 通过目标、帖子、评论、父子关系和分页状态五层对账证明数据完整性。
4. 缺失值必须保持为空，不能把“未知/未返回”改成数值 0。

二、必须保留
1. 任务与区域字段：event_id、event_name、phase_id、phase_name、source_keyword、region、batch/chunk、目标序号、采集终态。
2. 帖子字段：note_id、无查询参数的公开标准 URL、title、desc、tag_list、发布时间、公开互动量、内容类型。
3. 评论字段：note_id、comment_id、parent_comment_id、comment_text、评论时间、公开点赞量、公开属地、is_reply、sub_comment_count、内容类型。
4. 关系字段：一级/二级评论标记、父评论关系、悬空父关系标记；不得为了“看起来完整”而虚构父评论。
5. 质量字段：目标完成状态、分页状态、停止原因的安全分类、去重规则、行数、唯一键、缺失文本、悬空父关系、敏感片段替换计数。

三、必须删除或替换
1. 删除 cookie、authorization、Bearer token、session、二维码、浏览器 profile、账号口令、代理凭据、真实出口 IP、设备端口、设备标识、绝对本地路径和采集日志。
2. 删除 xsec_token、签名参数、带访问参数的 URL、图片/视频 CDN 原始地址；帖子 URL 仅保留无查询参数的公开标准链接。
3. 删除 nickname、原始 creator/user 标识及其他直接身份字段。
4. 如研究确需跨行识别同一公开作者/评论者，只能使用 HMAC-SHA256 生成稳定匿名 ID；密钥必须随机生成并保存在仓库之外，禁止提交密钥，禁止直接使用无密钥 SHA-256 处理原始身份值。
5. 公开属地只保留省级或国家级值，不保留城市、区县或更细位置。
6. 对公开文本中的邮箱、手机号、身份证号、银行卡号、带语境的微信/QQ 号、URL 和 @账号做片段级替换，分别替换为 [EMAIL]、[PHONE]、[ID]、[BANK_CARD]、[CONTACT]、[URL]、[MENTION]；保留文本其余内容，并记录 text_redacted、pii_redaction_count、pii_types。

四、禁止事项
1. 禁止把 title、desc、tag_list 或 comment_text 整体哈希后作为公开文本的替代品。
2. 禁止因为评论文本为空就删除该行；带图片但无文字的评论标记为 image_only。
3. 禁止把不可访问目标从工作表中删除；应保留 terminal status，并与有内容目标分开统计。
4. 禁止把重复采集行直接相加。

五、去重规则
1. 工作目标唯一键：(phase_id, note_id)，并验证 note_id 在冻结名单中全局唯一时可同时报告全局唯一数。
2. 帖子唯一键：note_id；优先保留 last_modify_ts 较新且文本更完整的记录。
3. 评论唯一键：(note_id, comment_id)；优先保留 last_modify_ts 较新且文本/图片状态更完整的记录。
4. 分页唯一键：(note_id, kind, root_comment_id)；保留 recorded_at 最新记录。
5. 多设备进度按 (phase_id, chunk) 合并；终态优先于非终态，相同终态取 finished_at 最新记录。

六、最少交付文件
1. worklist.csv：冻结目标清单。
2. collection_completion.csv：每个目标一条有效终态。
3. notes_unified.csv：去重后的公开帖子文本与元数据。
4. comments_unified.csv：去重后的一级、二级评论文本与关系。
5. pagination_status.csv：最新分页证据。
6. event_phase_summary.csv：每个事件/阶段的目标、帖子、评论与终态统计。
7. quality_summary.json：唯一键、文本完整度、父子关系、分页、PII 替换和异常统计。
8. data_inventory.csv：文件行数、字节数和 SHA-256。
9. manifest.json：边界、口径、计数、隐私策略和完成声明。
10. README.md：人可读说明、已知限制和复用方法。

七、提交前验收
1. 冻结目标数 = completion 唯一目标数 = 各终态数量之和。
2. notes.note_id 必须属于工作目标，且 note_id 唯一。
3. comments 的 (note_id, comment_id) 唯一，且每条评论所属帖子必须存在于 notes。
4. 一级评论数 + 二级评论数 = 评论总数。
5. 明确报告非空标题、非空正文、非空评论、image_only、空文本、悬空父关系数量。
6. 明确报告 pagination 各状态数量；不能仅凭进程或日志声称“完成”。
7. 扫描交付目录，确认不含 xsec_token、cookie、authorization、Bearer、代理凭据、绝对本地路径、带签名查询参数的 URL、nickname 和原始身份字段。
8. 抽查 CSV 可用 UTF-8 正确打开，多行文本保持在同一单元格，行数与 manifest、quality_summary 和 README 一致。
9. 最终输出明确区分：公开文本已保留；身份与访问凭据已删除；哪些值因平台不可访问而缺失；哪些关系是观察到但父行未落盘。
```

这套口径适用于本仓库国际版/RedNote 后续数据。若某次研究伦理或协议要求更严格，可在此基础上减少公开字段，但不能在仍声称“可做文本分析”的同时把全部文本替换成哈希值。
