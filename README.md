# Git Auto Commit Tool

定时自动对多个 Git 仓库执行 `git add -A` → `git commit` → `git push`。

## 快速开始

**1. 安装 Python 3.10+**

**2. 配置仓库**

复制 `config.example.json` 为 `config.json`，编辑要监控的仓库路径：

```json
{
  "repos": [
    {"path": "D:/Projects/my-app"},
    {"path": "E:/Code/another-project"}
  ],
  "interval_minutes": 30,
  "pull_before_push": false,
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
# 守护模式（每 30 分钟自动扫描）
py -m git_auto_commit

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

## 工作流程

```
检测变更 → git add -A → git commit → git push
```

- 有变更 → 自动暂存、提交、推送
- 无变更 → 跳过，不做任何操作
- 无远程仓库 → 只 commit，不 push
- Detached HEAD → 只 commit，不 push
- Push 失败 → 自动重试（次数可配置）

## 终止方式

- **Ctrl+C 一次** → 完成当前操作后优雅退出
- **Ctrl+C 两次** → 立即强制退出
