# 插件式工具架构 Roadmap

> 目标：第三方可以独立开发 IDA 分析工具，不修改 ramune-ida 源码。
> 内置工具和插件工具对 AI 完全透明，无区别。

---

## 一、现状与动机

### 1.1 当前添加一个工具的流程（6 处改动）

以 `decompile` 为例，需要修改/新建：

```
1. protocol.py          — Method 枚举 + Method.DECOMPILE
2. commands.py           — Decompile(Command) + Decompile.Result
3. worker/handlers/*.py  — @handler(Method.DECOMPILE) 实现函数
4. worker/main.py        — import handler 模块（触发注册）
5. server/tools/*.py     — async def decompile(...) MCP 函数
6. server/tools/__init__.py — register_tool(description=...)(fn)
```

Server 侧（步骤 5-6）和 Worker 侧（步骤 3-4）的样板代码高度相似：
- Server 侧每个工具都重复 resolve_project → execute → 拆包 task 的模式
- Worker 侧 handler 注册是装饰器，已经比较简洁

### 1.2 问题

- **添加摩擦大**：6 处改动，3 个文件定义同一个概念（Method / Command / Handler）
- **Server 侧样板**：每个转发型工具（非 session 类）的 MCP 函数逻辑几乎一致
- **不可外部扩展**：所有工具必须写在 ramune-ida 源码树中

---

## 二、演进路线

```
阶段 0（现状）     → 阶段 1（注册式简化）     → 阶段 2（插件系统）
6 处改动/工具          4 处改动/工具               1 个 Python 包/工具
手写 MCP 函数          自动生成 MCP 函数           metadata 驱动注册
```

---

## 三、阶段 1：注册式简化（Phase 1 剩余工具时实施）

### 3.1 目标

Worker 转发型工具的 Server 层样板消除。改动点从 6 → 4。

### 3.2 task_to_result helper

提取所有 MCP 工具函数中重复的 task 拆包逻辑：

```python
# server/tools/_helpers.py

def task_to_result(task: Task, project_id: str) -> dict:
    result: dict = {"project_id": project_id, "status": task.status.value}
    if task.result is not None:
        result.update(task.result)
    if task.error is not None:
        result["error"] = task.error.message
    if not task.is_done:
        result["task_id"] = task.task_id
    return result
```

现有的 `decompile`、`execute_python` 等立即受益，减少约 6 行/工具。

### 3.3 register_worker_tool 自动生成

对于纯转发型工具（resolve_project → Command → execute → 拆包），
从 Command 类自动生成 MCP tool 函数：

```python
# server/tools/_helpers.py

def register_worker_tool(
    command_cls: type[Command],
    description: str,
    timeout: float | None = None,
):
    """从 Command 类自动注册一个 MCP 工具。

    生成的函数签名从 command_cls.model_fields 推导：
    - 始终有 project_id: str, ctx: Context
    - Command 的字段成为额外参数
    - 如果 command_cls 有 timeout 语义，加 timeout 参数
    """
    ...
```

使用示例：

```python
# server/tools/__init__.py

register_worker_tool(Decompile, description="Decompile a function by name or hex address.")
register_worker_tool(Disasm, description="Disassemble instructions at an address.")
register_worker_tool(ExecPython, description="Execute arbitrary IDAPython code.", timeout=60)
```

消除步骤 5（手写 MCP 函数）。添加新工具只需 4 处改动：

```
1. protocol.py          — Method 枚举
2. commands.py           — Command 子类
3. worker/handlers/*.py  — handler 实现
4. server/tools/__init__.py — register_worker_tool(Cmd, description=...)
                             （worker/main.py import 在 handlers/ __init__ 自动化后也可省略）
```

### 3.4 复杂工具仍手写

Session 类工具（open_project, close_database 等）有独立逻辑，不走 Worker 转发，
继续手写 MCP 函数。这不是退化——这些工具本就不适合自动生成。

### 3.5 实施时机

Phase 1 剩余工具（disasm MCP 注册、xrefs、rename、survey）实现时一并完成。
验证 register_worker_tool 能覆盖所有转发型工具的需求后，再考虑阶段 2。

---

## 四、阶段 2：插件系统

### 4.1 核心思想

**插件 = 一个独立 Python 包**，自带两样东西：

1. **metadata** — 工具名、description、参数 JSON schema、入口路径、tags
2. **handler 代码** — 只依赖 IDA 环境 + 标准 Python，不 import ramune-ida

