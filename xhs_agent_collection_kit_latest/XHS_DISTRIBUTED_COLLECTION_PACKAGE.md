# 小红书 Agent 模拟数据采集分发套件

这套项目用于把同一份小红书采集代码分发到多台电脑运行，再把各设备结果回收合并为统一 CSV。核心原则保持不变：

> 总量采集行为事件，有限采集匿名行为体画像，不采集真人链条身份。

## 1. 套件包含什么

- `MediaCrawler/`：实际采集引擎。
- `xhs_distributed_runner.py`：统一分布式运行入口。
- `xhs_unified_export.py`：统一 CSV 合并与字段标准化。
- `xhs_author_probe.py`：发帖作者公开画像抽样工具。
- `configs/*.csv`：事件清单、设备分工、高考基线清单。
- `scripts/xhs_device_setup.sh`：新电脑安装依赖。
- `scripts/xhs_device_run.sh`：每台设备统一运行。
- `scripts/xhs_device_status.py`：查看当前设备进度。
- `scripts/xhs_package_results.sh`：把单台设备结果打包回传。
- `scripts/xhs_merge_received.sh`：主机统一合并。
- `scripts/xhs_prepare_github_data.py`：生成 GitHub 可存储数据目录。
- `scripts/xhs_github_sync.sh`：提交并推送代码、配置和 GitHub 数据导出。
- `seed_data/`：可选的操作用代表笔记 URL 文件，仅用于请求，不进入最终建模数据。

## 2. 三台电脑怎么分工

默认配置在 `configs/xhs_device_assignments.csv`。

| 设备 | 账号标签 | 建议任务 |
|---|---|---|
| A | `account_a` | DeepSeek/OpenAI；或高考 B001_P2 |
| B | `account_b` | Claude 系列 |
| C | `account_c` | Qwen/豆包/Kimi；或其他观察事件 |

高考基线当前使用 `configs/xhs_gaokao_baseline_firstpass_manifest.csv`，AI 大模型事件使用 `configs/xhs_core_events_manifest.csv`。

## 3. 新电脑首次安装

解压 zip 后进入目录：

```bash
cd xhs_agent_collection_kit_YYYYMMDD_HHMMSS
scripts/xhs_device_setup.sh
```

然后打开 Chrome 并登录小红书。建议每台电脑使用独立 Chrome profile、独立账号、独立网络环境。

## 4. 先做 dry-run

```bash
DEVICE_ID=A \
ACCOUNT_ID=account_a \
STAGE=recon \
DRY_RUN=1 \
scripts/xhs_device_run.sh
```

dry-run 只写命令和账本，不真正请求小红书。

## 5. AI 大模型事件采集

侦察笔记：

```bash
DEVICE_ID=A ACCOUNT_ID=account_a STAGE=recon RUN_ID=ai_core_20260705 scripts/xhs_device_run.sh
```

评论试采：

```bash
DEVICE_ID=A ACCOUNT_ID=account_a STAGE=pilot-comments RUN_ID=ai_core_20260705 EVENT_IDS=E001 scripts/xhs_device_run.sh
```

核心深采：

```bash
DEVICE_ID=A ACCOUNT_ID=account_a STAGE=deep-comments RUN_ID=ai_core_20260705 EVENT_IDS=E001,E002,E003 scripts/xhs_device_run.sh
```

建议每次只跑少量事件，并设置较长间隔：

```bash
SLEEP_BETWEEN_KEYWORDS=900 SLEEP_BETWEEN_BATCHES=300 MAX_CONCURRENCY=1
```

## 6. 高考基线 selected-comments 采集

如果主机已经生成了代表笔记 URL 文件，将该文件放到每台电脑，例如：

```text
seed_data/gaokao_2026_firstpass_representative_note_urls_for_collection.csv
```

设备 A 继续采 B001_P2 的 31-40：

