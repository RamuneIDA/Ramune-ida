# Ramune-ida

> **[开发中] 本项目正在积极开发中，API 和功能可能随时变更。**

Headless IDA Pro MCP Server —— 通过 [Model Context Protocol](https://modelcontextprotocol.io/) 将 IDA Pro 的逆向分析能力暴露给 AI Agent。

[English](README.md)

---

## 这是什么？

Ramune-ida 以 headless 模式运行 IDA Pro (idalib)，并将其封装为 MCP 服务器。Claude、Cursor 等 MCP 兼容客户端可以通过结构化工具调用来反编译函数、反汇编代码、执行任意 IDAPython。

## 核心设计

**进程分离** —— MCP Server 和 IDA 运行在不同进程中。Server 是纯 async Python；每个 IDA Worker 是单线程子进程，通过专用 fd-pair 管道（JSON line 协议）通信。从架构层面消灭线程安全问题。

**插件架构** —— 工具通过 metadata（描述、参数）和 handler 函数定义。Server 启动时自动发现工具，动态生成 MCP tool 函数并分发调用到 Worker。添加新工具只需写一个 metadata 文件和 handler 实现——无样板注册代码。支持外部插件文件夹。

**Worker 无状态** —— Worker 是一次性命令执行器。所有管理状态（任务队列、崩溃恢复）集中在 Project 层。Worker 崩溃后 Project 自动重启并重新打开 IDB，对使用者完全透明。

## 架构

```
MCP 客户端 (Claude / Cursor / ...)
    │  Streamable HTTP / SSE
    ▼
┌──────────────────────────────────┐
│  MCP Server (async Python)       │
│  FastMCP + Project 管理          │
│  插件发现 + 动态注册             │
└──────────────┬───────────────────┘
               │  fd-pair pipe (JSON lines)
         ┌─────┼─────┐
         ▼     ▼     ▼
      Worker Worker Worker
      idalib idalib idalib
      (插件 handler)
```

## 当前状态

### 已实现

**会话工具（7 个）：**
`open_project`、`close_project`、`projects`、`open_database`、`close_database`、`get_task_result`、`cancel_task`

**分析/执行工具（3 个）：**

| 工具 | 说明 |
|------|------|
| `decompile` | 反编译函数（支持函数名或十六进制地址） |
| `disasm` | 反汇编指令 |
| `execute_python` | 执行任意 IDAPython（stdout/stderr 捕获、`_result` 约定、优雅取消） |

**基础设施：**
- 插件架构：metadata 驱动的工具发现、动态 MCP 注册、外部插件文件夹
- 优雅取消：SIGUSR1 + `sys.setprofile` hook → 5 秒看门狗 → SIGKILL 兜底
- 输出截断 + HTTP 下载完整结果
- MCP Resources（项目/文件发现）
- 文件上传/下载 HTTP 端点

### 开发路线

| 阶段 | 重点 | 状态 |
|------|------|------|
| Phase 0 | 会话管理 | 已完成 |
| Phase 1 | 核心分析 —— decompile、disasm、execute_python、xrefs、rename、survey | 进行中 |
| Phase 2 | 查询搜索 —— list、search、read、resolve | 计划中 |
| Phase 3 | 标注 —— set_type、define_type、set_comment、undo | 计划中 |

## 插件

Ramune-ida 支持外部插件。将插件文件夹放入 `~/.ramune-ida/plugins/` 并重启服务器，工具会自动出现。

详见[插件编写指南](docs/writing-plugins_zh.md)。

## 快速开始

### 环境要求

- Python >= 3.10
- IDA Pro 9.0+（含 idalib）
- PDM（包管理器）

### 安装

```bash
git clone https://github.com/user/Ramune-ida.git
cd Ramune-ida
pdm install
```

### 运行

```bash
# 默认：Streamable HTTP，127.0.0.1:8000
ramune-ida

# 指定地址和端口
ramune-ida http://0.0.0.0:8745

# 使用 IDA 自带的 Python 启动 Worker
ramune-ida --worker-python /opt/ida/python3

# SSE 模式（兼容旧版 MCP 客户端）
ramune-ida sse://127.0.0.1:9000
```

### MCP 客户端配置

Claude Desktop 或 Cursor 中添加：

```json
{
  "mcpServers": {
    "ramune-ida": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

### 基本工作流

```
1. open_project()                          → 获取 project_id
2. open_database(project_id, "target.exe") → IDA 分析二进制文件
3. decompile(project_id, "main")           → 反编译 C 代码
4. execute_python(project_id, code)        → 执行任意 IDAPython 脚本
5. close_database(project_id)              → 保存并关闭
6. close_project(project_id)               → 清理
```

## CLI 参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `url` | `http://127.0.0.1:8000` | 传输协议地址 |
| `--worker-python` | `python` | Worker 子进程使用的 Python 解释器 |
| `--soft-limit` | `4` | 并发 Worker 建议上限 |
| `--hard-limit` | `8` | 并发 Worker 硬上限（0 = 不限） |
| `--work-dir` | `~/.ramune-ida/projects` | 项目文件工作目录 |
| `--auto-save-interval` | `300` | 自动保存间隔秒数（0 = 禁用） |
| `--output-max-length` | `50000` | 工具输出截断字符数 |

## 许可证

MIT
