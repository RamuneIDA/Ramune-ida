# MCP Tools 实现计划（v2 — AI-First 设计）

> 设计哲学：输入宽容，输出诚实。
> 工具 = 高级意图，不是低级 API。MCP 吸收 IDA 内部复杂性。
> 工具详细设计见 tools-checklist.md
> 参考代码：/home/explorer/agent/ida-pro-mcp/src/ida_pro_mcp/ida_mcp/api_*.py

---

## 核心原则

1. **输入宽容** — AI 给模糊意图，MCP 尽力推断正确的 IDA API 路径
2. **输出诚实** — 说人话，明确说做了什么。AI 能理解自然语言结果
3. **失败有指导** — 处理不了返回原因 + 补救建议，让 AI 用 execute_python 兜底
4. **统一同类** — list/search/read/rename 等把 IDA 的多个 API 合并为一个高级工具
5. **工具少而厚** — 14 个核心工具，每个内部有智能路由逻辑
6. **无 default project** — 所有工具都传 project_id，无歧义
7. **project/database 分离** — project 是工作上下文，database 是 IDB 生命周期

---

## 当前已实现

MCP 会话工具（7 个，Phase 0 已重构）：
open_project, close_project, projects, open_database, close_database, get_task_result, cancel_task

MCP 核心工具（2 个）+ Worker handler（3 个）：
- decompile — MCP 工具 + Worker handler ✅
- execute_python — MCP 工具 + Worker handler ✅（stdout/stderr 捕获 + _result 约定 + 优雅取消）
- disasm — Worker handler only（MCP 工具待注册）

通用取消机制 ✅：
- Worker 侧：SIGUSR1 handler + cancel flag + sys.setprofile hook（Python 函数边界中断）
- Project 侧：两阶段——SIGUSR1 优雅取消 + 5s 看门狗 SIGKILL 兜底
- 三种场景验证通过：fast sleep / slow sleep / tight loop（SIGKILL fallback）

---

## 实现顺序

### Phase 0：会话重构 ✅

已完成：
- open_project/open_database 拆分（project 只创建上下文，database 绑定文件）
- close_database 合并 force_close（force 参数）
- 去掉 default project、switch_default、save_database、staging
- 新增 projects()、cancel_task()
- 放弃 stdio，只支持 Streamable HTTP / SSE
- INSTRUCTIONS 更新（含文件路由说明）
- Worker cwd 设为 work_dir

### Phase 1：核心分析循环 + 万能后备

目标：AI 能反编译、重命名、追踪引用——最小可用的逆向循环。
execute_python 提前到本阶段，有了它 AI 立即拥有完整的 IDA 能力，也方便测试验证。

1. **decompile** ✅ — MCP 工具 + Worker handler
2. **execute_python** ✅ — 万能后备（stdout/stderr 捕获 + _result + traceback + 优雅取消）
3. **disasm** — MCP 注册（Worker handler 已有）
4. **xrefs** — 全链路（第一版：经典地址 xref）
5. **rename** — 全链路（智能路由：全局/函数/局部变量）
6. **survey** — 全链路（二进制概览）

**准备工作：**
- _resolve_addr 提取到 worker/handlers/_utils.py（当前在 analysis.py 中，query/modify 也需要）
- 所有 MCP 工具参数加 Annotated 描述（当前 schema 只有 title 无 description）
- task_to_result helper 提取（MCP tool 拆包样板消除）
- register_worker_tool 简化注册（从 Command 类自动生成 MCP tool 函数）

**新增文件：**
- worker/handlers/_utils.py — resolve_addr 共享工具
- server/tools/_helpers.py — task_to_result + register_worker_tool

**修改文件：**
- protocol.py — 新增 XREFS, RENAME, SURVEY
- commands.py — 新增对应 Command 子类
- worker/handlers/analysis.py — 追加 xrefs handler
- worker/main.py — import 新 handler 模块

**新建文件：**
- worker/handlers/modify.py — rename handler
- server/tools/modify.py — rename MCP 工具（或用 register_worker_tool 注册）

### Phase 2：查询 + 搜索 + 地址映射

目标：AI 能浏览、搜索、读取二进制中的内容。

7. **list** — 统一列表（funcs/strings/imports/exports/segments/types/structs/enums/names/entries）
8. **search** — 统一搜索（bytes/regex 自动判断）
9. **read** — 统一数据读取（自动类型检测）
10. **resolve** — 地址三者互转（VA ↔ 文件偏移 ↔ ASLR 运行时地址）

**新增文件：**
- worker/handlers/query.py — list, search, survey handler
- worker/handlers/memory.py — read, resolve handler
- server/tools/query.py — list, search, read, resolve MCP 工具

### Phase 3：标注

目标：完整的标注能力。

11. **set_type** — 给地址/变量设类型
12. **define_type** — 创建/增量编辑结构体、枚举
13. **set_comment** — 汇编级 / F5 伪代码级注释
14. **undo** — 撤销

**修改文件：**
- worker/handlers/modify.py — 追加 set_type, define_type, set_comment, undo handler
- server/tools/modify.py — 追加对应 MCP 工具

---

## 工具总览

| 类别 | 工具数 | 工具 |
|------|--------|------|
| 分析 | 4 | decompile, disasm, xrefs, survey |
| 查询 | 4 | list, search, read, resolve |
| 修改 | 5 | rename, set_type, define_type, set_comment, undo |
| 执行 | 1 | execute_python |
| 会话 | 7 | open_project, close_project, projects, open_database, close_database, get_task_result, cancel_task |
| **合计** | **21** | 其中分析/查询/修改/执行 = **14 个核心工具** |

---

## 架构演进

### 近期：注册式简化（Phase 1 剩余工具时实施）

目标：Worker 工具的 MCP 层样板消除。添加工具从 6 处改动减少到 4 处。

- `register_worker_tool(CommandClass, description=...)` 从 Command 类自动生成 MCP tool
- `task_to_result(task, project_id)` 统一拆包逻辑
- 复杂工具（session 类、需要额外逻辑的）仍手写 MCP tool 函数

### 远期：插件式扩展

目标：第三方可以独立开发 IDA 分析工具，不修改 ramune-ida 源码。

插件 = 独立 Python 包，提供：
- metadata（JSON 或 Python dict）：工具名、description、参数 JSON schema、入口函数路径
- handler 代码：只依赖 IDA 环境 + 标准 Python，不依赖 ramune-ida 内部

Server 侧读 metadata → 注册 MCP tool → IPC 调用。Worker 侧 import 插件 → 调入口函数。
内置工具和插件工具对 AI 完全透明，无区别。

前置条件：内置工具稳定、注册式模式验证充分后再推进。