```bash
DEVICE_ID=A \
ACCOUNT_ID=account_a \
STAGE=selected-comments \
RUN_ID=gaokao_2026_firstpass \
MANIFEST=configs/xhs_gaokao_baseline_firstpass_manifest.csv \
RUN_ROOT=runs/xhs_baseline_events \
SELECTED_NOTES_FILE=seed_data/gaokao_2026_firstpass_representative_note_urls_for_collection.csv \
SELECTED_PHASE_IDS=B001_P2 \
NOTES_PER_BATCH=1 \
COMMENTS_PER_NOTE=80 \
SLEEP_BETWEEN_BATCHES=180 \
MAX_BATCHES=40 \
scripts/xhs_device_run.sh
```

设备 B 或 C 可以负责后续区间，例如把 `MAX_BATCHES` 改成 50 或 62。脚本会跳过已经有评论输出的 chunk；如果是全新设备，没有已有输出，则应由主机预先分配不同阶段、不同事件或不同 selected note 文件，避免重复请求同一批笔记。

## 7. 发帖作者公开画像

只建议在核心事件已经筛定后运行：

```bash
DEVICE_ID=A \
ACCOUNT_ID=account_a \
STAGE=author-profiles \
RUN_ID=ai_core_20260705 \
AUTHOR_POST_LIMIT=20 \
scripts/xhs_device_run.sh
```

作者画像只保留匿名哈希、公开统计、区间值和类型字段。不要采关注列表、粉丝列表、点赞列表、私密内容。

## 8. 查看设备状态

```bash
python3 scripts/xhs_device_status.py \
  --run-root runs/xhs_baseline_events \
  --run-id gaokao_2026_firstpass \
  --device-id A
```

## 9. 单设备结果打包回传

```bash
RUN_ROOT=runs/xhs_baseline_events \
RUN_ID=gaokao_2026_firstpass \
DEVICE_ID=A \
scripts/xhs_package_results.sh
```

输出 zip 在 `dist/device_results/`。把这个 zip 回传到主机后，在主机解压到同一个项目根目录。

## 10. 主机合并统一 CSV

```bash
RUN_ROOT=runs/xhs_baseline_events \
RUN_ID=gaokao_2026_firstpass \
MANIFEST=configs/xhs_gaokao_baseline_firstpass_manifest.csv \
REPRESENTATIVE_NOTES_PER_PHASE=120 \
scripts/xhs_merge_received.sh
```

输出：

- `notes_unified.csv`
- `comments_unified.csv`
- `actor_commenter_seed.csv`
- `event_phase_summary.csv`
- `representative_note_urls_for_collection.csv`

## 11. 风控规则

- `MAX_CONCURRENCY=1`。
- selected-comments 建议 `NOTES_PER_BATCH=1`。
- 每批间隔至少 180 秒；账号不稳时提高到 300-600 秒。
- 触发验证码立即停止，冷却 3-6 小时。
- 不要多台电脑同时抢同一批 URL。
- 不要采集原始身份链条、关注链条、点赞链条。

## 12. 打包分发 zip

在主机运行：

```bash
python3 tools/build_xhs_collection_package.py
```

生成的 zip 在 `dist/` 下。默认包含代码、配置、脚本、文档和高考代表笔记操作用种子文件；不包含已有 `runs/` 原始采集数据。

## 13. GitHub 存储与同步

建议使用私有 GitHub 仓库。默认同步代码、配置、文档和 `github_data/` 下的统一 CSV，不直接提交 `runs/` 原始采集目录。

生成 GitHub 可读取数据：

```bash
python3 scripts/xhs_prepare_github_data.py \
  --run-dir runs/xhs_baseline_events/gaokao_2026_firstpass \
  --export-name gaokao_2026_firstpass
```

如果仓库确认是私有，并且需要长期保存原始采集目录，可加：

```bash
python3 scripts/xhs_prepare_github_data.py \
  --run-dir runs/xhs_baseline_events/gaokao_2026_firstpass \
  --export-name gaokao_2026_firstpass_private \
  --include-raw-zip
```

首次推送：

```bash
REMOTE_URL=git@github.com:<owner>/<repo>.git scripts/xhs_github_sync.sh
```

后续更新：

```bash
scripts/xhs_merge_received.sh
python3 scripts/xhs_prepare_github_data.py --run-dir runs/xhs_baseline_events/gaokao_2026_firstpass --export-name gaokao_2026_firstpass
scripts/xhs_github_sync.sh
```

详细说明见 `GITHUB_SYNC_RUNBOOK.md`。
