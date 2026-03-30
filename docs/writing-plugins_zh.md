# 编写 Ramune-ida 插件

Ramune-ida 支持通过外部插件添加 IDA 分析工具。插件会被自动发现并注册为 MCP 工具，无需修改源码。

[English](writing-plugins.md)

---

## 快速开始

在 `~/.ramune-ida/plugins/` 下创建一个文件夹：

```
~/.ramune-ida/plugins/
└── my_crypto/
    ├── __init__.py
    ├── metadata.py
    └── handlers.py
```

### 1. 定义 metadata

```python
# metadata.py

TOOLS = [
    {
        "name": "identify_crypto",
        "description": "Identify cryptographic algorithms by constant signatures (S-box, round constants).",
        "tags": ["crypto", "analysis"],
        "params": {
            "addr": {
                "type": "string",
                "required": False,
                "description": "Limit scan to a specific function address or name",
            },
        },
        "timeout": 120,
    },
]
```

### 2. 实现 handler

```python
# handlers.py

from ramune_ida.core import ToolError


def identify_crypto(params):
    import idaapi
    import ida_bytes

    addr = params.get("addr")
    # ... 扫描加密常量 ...

    if not results:
        raise ToolError(-12, "No crypto patterns found")

    return {
        "algorithms": ["AES-128", "SHA-256"],
        "details": [
            {"name": "AES S-box", "addr": "0x4050A0", "confidence": 0.98},
        ],
    }
```

### 3. 从包导出

```python
# __init__.py

from my_crypto.handlers import identify_crypto

__all__ = ["identify_crypto"]
```

重启服务器，工具会自动出现在 MCP 工具列表中。

---

## Metadata 字段说明

`TOOLS` 列表中的每个条目：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | str | 是 | 工具名，全局唯一 |
| `description` | str | 是 | AI 在 MCP schema 中看到的描述 |
| `params` | dict | 否 | 参数定义（见下方） |
| `tags` | list[str] | 否 | 分类标签（预留，未来用于可见性过滤） |
| `timeout` | int | 否 | 默认超时秒数（默认 30） |
| `handler` | str | 否 | handler 函数名（不指定则与 name 相同） |

参数定义：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `type` | str | `"string"` | `"string"`, `"integer"`, `"number"`, `"boolean"` |
| `required` | bool | `True` | 是否必填 |
| `default` | any | — | 可选参数的默认值 |
| `description` | str | — | AI 在 MCP schema 中看到的描述 |

## Handler 约定

```python
def tool_name(params: dict[str, Any]) -> dict[str, Any]:
```

- **输入**：`params` dict，字段由 metadata 中 `params` 定义
- **输出**：`dict`，会合并到 MCP 工具返回结果中
- **错误**：抛 `ToolError(code, message)` 返回结构化错误
- **IDA 导入**：在函数体内 import（`--list-plugins` 模式不加载 idalib）
- **取消**：由 dispatch 层通过 `sys.setprofile` 自动处理，handler 无需关心
- **Python 版本**：须兼容 Worker 的 Python（>= 3.10）

## 插件目录

默认路径：`~/.ramune-ida/plugins/`

可通过 `RAMUNE_PLUGIN_DIR` 环境变量或 `plugin_dir` 配置项覆盖。

目录只扫描一层。每个含有 `metadata.py` 的子目录被视为一个插件包。

## 错误处理

使用 `ToolError` 返回结构化错误：

```python
from ramune_ida.core import ToolError

def my_tool(params):
    addr = params.get("addr")
    if not addr:
        raise ToolError(-4, "Missing required parameter: addr")

    raise ToolError(-12, "Cannot resolve address")
```

其他异常由 dispatch 层捕获，作为内部错误返回。

## 测试

直接测试 handler，无需启动 MCP 服务器：

```python
def test_identify_crypto():
    from my_crypto.handlers import identify_crypto
    result = identify_crypto({"addr": "0x401000"})
    assert "algorithms" in result
```

完整 MCP 链路的集成测试参考 ramune-ida 仓库中的 `tests/test_mcp_tools.py`。

## 名称冲突

工具名在所有插件和内置工具中必须全局唯一。发现重名时服务器会中止启动并报错。

建议使用命名空间前缀：`crypto_identify` 而非 `identify`。
