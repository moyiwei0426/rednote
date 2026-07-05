# GitHub 同步与数据存储流程

本项目建议使用 **GitHub 私有仓库**。代码、配置和脱敏/统一 CSV 可以长期保存在仓库里；原始爬虫输出只建议以私有 raw archive 形式保存，不能放公开仓库。

## 1. 推荐仓库结构

```text
.
├── MediaCrawler/
├── configs/
├── scripts/
├── tools/
├── github_data/
│   └── gaokao_2026_firstpass/
│       ├── notes_unified.csv
│       ├── comments_unified.csv
│       ├── actor_commenter_seed.csv
│       ├── event_phase_summary.csv
│       ├── representative_notes.csv
│       ├── data_inventory.csv
│       └── README.md
└── runs/                 # 默认不提交，原始本地采集目录
```

## 2. 生成 GitHub 可存储数据

只导出统一 CSV：

```bash
python3 scripts/xhs_prepare_github_data.py \
  --run-dir runs/xhs_baseline_events/gaokao_2026_firstpass \
  --export-name gaokao_2026_firstpass
```

如果仓库确认是私有，并且你确实要保存原始采集目录：

```bash
python3 scripts/xhs_prepare_github_data.py \
  --run-dir runs/xhs_baseline_events/gaokao_2026_firstpass \
  --export-name gaokao_2026_firstpass_private \
  --include-raw-zip
```

`--include-raw-zip` 会生成 `raw_run_archive.zip`，只适合私有仓库。

## 3. 首次同步到 GitHub

先在 GitHub 创建一个私有仓库，然后运行：

```bash
REMOTE_URL=git@github.com:<owner>/<repo>.git scripts/xhs_github_sync.sh
```

或 HTTPS：

```bash
REMOTE_URL=https://github.com/<owner>/<repo>.git scripts/xhs_github_sync.sh
```

## 4. 后续更新

每次采集结束后：

```bash
scripts/xhs_merge_received.sh

python3 scripts/xhs_prepare_github_data.py \
  --run-dir runs/xhs_baseline_events/gaokao_2026_firstpass \
  --export-name gaokao_2026_firstpass

scripts/xhs_github_sync.sh
```

## 5. 读取数据

其他电脑拉取仓库：

```bash
git clone git@github.com:<owner>/<repo>.git
cd <repo>
```

然后直接读取：

```text
github_data/<export_name>/notes_unified.csv
github_data/<export_name>/comments_unified.csv
github_data/<export_name>/actor_commenter_seed.csv
```

## 6. 注意

- 不要把 `runs/` 直接加入 git。
- 不要把公开仓库用于保存 raw archive。
- `representative_note_urls_for_collection.csv` 是操作用 URL 种子文件，可能含访问参数，不进入默认 GitHub 数据导出。
- 最终建模优先读取 `github_data/` 下的统一 CSV。
