# 插件式工具架构

> 目标：第三方可以独立开发 IDA 分析工具，不修改 ramune-ida 源码。
> 内置工具和插件工具对 AI 完全透明，无区别。

---

## 一、当前实现

### 1.1 添加一个工具只需 2 处

```
1. core/<category>/metadata.py  — 工具描述（名称、参数、timeout）
2. core/<category>/handlers.py  — Worker 侧 handler 实现
   + __init__.py 导出 handler 函数
```

Server 侧 MCP tool 函数由 `server/plugins.py` 从 metadata 自动生成。
Worker 侧通过 `worker/plugins.py` 自动发现并注册到 dispatch。

### 1.2 架构概览

```
启动流程：

Server                                    Worker
  │                                         │
  │  subprocess: --list-plugins             │
  │ ──────────────────────────────────────▶  │
  │                                         │  worker/plugins.py:
  │                                         │    discover_all()
  │                                         │      → scan core/ sub-packages
  │                                         │      → scan plugin folder
  │  ◀── JSON metadata (stdout) ◀───────── │
  │                                         │
  │  server/plugins.py:                     │
  │    register_plugin_tools()              │
  │    → 动态生成 MCP tool 函数             │
  │    → 设 __signature__ + __annotations__ │
  │                                         │

运行时调用：

MCP Client → Server (plugin MCP tool)
  → PluginInvocation("plugin:decompile", params)
  → Project.execute() → Worker IPC
  → Worker dispatch: plugin: prefix → handler
  → 返回 dict → Task.to_mcp_result()
```

### 1.3 关键模块

| 模块 | 职责 |
|------|------|
| `core/__init__.py` | `ToolError` 定义 |
| `core/<cat>/metadata.py` | `TOOLS` 列表（工具名、描述、参数、timeout） |
| `core/<cat>/handlers.py` | handler 实现（`params: dict → dict`） |
| `core/<cat>/__init__.py` | 导出 handler 函数 |
| `worker/plugins.py` | 统一发现：扫描 core 包 + 外部文件夹 |
| `worker/dispatch.py` | 双轨 dispatch：`plugin:` 前缀 → handler map |
| `server/plugins.py` | discovery（子进程）+ 动态 MCP tool 注册 |
| `commands.py` | `PluginInvocation`：轻量 Command 替身 |

### 1.4 外部插件文件夹

用户可将插件包放入 `~/.ramune-ida/plugins/`（或 `RAMUNE_PLUGIN_DIR` 指定的路径）。
每个插件是一个子目录，包含 `metadata.py` 和导出 handler 的 `__init__.py`。

```
~/.ramune-ida/plugins/
└── my_plugin/
    ├── __init__.py     # from .handlers import my_tool
    ├── metadata.py     # TOOLS = [...]
    └── handlers.py     # def my_tool(params: dict) -> dict: ...
```

工具名全局唯一，重名时 abort 并报错。

### 1.5 Metadata 格式

```python
# metadata.py
TOOLS = [
    {
        "name": "identify_crypto",
        "description": "Identify cryptographic algorithms by constant signatures.",
        "tags": ["crypto", "analysis"],
        "params": {
            "addr": {
                "type": "string",
                "required": False,
                "description": "Limit scan to a specific function",
            },
        },
        "timeout": 120,
    },
]
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | str | MCP 工具名，全局唯一 |
| `description` | str | 工具描述，直接用于 MCP schema |
| `tags` | list[str] | 标签列表（预留，未来用于可见性过滤） |
| `params` | dict | 参数定义：type / required / default / description |
| `handler` | str? | 函数名覆盖（默认与 name 相同） |
| `timeout` | int? | 默认超时秒数 |

### 1.6 Handler 接口

```python
def my_tool(params: dict[str, Any]) -> dict[str, Any]:
    import idaapi  # 懒加载 IDA 模块
    # ... 实现 ...
    return {"result_key": "value"}
```

- **输入**：`params: dict`，字段由 metadata 中 `params` 定义
- **输出**：`dict`，直接合并到 MCP tool 返回
- **错误**：抛 `ToolError(code, message)` → 结构化错误响应
- **取消**：sys.setprofile hook 由 dispatch 层自动安装，handler 无需关心
- **IDA 模块**：函数体内 import（`--list-plugins` 模式不加载 idalib）

---

## 二、未来规划

### 2.1 Tag 与动态工具可见性

插件通过 `tags` 字段声明类别。运行时可按 tag 过滤 AI 可见的工具集：

- 全部加载，动态可见（`tools/list` 时按 filter 决定展示）
- `set_tool_filter(include_tags=["crypto"])` 随时切换
- 内置工具始终可见，不受 filter 影响
- 隐藏的工具仍可直接调用（防止工作链断裂）

推荐 tag：analysis, modify, query, crypto, malware, firmware, deobfuscation, experimental

### 2.2 CLI filter

```bash
ramune-ida --plugin-tags crypto,malware         # 初始 include filter
ramune-ida --plugin-tags-exclude experimental   # 排除
ramune-ida --no-plugins                         # 完全跳过 discover
```

### 2.3 pip install 发现（远期）

当前使用文件夹扫描。未来可额外支持 Python entry_points 发现：

```toml
# pyproject.toml
[project.entry-points."ramune_ida.plugins"]
crypto = "ramune_plugin_crypto.metadata"
```

两种发现方式可并存：文件夹扫描（快速开发）+ entry_points（正式发布）。

---

## 三、安全边界

插件运行在 Worker 进程中，与 `execute_python` 的安全模型一致：

- **不做沙箱** — IDA 环境需要完整权限
- **进程隔离** — 插件崩溃 = Worker 崩溃，不影响 Server
- **超时保护** — metadata 中声明的 timeout 生效
- **取消支持** — sys.setprofile hook 自动安装
- **输出截断** — Server 层的 output_limit 统一生效

信任模型：安装插件 = 信任其代码。

---

## 四、不做什么

| 不做 | 原因 |
|------|------|
| 运行时热加载插件 | 复杂度高，重启 Server 即可 |
| 插件间依赖/通信 | 超出范围，插件应自包含 |
| 插件 marketplace | 前期不需要，pip install 即可 |
| 沙箱/权限系统 | 与 execute_python 同级信任模型 |
| 插件版本兼容性检查 | 初期信任开发者 |
