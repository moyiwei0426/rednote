# 小红书核心事件多设备采集运行说明

本说明用于把同一套采集计划复制到其他电脑运行。每台设备只需要改 `device-id` 和 `account-id`，输出目录、字段、批次元数据保持统一。

## 1. 文件

- 事件清单：`configs/xhs_core_events_manifest.csv`
- 统一运行脚本：`xhs_distributed_runner.py`
- 简易 shell 包装：`run_xhs_device.sh`
- 作者画像 probe：`xhs_author_probe.py`
- 正式采集计划：`xhs_core_event_collection_plan.md`

## 2. 设备分工

| 设备 | 默认事件 |
|---|---|
| A | DeepSeek / OpenAI |
| B | Claude |
| C | Qwen / 豆包 / Kimi / 应用对照 |

如需改分工，编辑 `configs/xhs_core_events_manifest.csv` 的 `assigned_device` 列。

## 3. 首次准备

在每台电脑上放置完整目录后：

```bash
cd "/Users/momo/Documents/media catch"
cd MediaCrawler
UV_DEFAULT_INDEX=https://pypi.org/simple uv sync
cd ..
```

然后确认 Chrome 远程调试已经开启并登录小红书。当前 MediaCrawler 配置默认连接 `9222` 端口的现有 Chrome。

## 4. 阶段 A：候选事件侦察

只抓笔记，不抓评论。每个关键词默认 20 条，关键词之间默认间隔 10 分钟。

```bash
python3 xhs_distributed_runner.py --device-id A --account-id account_a --stage recon --run-id main_20260704
python3 xhs_distributed_runner.py --device-id B --account-id account_b --stage recon --run-id main_20260704
python3 xhs_distributed_runner.py --device-id C --account-id account_c --stage recon --run-id main_20260704
```

想先试跑一个关键词：

```bash
python3 xhs_distributed_runner.py --device-id A --account-id account_a --stage recon --max-keywords 1 --sleep-between-keywords 0 --run-id test_20260704
```

## 5. 阶段 B：评论试采

每条笔记默认抓 30 条一级评论。

```bash
python3 xhs_distributed_runner.py --device-id A --account-id account_a --stage pilot-comments --run-id main_20260704
```

建议每台设备一次只跑少量事件：

```bash
python3 xhs_distributed_runner.py --device-id A --account-id account_a --stage pilot-comments --event-ids E001 --run-id main_20260704
```

## 6. 阶段 C：核心事件深采

每条笔记默认抓 80 条一级评论。仅对筛出的核心事件运行。

```bash
python3 xhs_distributed_runner.py --device-id A --account-id account_a --stage deep-comments --event-ids E001,E002,E003 --run-id main_20260704
python3 xhs_distributed_runner.py --device-id B --account-id account_b --stage deep-comments --event-ids E004,E005,E006 --run-id main_20260704
```

如触发验证码，脚本会检测日志中的验证码标记并停止。此时冷却 3-6 小时，不要立刻重跑。

## 7. 发帖作者画像采样

在某台设备已经跑过 `recon` 或 `deep-comments` 后，可以采该设备下的发帖作者公开统计和最近 20 条公开作品。

```bash
python3 xhs_distributed_runner.py --device-id A --account-id account_a --stage author-profiles --run-id main_20260704 --author-post-limit 20
```

如果某个核心事件作者数量较少，可改为 50：

```bash
python3 xhs_distributed_runner.py --device-id A --account-id account_a --stage author-profiles --run-id main_20260704 --author-post-limit 50
```

也可以直接指定已有的 notes CSV/JSONL：

```bash
python3 xhs_distributed_runner.py \
  --device-id A \
  --account-id account_a \
  --stage author-profiles \
  --run-id main_20260704 \
  --notes-file runs/xhs_ai_hot_30_20260424_20260703/xhs/jsonl/search_contents_2026-07-04.jsonl \
  --author-post-limit 20
```

作者画像阶段只保存匿名哈希、公开统计和区间化/可建模字段，不保存原始 user_id、头像、主页 URL、原始昵称或 xsec_token。

## 8. 输出目录

统一输出到：

```text
runs/xhs_core_events/<run_id>/
  device_a/
    recon/
    pilot-comments/
    deep-comments/
    author_profiles/
    batch_ledger.csv
  device_b/
  device_c/
```

每个关键词批次内有：

- `batch_meta.json`
- `crawler.log`
- `xhs/jsonl/search_contents_YYYY-MM-DD.jsonl`
- `xhs/jsonl/search_comments_YYYY-MM-DD.jsonl`，评论阶段才有

## 9. 不采集边界

最终研究数据集不保存：

- 原始 user_id
- redId
- 主页 URL
- 头像 URL
- 原始昵称
- xsec_token
- 关注列表
- 粉丝列表
- 点赞列表
- 私密或半私密内容

核心原则：

> 总量采集行为事件，有限采集匿名行为体画像，不采集真人链条身份。

## 10. 高考基线事件

高考基线使用单独事件清单：

- `configs/xhs_gaokao_baseline_manifest.csv`
- `XHS_GAOKAO_BASELINE_PLAN.md`

侦察阶段示例：

```bash
python3 xhs_distributed_runner.py \
  --manifest configs/xhs_gaokao_baseline_manifest.csv \
  --run-root runs/xhs_baseline_events \
  --run-id gaokao_2026_baseline \
  --device-id A \
  --account-id account_a \
  --stage recon
```

深采阶段示例：

```bash
python3 xhs_distributed_runner.py \
  --manifest configs/xhs_gaokao_baseline_manifest.csv \
  --run-root runs/xhs_baseline_events \
  --run-id gaokao_2026_baseline \
  --device-id A \
  --account-id account_a \
  --stage deep-comments
```

合并统一结构并筛选代表性高互动样本：

```bash
python3 xhs_unified_export.py \
  --run-dir runs/xhs_baseline_events/gaokao_2026_baseline \
  --manifest configs/xhs_gaokao_baseline_manifest.csv \
  --output-dir runs/xhs_baseline_events/gaokao_2026_baseline/merged \
  --representative-notes-per-phase 120
```