Server 侧读 metadata → 自动注册 MCP tool → IPC 调用。
Worker 侧 import 插件模块 → 调入口函数。
两侧完全不需要共享代码。

### 4.2 插件包结构

```
ramune-plugin-crypto/
├── pyproject.toml
└── ramune_plugin_crypto/
    ├── __init__.py         # 空或 package marker
    ├── metadata.py         # 工具 metadata（Python dict）
    └── handlers.py         # Worker 侧 handler 实现
```

### 4.3 Metadata 格式

使用 Python dict 而非 JSON 文件——更灵活，可引用常量，IDE 补全友好：

```python
# ramune_plugin_crypto/metadata.py

TOOLS = [
    {
        "name": "identify_crypto",
        "description": "Identify cryptographic algorithms by constant signatures (S-box, round constants, etc).",
        "tags": ["crypto", "analysis"],
        "params": {
            "project_id": {"type": "string", "required": True},
            "addr": {"type": "string", "required": False, "description": "Limit scan to a specific function"},
        },
        "handler": "ramune_plugin_crypto.handlers:identify_crypto",
        "timeout": 120,
    },
    {
        "name": "extract_constants",
        "description": "Extract constant tables (S-boxes, key schedules) used by a function.",
        "tags": ["crypto", "query"],
        "params": {
            "project_id": {"type": "string", "required": True},
            "func": {"type": "string", "required": True},
        },
        "handler": "ramune_plugin_crypto.handlers:extract_constants",
        "timeout": 60,
    },
]
```

字段说明：

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | str | MCP 工具名，全局唯一 |
| `description` | str | 工具描述，直接用于 MCP schema |
| `tags` | list[str] | 标签列表，用于启动时按条件过滤（见 4.10） |
| `params` | dict | 参数定义，生成 JSON schema + MCP 函数签名 |
| `handler` | str | `module.path:function_name` 格式，Worker 侧 import 调用 |
| `timeout` | float? | 默认超时秒数，可选 |

### 4.4 Handler 接口

Handler 函数签名约定——接收一个 dict 参数，返回一个 dict：

```python
# ramune_plugin_crypto/handlers.py

def identify_crypto(params: dict) -> dict:
    """Scan binary for known crypto constants.

    params:
        addr (str, optional): limit scan to function at this address

    Returns:
        dict with keys: algorithms (list), details (list of match objects)
    """
    import idaapi
    import ida_bytes

    # ... 实际逻辑 ...

    return {
        "algorithms": ["AES-128", "SHA-256"],
        "details": [
            {"name": "AES S-box", "addr": "0x4050A0", "confidence": 0.98},
        ],
    }
```

关键约定：

- **输入**：`params: dict`，字段由 metadata 中 `params` 定义
- **输出**：`dict`，直接作为 MCP tool result
- **异常**：抛 `Exception` → ramune-ida 捕获转为错误响应
- **无依赖**：不 import ramune_ida 任何模块。只用 IDA SDK + 标准库
- **取消支持**：sys.setprofile hook 由 dispatch 层自动安装，handler 无需关心

### 4.5 发现机制

使用 Python entry_points（setuptools / PEP 621 标准）：

```toml
# ramune-plugin-crypto/pyproject.toml

[project]
name = "ramune-plugin-crypto"
version = "0.1.0"

[project.entry-points."ramune_ida.plugins"]
crypto = "ramune_plugin_crypto.metadata"
```

ramune-ida 启动时扫描所有已安装插件（全量加载，不过滤）：

```python
# ramune_ida/plugins/discovery.py

from importlib.metadata import entry_points

def discover_plugins() -> list[dict]:
    """Scan installed packages for ramune_ida.plugins entry points."""
    tools = []
    for ep in entry_points(group="ramune_ida.plugins"):
        module = ep.load()
        if hasattr(module, "TOOLS"):
            for tool_meta in module.TOOLS:
                tool_meta["_plugin"] = ep.name
                tools.append(tool_meta)
    return tools
```

可见性过滤不在 discover 阶段，而是在运行时由 `ToolRegistry` 控制（见 4.10）。

### 4.6 Server 侧自动注册

发现到的 metadata 直接生成 MCP tool 函数并注册：

