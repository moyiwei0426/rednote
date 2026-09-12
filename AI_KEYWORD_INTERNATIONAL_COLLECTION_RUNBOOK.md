# AI 关键词五地补采与国际版 RedNote 运行手册

## 1. 任务边界

- 国内五地补采任务：`AIKF-20260908`，数据集 `xhs_ai_keyword_followup_20260705_20260908`；覆盖北京时间 `2026-07-05` 至 `2026-09-08`，与上一轮截止日 `2026-07-04` 不重叠。
- 固定事件关键词：`GPT-5.6`、`Kimi K3`、`DeepSeek V4 Pro`、`DeepSeek V4 Flash Vision`、`Claude Fable 5.1`、`GPT-6 Astra`。定义见 `configs/xhs_ai_keyword_followup_20260705_20260908.csv`；不得在平台内另行发现或替换关键词。
- 国内五地是广州、上海、北京、武汉、成都。每地每词只启动一条可恢复的搜索会话；搜索卡完成并全局去重后，详情和评论只在一个通过预检的设备上集中深采一次。
- 国际版是独立样本：使用 `rednote.com`/`webapi.rednote.com` 的账号、浏览器 profile、CDP 端口和 `runs/rednote_ai_keyword_followup/AIKF-INT-<日期>/` 目录。不得把国际版曝光直接写入国内 `region_to_note` 传播边；如需比较，单独标为 `platform=rednote_international`。

## 2. 其他电脑的准备

1. 拉取本分支（合并后改为 `main`），安装项目既有依赖；不要复制其他电脑的浏览器 profile、Cookie、`runs/`、日志或原始 JSONL。
2. 为该设备创建专用浏览器 profile，并以专用 CDP 端口启动 Chrome。例如国际版使用 9342，国内其余地点分别使用不同端口。登录必须由该电脑的操作者在浏览器中完成。
3. 启动前分别验证：实际出口地区、`http://127.0.0.1:<端口>/json/version` 可访问、目标站登录状态有效。profile 名称、代理名称或浏览器进程存活均不能替代这三项证据。
4. 不修改系统代理或其他应用的代理规则。若使用固定代理，浏览器和采集请求必须使用同一出口；仅在已验证的直连环境中使用 `--allow-direct-egress`。

## 3. 国际版搜索命令（只采搜索卡和分页证据）

以下命令按 F001--F006 串行运行。将 `INT-电脑标识` 和 `实际出口标签` 替换为不含账号或密钥的标签；CDP 浏览器须已在 9342 启动并登录 RedNote。

```bash
python3 xhs_distributed_runner.py \
  --stage recon \
  --device-id INT-电脑标识 \
  --account-id international-rednote \
  --collection-egress-region 实际出口标签 \
  --collection-egress-id direct-verified \
  --allow-direct-egress \
  --international-rednote \
  --cdp-debug-port 9342 \
  --manifest configs/xhs_ai_keyword_followup_20260705_20260908.csv \
  --run-root runs/rednote_ai_keyword_followup \
  --run-id AIKF-INT-YYYYMMDD \
  --event-ids F001,F002,F003,F004,F005,F006 \
  --all-search-results \
  --search-card-only \
  --search-sort latest \
  --page-sleep 30 \
  --search-page-cooldown 1800 \
  --search-page-cooldown-every 5 \
  --search-detail-session-limit 0 \
  --sleep-between-keywords 600 \
  --max-concurrency 1 \
  --stop-on-captcha \
  --stop-on-error
```

首次只做一词可附加 `--event-ids F001 --max-keywords 1 --dry-run` 检查命令、目录和参数；`--dry-run` 不验证登录或页面数据。实际采集出现验证码、登录失效、接口错误或出口变化时应停止，保留当前目录和 `batch_ledger.csv`，不要自动切换账号、代理或提高频率。

## 4. 节奏、恢复与数据要求

- 国际版的搜索、详情、一级评论和二级回复都必须使用 `--international-rednote`。运行器会把它透传为 `--xhs_international true`，并在 `batch_meta.json`、原始分页质量记录中写入 `collection_platform=rednote_international`；缺少该标记的批次不得与本任务合并。
- 搜索：单并发；每页 30 秒；每成功 5 页冷却 1,800 秒；关键词之间冷却 600 秒。
- 搜索阶段只落盘公开搜索卡、页码、排名、采集时间、原始分页状态和必要的访问令牌字段；令牌只在本机受忽略的 `runs/` 中保存，绝不提交 Git。
- 终止证据必须是 `has_more_false`、`two_pages_before_window` 或被明确记录的 `max_pages_guard`/中断原因。仅有进程存活、ledger 行或非空文件都不代表完整。
- 国际版搜索完成后，先在本机核验 `xhs/raw/search_results.jsonl` 与 `xhs/quality/search_pagination_status.jsonl`。再由项目负责人决定是否建立独立的国际版详情/评论样本；不得与国内五地深采队列混合。
- 国内五地的详情/评论阶段沿用 `plans/AI_KEYWORD_FOLLOWUP_5R_PLAN_20260908.md`：全局按 `note_id` 去重后每帖只请求一次，且一级评论、二级回复、分页质量和台账必须相互可复算。

## 5. 提交与交付

- Git 中只提交代码、CSV 清单、计划和脱敏汇总；`.gitignore` 已排除 `runs/`、浏览器数据、日志和本地备份。
- 每台电脑交付独立的脱敏摘要：运行 ID、平台、实际出口标签、开始/结束时间、每词页数与终止原因、搜索卡数、CAPTCHA/失败情况和缺口。原始数据由负责人通过受控渠道汇总，不通过 Git 同步。
- 采集器日志只记录分页数量和状态，不记录完整 API 响应，避免把访问令牌写入可共享日志。
