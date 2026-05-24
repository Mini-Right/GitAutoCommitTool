# Git Auto Commit Tool

定时自动对多个 Git 仓库执行 `git add -A` → `git commit` → `git push`。

支持 Web 管理面板、GUI 独立窗口、一键推送、单仓库推送。

## 快速开始

### 方式 1：EXE 双击运行（推荐）

下载 `dist/GitAutoCommit.exe`，双击即可启动 GUI 模式 —— 自动弹出原生管理窗口，无需浏览器、无需 CMD。

首次运行会在同目录自动生成 `config.json` 模板，在页面中添加仓库即可。

### 方式 2：Python 命令行

**1. 安装 Python 3.10+**

**2. 配置仓库**

首次运行会自动创建 `config.json` 模板。也可手动创建：

```json
{
  "repos": [
    {"path": "D:/Projects/my-app"},
    {"path": "E:/Code/another-project"}
  ],
  "interval_minutes": 30,
  "pull_before_push": true,
  "max_push_retries": 3,
  "push_retry_delay_seconds": 5
}
```

| 字段 | 必填 | 默认值 | 说明 |
|---|---|---|---|
| `repos[].path` | 是 | - | 仓库本地路径 |
| `repos[].enabled` | 否 | `true` | 是否启用该仓库 |
| `repos[].commit_message_prefix` | 否 | `"自动提交: "` | commit 消息前缀 |
| `interval_minutes` | 否 | `30` | 扫描间隔（分钟） |
| `pull_before_push` | 否 | `true` | push 前是否先 pull |
| `max_push_retries` | 否 | `3` | push 失败重试次数 |
| `push_retry_delay_seconds` | 否 | `5` | 重试间隔（秒） |

**3. 运行**

```bash
# 守护模式（启动 Web 管理面板 + 自动扫描）
py -m git_auto_commit

# GUI 模式（原生窗口，无需浏览器）
py -m git_auto_commit --gui

# 单次扫描后退出
py -m git_auto_commit --once

# 预览模式（只显示将要执行的操作，不实际提交）
py -m git_auto_commit --once --dry-run

# 自定义扫描间隔（10 分钟）
py -m git_auto_commit --interval 10

# 调试模式
py -m git_auto_commit --verbose

# 查看帮助
py -m git_auto_commit --help
```

## Web 管理面板

启动后自动打开浏览器访问 `http://localhost:8080`（GUI 模式下内嵌在窗口中）。

功能：
- **仓库管理** — 添加、删除、启用/禁用仓库
- **立即扫描** — 手动触发一轮扫描
- **一键推送** — 强制所有仓库执行 add + commit + push
- **单仓库推送** — 对某个仓库单独执行推送
- **全局设置** — 修改扫描间隔、pull 策略、重试参数
- **扫描历史** — 查看历次扫描结果
- **实时日志** — 流式查看运行日志

## CLI 参数

| 参数 | 说明 |
|---|---|
| `--config PATH` | 指定配置文件路径（默认 `./config.json`） |
| `--interval N` | 扫描间隔（分钟） |
| `--once` | 单次扫描后退出 |
| `--dry-run` | 预览模式，不实际提交 |
| `--gui` | GUI 模式，弹出原生管理窗口 |
| `--port N` | Web 服务器端口（默认 8080） |
| `--no-web` | 不启动 Web 管理面板 |
| `--verbose` | 调试日志 |
| `--quiet` | 仅输出警告和错误 |
| `--log-file PATH` | 写入日志文件 |
| `--no-color` | 禁用 ANSI 颜色输出 |

## 工作流程

```
检测变更 → git add -A → git commit → git push
```

- 有变更 → 自动暂存、提交、推送
- 无变更 → 跳过，不做任何操作
- 一键推送 → 无论是否有变更，强制执行 add + commit(`--allow-empty`) + push
- 无远程仓库 → 只 commit，不 push
- Detached HEAD → 只 commit，不 push
- Push 失败 → 自动重试（次数可配置）

## 构建 EXE

```bash
pip install pywebview
pip install pyinstaller

py -m PyInstaller --onefile --noconsole --name GitAutoCommit \
  --add-data "git_auto_commit/static;git_auto_commit/static" \
  --hidden-import webview --hidden-import webview.platforms.winforms \
  run_gui.py
```

输出文件：`dist/GitAutoCommit.exe`

## 终止方式

- **Ctrl+C 一次** → 完成当前操作后优雅退出
- **Ctrl+C 两次** → 立即强制退出
- GUI 模式直接关闭窗口即可