```python
# ramune_ida/plugins/register.py

def register_plugin_tools(discovered: list[dict]):
    """为每个插件工具生成 MCP tool 函数并注册到 FastMCP。"""
    for meta in discovered:
        # 从 meta["params"] 动态构建函数签名
        # 生成的函数逻辑等同 register_worker_tool：
        #   resolve_project → IPC 调用 → task_to_result
        # IPC method 统一为 "plugin:{name}" 避免与内置冲突
        register_tool(description=meta["description"])(generated_fn)
```

IPC 协议扩展：

```json
{
    "id": "req-042",
    "method": "plugin:identify_crypto",
    "params": {"addr": "0x401000"}
}
```

`method` 以 `plugin:` 前缀区分。Worker 的 dispatch 层识别后走插件调用路径。

### 4.7 Worker 侧动态 dispatch

Worker dispatch 扩展——识别 `plugin:` 前缀，动态 import handler：

```python
# worker/dispatch.py 扩展

_PLUGIN_CACHE: dict[str, Callable] = {}

def _resolve_plugin_handler(method: str) -> Callable:
    """'plugin:identify_crypto' → import + cache handler function."""
    plugin_name = method.removeprefix("plugin:")
    if plugin_name in _PLUGIN_CACHE:
        return _PLUGIN_CACHE[plugin_name]

    # 从 metadata 中查找 handler 路径（启动时已加载）
    handler_ref = _PLUGIN_METADATA[plugin_name]["handler"]
    module_path, func_name = handler_ref.rsplit(":", 1)
    module = importlib.import_module(module_path)
    fn = getattr(module, func_name)
    _PLUGIN_CACHE[plugin_name] = fn
    return fn
```

dispatch 主流程中增加一个分支：

```python
def dispatch(request: Request) -> Response:
    if request.method.startswith("plugin:"):
        fn = _resolve_plugin_handler(request.method)
        # sys.setprofile + cancel 机制同样生效
        result = fn(request.params or {})
        return Response.ok(request.id, result)
    # ... 内置工具原有逻辑 ...
```

### 4.8 Worker 环境下的插件 metadata 传递

Worker 进程需要知道插件的 handler 映射。两种方式：

**方案 A：Worker 自行发现（推荐）**

Worker 启动时也执行 `discover_plugins()`。由于插件包已 pip install，
Worker 的 Python 环境也能发现 entry_points。

优点：零配置，Server/Worker 独立发现，不需要 IPC 传递 metadata。
缺点：要求插件包同时安装在 Server 和 Worker 的 Python 环境中。

**方案 B：Server 通过 IPC 下发 metadata**

Server 启动后，首次与 Worker 通信时发送一条 `register_plugins` 命令，
携带所有 metadata。Worker 据此缓存 handler 映射。

优点：只需在 Server 侧安装插件包（Worker 侧通过 handler 路径动态 import）。
缺点：增加 IPC 复杂度。

**选择**：方案 A。原因：
- Worker 的 Python 是 IDA 的 Python（可能是 3.12），插件的 handler 代码需要在该环境运行
- 既然 handler 代码必须安装在 Worker Python 中，metadata 自然也在
- 方案 B 只是把安装问题推迟了——handler 代码不安装，Worker 也没法 import

### 4.9 双 Python 环境的安装策略

ramune-ida 存在 Server Python（3.14）和 Worker Python（IDA 3.12）两个环境：

```
Server Python (3.14):
  pip install ramune-ida
  pip install ramune-plugin-crypto    ← 只需 metadata（读 TOOLS dict）

Worker Python (3.12, IDA):
  pip install ramune-plugin-crypto    ← 需要 handler 代码（依赖 IDA SDK）
```

插件包的 pyproject.toml 不声明 IDA SDK 依赖（它不在 PyPI 上），
而是在 handler 代码中 runtime import。这也是 ramune-ida 本身的做法。

如果两个 Python 版本完全不同，且插件使用了 3.13+ 语法：
- handler 代码必须兼容 Worker Python 版本（与 ramune-ida worker/ 约束相同）
- metadata 无此限制（只在 Server 侧读取）

### 4.10 Tag 与动态工具可见性

插件工具通过 `tags` 字段声明自己的类别。
这解决了一个实际问题：**安装了很多插件，但当前任务只需要其中一部分。**

AI 可见的工具越多，工具选择的噪声越大。Tag 过滤让用户根据当前分析场景精准控制工具集。

#### 核心设计：全部加载，动态可见

