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

Worker handler（2 个，无 MCP 工具）：decompile, disasm

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

### Phase 1：核心分析循环

目标：AI 能反编译、重命名、追踪引用——最小可用的逆向循环。

1. **decompile** — MCP 注册（Worker handler 已有）
2. **disasm** — MCP 注册（Worker handler 已有）
3. **xrefs** — 全链路（第一版：经典地址 xref）
4. **rename** — 全链路（智能路由：全局/函数/局部变量）
5. **survey** — 全链路（二进制概览）

**准备工作：** _resolve_addr 提取到 worker/handlers/_utils.py

**新增文件：**
- worker/handlers/_utils.py — resolve_addr 共享工具
- server/tools/analysis.py — decompile, disasm, xrefs, survey MCP 工具

**修改文件：**
- protocol.py — 新增 XREFS, RENAME, SURVEY
- commands.py — 新增对应 Command 子类
- worker/handlers/analysis.py — 追加 xrefs handler
- worker/main.py — import 新 handler 模块

**新建文件：**
- worker/handlers/modify.py — rename handler
- server/tools/modify.py — rename MCP 工具

### Phase 2：查询 + 搜索 + 地址映射

目标：AI 能浏览、搜索、读取二进制中的内容。

6. **list** — 统一列表（funcs/strings/imports/exports/segments/types/structs/enums/names/entries）
7. **search** — 统一搜索（bytes/regex 自动判断）
8. **read** — 统一数据读取（自动类型检测）
9. **resolve** — 地址三者互转（VA ↔ 文件偏移 ↔ ASLR 运行时地址）

**新增文件：**
- worker/handlers/query.py — list, search, survey handler
- worker/handlers/memory.py — read, resolve handler
- server/tools/query.py — list, search, read, resolve MCP 工具

### Phase 3：标注 + 兜底

目标：完整的标注能力 + 万能后备。

10. **set_type** — 给地址/变量设类型
11. **define_type** — 创建/增量编辑结构体、枚举
12. **set_comment** — 汇编级 / F5 伪代码级注释
13. **execute_python** — 万能后备（stdout 捕获 + _result + traceback）
14. **undo** — 撤销

**新增文件：**
- worker/handlers/python.py — execute_python handler
- server/tools/python.py — execute_python MCP 工具

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
