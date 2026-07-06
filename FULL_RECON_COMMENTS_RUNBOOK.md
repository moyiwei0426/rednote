# 小红书全量评论优先采集流程

本流程用于需要研究评论时间线、评论者公开 IP 属地、地域扩散和互动变化的任务。默认目标不再是“只采笔记后再筛选评论”，而是尽量在第一次访问笔记时同步采集可见一级评论，减少后续重复访问同一批笔记。

## 1. 推荐阶段

使用新增阶段：

```bash
STAGE=full-recon-comments
```

该阶段执行：

```text
搜索关键词 -> 采集笔记 -> 立即采集每条笔记的可见一级评论 -> 写入统一输出结构
```

保留旧阶段：

- `recon`：只采笔记，最低访问量，用于登录/风控测试。
- `pilot-comments`：旧的少量评论试采。
- `deep-comments`：旧的深度评论采集。
- `selected-comments`：对代表性笔记 URL 定向补采评论。

## 2. 默认参数

推荐低频全量一级评论配置：

```bash
DEVICE_ID=C \
ACCOUNT_ID=account_c \
STAGE=full-recon-comments \
RUN_ID=ai_core_$(date +%Y%m%d) \
COMMENTS_PER_NOTE=10000 \
SLEEP_BETWEEN_KEYWORDS=1200 \
MAX_CONCURRENCY=1 \
scripts/xhs_device_run.sh
```

参数含义：

- `COMMENTS_PER_NOTE=10000`：对每条笔记尽可能抓取平台接口可返回的一级评论。
- `SLEEP_BETWEEN_KEYWORDS=1200`：关键词之间间隔 20 分钟，降低风控概率。
- `MAX_CONCURRENCY=1`：单线程采集，稳定优先。
- `GET_SUB_COMMENT=false`：当前仍不抓二级回复，避免访问量暴增。
- `--stop-on-captcha`：触发验证码立即停止，冷却后再恢复。

## 3. 数据位置

统一导出后：

- 发帖者公开 IP 属地：`notes_unified.csv` 的 `public_ip_location`
- 评论者公开 IP/地区：`comments_unified.csv` 的 `commenter_region`
- 评论时间：`comments_unified.csv` 的 `comment_time` 和 `comment_date_bj`
- 评论者匿名键：`comments_unified.csv` 的 `commenter_anonymous_hash`

## 4. 恢复与避免重复

搜索阶段现在会按 `stage + event_id + keyword` 跳过已经成功完成的批次。中断后重新运行同一个 `RUN_ID` 时，默认不会重复采集已经 `ok` 的关键词。

如果某个关键词触发验证码或失败，它不会被标记为完成；冷却后重新运行同一命令即可补采剩余失败批次。

## 5. 全量边界

这里的“全量评论”指：

```text
小红书当前页面/接口可见、可分页返回的一级评论
```

以下情况无法保证采到：

- 评论被删除、隐藏或折叠。
- 平台接口不再返回历史评论。
- 登录状态失效、网络异常或验证码导致提前停止。
- 二级回复当前默认不采集。

如果研究必须包含二级回复，需要单独评估访问量和风控风险后再开启。

## 6. 后续补采

`full-recon-comments` 完成后仍应运行统一导出：

```bash
python3 xhs_unified_export.py \
  --run-dir runs/xhs_core_events/<RUN_ID>/device_<device_id> \
  --manifest configs/xhs_core_events_manifest.csv \
  --output-dir runs/xhs_core_events/<RUN_ID>/exports/<device_id>_unified
```

若导出后发现某些高互动笔记评论明显不足，再使用 `selected-comments` 对这些笔记补采，不需要重新跑关键词搜索。
