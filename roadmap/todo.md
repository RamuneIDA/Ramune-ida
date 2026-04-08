# Ramune-ida TODO

> 剩余未实现的功能和改进计划。
>
> 来源标记：[bench] = 2026-04-01 benchmark 测试中发现的问题

---

## 基础设施

- [ ] **tool call 批量化** — 支持单次请求中批量调用多个工具（如批量 rename、批量 set_type），减少 IPC 往返开销
- [x] **tag filter 系统** — `--exclude-tags` 按标签/路径通配/名称隐藏 MCP 工具。自动注入路径标签（`core::execution::execute_python`）和名称标签（`name::execute_python`），支持 `fnmatch` glob
- [x] [bench] **execute_python 硬超时去掉** — 统一走 MCP 层超时 + task_id 轮询/cancel
- [ ] **大文件上传流式写入** — `files.py` upload 端点改为分块流式写入磁盘，避免大文件全量读入内存

---

## 新工具

- [ ] addr_convert — VA ↔ 文件偏移 ↔ ASLR 运行时地址互转
- [ ] stack_frame — 函数栈帧布局查看
- [ ] [bench] call_graph — `call_graph(func, depth?, direction?)` 返回调用树 JSON。用 `idautils.CodeRefsFrom`/`CodeRefsTo` 递归构建

---

## listing 扩展

> 当前：list_funcs, list_strings, list_imports, list_names, list_types（5 个）。
> 过滤统一为 `filter`（substring 包含）+ `exclude`（substring 排除），各接受单个字符串。

- [x] list_types — 本地类型库（支持 kind 过滤：struct/enum/union/typedef）
- [ ] list_exports — 导出函数
- [ ] list_segments — 段信息
- [ ] list_structs — 结构体列表
- [ ] list_enums — 枚举列表
- [ ] list_entries — 入口点

---

## xrefs 增强

> 当前：xrefs(addr) — XrefsTo 按地址/名称查引用。返回包含 total 字段。

- [ ] 区分 code ref / data ref（可选标记）
- [ ] direction 参数：`"to"` / `"from"`（XrefsFrom）
- [ ] xrefs(struct, field) — 结构体成员 xref（依赖 ida_typeinf TID）
- [ ] xrefs(type) — 谁使用了这个类型（遍历函数签名/变量）
- [ ] [bench] **间接引用搜索** — 当 `idautils.XrefsTo` 返回空时（Rust `&str` slice 引用、C++ vtable 间接调用等场景），自动搜索目标地址的小端序编码字节（4/8 字节），作为 fallback。或通过新增 `deep=true` 参数触发

---

## search 扩展

> 当前：regex 搜索 strings/names/types/disasm + 字节模式搜索。

- [ ] 反编译结果搜索 — 从 decompile 缓存中 regex 搜索伪代码
- [ ] 偏移/常量搜索 — 搜索立即数（immediate value），跨汇编和数据段
- [ ] 注释搜索 — 搜索用户注释和 IDA 自动注释

---

## decompile 增强

- [ ] 局部反编译 — 行范围或地址范围，大函数场景
- [ ] 摘要模式 — 签名 + 调用 + 字符串 + 控制流概览
- [ ] [bench] **非函数地址自动创建函数** — 当目标地址未被 IDA 识别为函数时，自动尝试 `ida_funcs.add_func(addr)` 后重试反编译。通过 `force` 参数控制（默认 false）

---

## 错误哲学

> **报告事实，不做翻译。** MCP 的消费者是 AI，不需要我们替它解读 IDA API 的返回值含义。
> 错误信息应直接反映"调了什么 API、传了什么参数、得到了什么结果"，让 AI 自己判断下一步。
> 例如：`"get_func(0x1234) returned None"` 而非 `"0x1234 is not a function"`。
> 参数校验错误（`"Missing required parameter: func"`）保持不变——这些本身就是事实陈述。

---

## 设计观察

### AI 并发调用行为与 API 设计的关系（2026-04-02）

**现象**：Ramune-ida（HTTP 传输 + 单项参数 API）使用时，Claude 会积极并发调用 3-4 个 tool（如同时反编译多个函数）。而 ida-pro-mcp（即使使用 HTTP 传输 + batch 参数 API）Claude 仍倾向于逐个调用。

**可能的解释**：
- 单项 API（`decompile(func)` 只接受一个函数）迫使 Claude 发多个独立 tool call → MCP 客户端自动并发
- Batch API（`decompile(addrs="a,b,c")`）让 Claude "可以"打包，但 LLM 的 ReAct 推理循环天然倾向一次一步，实际上很少利用 batch 能力
- 结果：单项 API 反而比 batch API 更快，因为并发从"可选优化"变成了"唯一选择"

**Claude 自述**（直接询问得到的回答）：
> 原因是 ramune-ida 支持多项目并行，每个 project 独立进程，所以可以并发；
> ida-pro-mcp 是单 session 模型，并行请求会排队或冲突，所以串行。

这个解释有漏洞：Claude 在 Ramune-ida 的**同一个 project** 内也会并发调用多个 decompile，
说明它不只是跨 project 并发。更可能是 Claude 从 API 表面（instructions、project_id 隔离、
工具数量等）推断出"安全可并发"的心理模型，而非真的理解底层架构。LLM 的自我内省不可靠。

**存疑**：以上所有解释均缺乏充分数据验证。还可能受到以下因素影响：
- MCP 客户端实现（不同 host 对 stdio/HTTP 的并发策略不同）
- 工具数量（77 vs ~15）和 schema 复杂度对 Claude 保守程度的影响
- instructions 字段的有无（ida-pro-mcp 的 zeromcp 不返回 instructions）
- Claude 版本/模型差异

**应对措施**：
- 保持单项 API 设计；batch 如有需要作为补充而非替代
- 在 INSTRUCTIONS 中显式鼓励并发："ALL read-only tools are safe to call concurrently"
- 需要更多实际使用数据来验证哪些因素真正起作用

---

## 远期

- [ ] analysis_progress — 分析进度统计（已命名/已注释/已设类型比例）
- [ ] cluster_funcs — 基于调用图连通分量自动聚类
- [ ] 相似函数检测 — CFG 哈希或字节签名找结构相似函数
- [ ] FLIRT/Lumina 集成 — 自动标记已知库函数