启动时所有插件全部发现、全部注册到内部 registry。
**不在启动时做静态裁剪。** 过滤发生在运行时——MCP 返回 `tools/list` 时
根据当前 filter 条件决定哪些工具对 AI 可见。

```
启动：discover_plugins() → 全部注册到 _tool_registry
                                     ↓
运行时：tools/list 请求 → _tool_registry × _visibility_filter → 返回可见工具
                                     ↑
         set_tool_filter(tags=["crypto"]) 随时修改 filter
```

好处：
- 不重启 Server 即可切换工具集（分析 crypto 模块时开 crypto，完了关掉）
- 不影响已注册工具的 handler 和 IPC 通道——只是 list 不返回，调用仍然可达
- 默认全部可见，零配置

#### MCP 工具接口

通过一个内置 MCP tool 控制 filter：

```python
async def set_tool_filter(
    include_tags: list[str] | None = None,
    exclude_tags: list[str] | None = None,
    ctx: Context,
) -> dict:
    """Control which plugin tools are visible to AI.

    - include_tags: only show plugins matching any of these tags (OR).
    - exclude_tags: hide plugins matching any of these tags (takes priority).
    - Both None = show all plugins (default).
    - Built-in tools are always visible regardless of filter.

    Changes take effect on next tools/list refresh.
    """
```

AI 或用户均可调用。典型使用场景：

```
AI: "我要分析一个加密算法，先加载 crypto 工具"
  → set_tool_filter(include_tags=["crypto"])

AI: "crypto 分析完了，恢复全部工具"
  → set_tool_filter()  # 不传参 = 清除 filter
```

#### CLI 初始 filter（可选）

启动时可以通过 CLI 设置初始 filter，效果等同启动后立即调用 `set_tool_filter`：

```bash
# 启动时默认只展示 crypto 和 malware 相关插件
ramune-ida --plugin-tags crypto,malware

# 启动时排除 experimental
ramune-ida --plugin-tags-exclude experimental

# 不加载任何插件（完全跳过 discover，比 filter 更彻底）
ramune-ida --no-plugins
```

对应配置项：

```python
class RamuneConfig:
    plugin_tags: list[str] | None = None          # 初始 include filter
    plugin_tags_exclude: list[str] | None = None   # 初始 exclude filter
    plugins_enabled: bool = True                   # False = 跳过 discover
```

`--no-plugins` 和 tag filter 的区别：
- `--no-plugins`：不执行 discover，插件代码不加载，不可恢复
- `--plugin-tags`：全部加载，只是初始 visibility filter，运行时可通过 `set_tool_filter` 修改

#### Server 侧实现要点

```python
class ToolRegistry:
    _all_tools: dict[str, ToolEntry]          # name → 全量注册（含 handler/meta）
    _include_tags: set[str] | None = None     # 当前 include filter
    _exclude_tags: set[str] | None = None     # 当前 exclude filter

    def set_filter(self, include: list[str] | None, exclude: list[str] | None):
        self._include_tags = set(include) if include else None
        self._exclude_tags = set(exclude) if exclude else None
        # 触发 MCP tools/list_changed 通知（如果协议支持）

    def visible_tools(self) -> list[ToolEntry]:
        """返回当前 filter 下可见的工具列表（tools/list 使用）。"""
        result = []
        for tool in self._all_tools.values():
            if tool.builtin:
                result.append(tool)
                continue
            tags = set(tool.tags)
            if self._exclude_tags and tags & self._exclude_tags:
                continue
            if self._include_tags and not (tags & self._include_tags):
                continue
            result.append(tool)
        return result

    def resolve(self, name: str) -> ToolEntry | None:
        """按名称查找工具（调用时使用，不受 filter 限制）。"""
        return self._all_tools.get(name)
```

关键语义：
- `visible_tools()` 被 `tools/list` 使用——**受 filter 影响**
- `resolve()` 被工具调用使用——**不受 filter 影响**
- 即使工具被 filter 隐藏，直接按名调用仍然可以执行（防止中途切 filter 导致正在进行的工作链断裂）
- filter 变更后，MCP 协议如果支持 `notifications/tools/list_changed`，可以主动通知客户端刷新工具列表

#### 推荐 tag 约定

