# 参考资料

> 竞品分析和 AI 使用体验，作为设计参考保留。

---

## 一、ida-pro-mcp 项目分析

> 原文件：IDA-MCP-Analysis.md

ida-pro-mcp 是一个 MCP Server，将 IDA Pro 的反汇编/反编译能力暴露给 AI 助手。
采用两层代理架构：server.py（外部 MCP Server）→ ida_mcp/（IDA 插件侧 HTTP 服务）。

### 功能覆盖

71 个工具 + 24 个资源，包括：
- 核心查询：lookup_funcs, list_funcs, list_globals, imports
- 分析：decompile, disasm, xrefs_to, callees, callgraph, find_regex, find_bytes
- 内存读取：get_bytes, get_int, get_string, read_struct, patch
- 类型系统：set_type, declare_type, infer_types
- 修改：set_comments, rename, patch_asm, define_func
- 复合分析：analyze_function, analyze_component, diff_before_after, trace_data_flow
- Python 执行：py_eval

### 设计亮点

1. 零样板代码添加新功能（@tool + @idasync）
2. Batch-first 设计
3. 输出限流 50KB + 下载机制
4. 自实现 MCP 库 zeromcp（零外部依赖）

### Ramune-ida 的差异化选择

| 维度 | ida-pro-mcp | Ramune-ida |
|------|-------------|------------|
| 运行模式 | GUI 插件 + headless + 池代理 | 仅 headless idalib |
| MCP 实现 | 自研 zeromcp | 官方 MCP SDK |
| 线程安全 | @idasync + execute_sync | 进程分离，问题不存在 |
| 工具数量 | 71 个 | ~26 个核心 + execute_python 兜底 |
| 多实例 | 池代理 + Unix Socket | WorkerPool + fd pair pipe |

---

## 二、AI 使用体验报告

> 原文件：ida-mcp-review.md
> 使用场景：Enigma Protector v1.31 加壳程序逆向分析

### 高频工具

| 工具 | 单次项目调用量 |
|------|---------------|
| decompile | 200+ |
| get_bytes | 100+ |
| rename | 120+ |
| xrefs_to | 80+ |
| list_funcs / lookup_funcs | 60+ |
| find_bytes | 50+ |

### 关键痛点

1. **大函数反编译** — 2000+ 行函数截断后无法查看局部（→ 我们计划实现范围/摘要模式）
2. **类型系统对 LLM 不友好** — C 结构体声明格式要求严格（→ 我们选择 C 声明 + _parse_tinfo 三策略容错）
3. **trace_data_flow 实用性不足** — 输出太大，不如手动 xrefs 回溯
4. **缺少 undo/快照** — 批量修改后无法回退（→ 我们已实现 undo）

### 核心工作流

```
decompile(func) → 理解逻辑 → rename → decompile(caller)
                                        ↓
                  caller 中出现新名字，可读性逐步提升 → 继续命名
```

---

## 三、初始设计决策

> 原文件：next_mcp.md

### 精简工具 + Python 执行

不提供几十个细粒度工具。核心工具保证高频操作的可靠性和结构化输出，长尾需求通过 execute_python 覆盖。

### 进程分离消灭线程安全

MCP Server（async Python）+ idalib Worker（单线程子进程），通过 fd pair pipe 通信。
execute_sync / @idasync 从架构层面不再需要。

### 使用官方 MCP SDK

选择 Anthropic 官方 `mcp` 包，不用独立 FastMCP 3.x 或自研。理由：
1. 我们的 dispatch 是非标的（pipe 通信的哑 worker，不是 MCP-to-MCP）
2. 工具数量少，FastMCP 减样板的优势可忽略
3. 需要透明控制 worker 管理、session 路由、pipe I/O
4. 长期稳定，Anthropic 维护

### Multi-Agent 协同愿景

IDB 是天然共享黑板：Agent A 的 rename/set_type/set_comment 自动传播到 Agent B 的 decompile 结果中。协调信息（模块划分、任务分配、置信度）通过 IDB netnode 存储。
