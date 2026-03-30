# MCP Tools 实现计划（v2 — AI-First 设计）

> 设计哲学：输入宽容，输出诚实。
> 工具 = 高级意图，不是低级 API。MCP 吸收 IDA 内部复杂性。
> 工具详细设计见 tools-checklist.md

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

## 已实现

**会话工具（7 个）：**
open_project, close_project, projects, open_database, close_database, get_task_result, cancel_task

**分析/执行工具（3 个，通过插件架构注册）：**
- decompile — metadata + handler，自动注册 MCP tool ✅
- disasm — metadata + handler，自动注册 MCP tool ✅
- execute_python — metadata + handler（stdout/stderr 捕获 + _result 约定 + 优雅取消）✅

**插件架构 ✅：**
- 工具通过 `core/` 子包的 `metadata.py` 声明 + 包导出 handler 函数
- Worker `--list-plugins` CLI 输出 metadata JSON（不加载 idalib）
- Server 动态生成 MCP tool 函数（`server/plugins.py`）
- Worker 双轨 dispatch：`plugin:` 前缀走插件 handler，其余走内置 Command
- 外部插件文件夹扫描（`~/.ramune-ida/plugins/`，`RAMUNE_PLUGIN_DIR` 环境变量）
- 添加新工具只需 2 处：metadata.py 定义 + handler 实现

**通用取消机制 ✅：**
- Worker 侧：SIGUSR1 handler + cancel flag + sys.setprofile hook（Python 函数边界中断）
- Project 侧：两阶段——SIGUSR1 优雅取消 + 5s 看门狗 SIGKILL 兜底

---

## 实现顺序

### Phase 0：会话重构 ✅

### Phase 1：核心分析循环 + 万能后备（进行中）

目标：AI 能反编译、重命名、追踪引用——最小可用的逆向循环。

1. **decompile** ✅
2. **execute_python** ✅
3. **disasm** ✅
4. **xrefs** — 全链路（第一版：经典地址 xref）
5. **rename** — 全链路（智能路由：全局/函数/局部变量）
6. **survey** — 全链路（二进制概览）

### Phase 2：查询 + 搜索 + 地址映射

7. **list** — 统一列表（funcs/strings/imports/exports/segments/types/structs/enums/names/entries）
8. **search** — 统一搜索（bytes/regex 自动判断）
9. **read** — 统一数据读取（自动类型检测）
10. **resolve** — 地址三者互转（VA ↔ 文件偏移 ↔ ASLR 运行时地址）

### Phase 3：标注

11. **set_type** — 给地址/变量设类型
12. **define_type** — 创建/增量编辑结构体、枚举
13. **set_comment** — 汇编级 / F5 伪代码级注释
14. **undo** — 撤销

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