| tag | 含义 |
|-----|------|
| `analysis` | 分析型工具（只读，不修改 IDB） |
| `modify` | 修改型工具（会改 IDB） |
| `query` | 查询/列表类 |
| `crypto` | 密码学相关 |
| `malware` | 恶意软件分析 |
| `firmware` | 固件/嵌入式 |
| `deobfuscation` | 反混淆 |
| `experimental` | 实验性，不稳定 |

Tag 是自由文本，不做强制校验。上表只是推荐。插件开发者可以自定义任意 tag。

#### 内置工具的 tag

内置工具也有隐式 tag 分类（analysis / session / execution 等），
但它们不参与 tag 过滤——**始终可见**。如果未来需要禁用某些内置工具，
通过独立的 `--disable-tools` 参数实现，不复用 tag 机制。

---

## 五、内置工具与插件工具的关系

### 5.1 对 AI 完全透明

AI 看到的 MCP tool schema 没有"内置"和"插件"的区分。
所有工具都是平等的 MCP tools，有相同的参数格式和返回结构。

### 5.2 内置工具不迁移

已有的 decompile、execute_python 等内置工具保持原有实现方式
（阶段 1 的 register_worker_tool 注册）。不强制用插件格式重写。

原因：
- 内置工具与 ramune-ida 生命周期绑定，不需要独立发布
- 部分内置工具（session 类）有特殊逻辑，不适合插件接口
- 避免引入不必要的抽象层

### 5.3 名称冲突规则

- 内置工具名优先，插件不可覆盖
- 插件之间名称冲突时，按 entry_point 名字母序取第一个，日志告警
- 建议插件名带命名空间前缀：`crypto_identify` 而非 `identify`

---

## 六、安全边界

插件运行在 Worker 进程中，与 `execute_python` 的安全模型一致：

- **不做沙箱** — IDA 环境需要完整权限
- **进程隔离** — 插件崩溃 = Worker 崩溃，不影响 Server
- **超时保护** — metadata 中声明的 timeout 生效
- **取消支持** — sys.setprofile hook 自动安装
- **输出截断** — Server 层的 output_limit 统一生效

信任模型：安装插件 = 信任其代码。与 pip install 任何包的信任模型一致。

---

## 七、测试策略

### 7.1 插件开发者测试

插件包自带测试，使用 mock IDA 环境或真实 IDA：

```python
# tests/test_identify_crypto.py

def test_identify_aes():
    from ramune_plugin_crypto.handlers import identify_crypto
    # mock idaapi / ida_bytes ...
    result = identify_crypto({"addr": "0x401000"})
    assert "AES" in result["algorithms"]
```

### 7.2 ramune-ida 集成测试

测试插件发现、注册、IPC 调用全链路：

```python
def test_plugin_discovery(tmp_path):
    """安装一个 test plugin，验证 discover_plugins 返回正确 metadata。"""

def test_plugin_dispatch(mock_worker):
    """注册一个假插件，验证 Worker dispatch 能路由到 handler。"""

def test_plugin_cancel(mock_worker):
    """验证插件 handler 在 SIGUSR1 后被 CancelledError 中断。"""
```

---

## 八、时间线

| 阶段 | 前置条件 | 预计时间点 |
|------|---------|-----------|
| 阶段 1：注册式简化 | Phase 1 工具（disasm/xrefs/rename/survey）实现 | Phase 1 中期 |
| 阶段 2 设计：metadata 格式定稿 | 阶段 1 验证充分 | Phase 2 后 |
| 阶段 2 实现：插件发现 + 注册 + dispatch | metadata 格式定稿 | Phase 3 后 |
| 阶段 2 发布：文档 + 示例插件 | 内置工具稳定 | 14 个核心工具全部完成后 |

### 启动信号

不急于实现插件系统。以下信号出现时启动：
- 内置 14 个核心工具稳定运行
- register_worker_tool 模式经历了足够多的工具验证
- 出现了真实的外部扩展需求（自用或社区）

---

## 九、不做什么

| 不做 | 原因 |
|------|------|
| 运行时热加载插件 | 复杂度高，Worker 进程模型不适合。重启 Server 即可 |
| 插件间依赖/通信 | 超出范围。插件应自包含 |
| 插件 marketplace | 前期不需要。pip install 即可 |
| GUI 配置界面 | headless 项目，无 GUI |
| 插件版本兼容性检查 | 初期信任开发者。后续按需加 min_ramune_version 字段 |
| 沙箱/权限系统 | 与 execute_python 同级信任模型，无意义 |
