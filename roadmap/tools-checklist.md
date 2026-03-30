# MCP Tools — AI-First 设计

> 设计哲学：输入宽容，输出诚实。
> 工具代表高级意图，不是低级 API 调用。
> MCP 层吸收 IDA 内部复杂性，AI 只需表达"我想做什么"。
> 处理不了的返回明确错误 + 补救建议，让 AI 用 execute_python 兜底。

---

## 分析工具

### decompile(func)
反编译函数。func 可以是地址、函数名。最核心的工具。

**待设计：范围/摘要模式。**
大函数（VM dispatcher 等 2000+ 行）截断后无法指定查看局部。
需要支持：行范围（start_line/end_line）或摘要模式（签名+调用+字符串+控制流概览）。
具体方案实现时再定。

### disasm(addr, count?)
反汇编指令。decompile 失败时的后备。

### xrefs(addr?, struct?, field?, type?)
获取交叉引用。多种输入形式，MCP 内部路由：
- xrefs(addr="0x401000") → 经典地址/函数 xref（idautils.XrefsTo）
- xrefs(struct="MyStruct", field="key") → 结构体成员 xref（ida_typeinf TID xref，需 struct 已 apply）
- xrefs(type="MyStruct") → 谁使用了这个类型（遍历函数签名/变量，尽力而为）
- 神秘偏移搜索不在此工具范围，属于 search 或 execute_python
- 第一版先实现经典地址 xref，接口预留扩展

**待设计：callees / callgraph 能力。**
架构分析核心需求——"这个函数调用了谁"以及"从入口展开 N 层调用关系"。
方案待定：作为 xrefs 的 direction/depth 扩展，或独立工具。

### survey()
二进制概览。一次返回文件信息、段、入口点、函数统计、导入摘要、字符串数量。

---

## 查询工具

### list(what, filter?, offset?, count?)
统一列表工具。对应 IDA 的各个 View 窗口，每个都是行表单。
支持分页和过滤。MCP 内部根据 what 路由到不同的 IDA API。

what 可选值（对应 IDA View）：
- "funcs" — Functions window
- "strings" — Strings window
- "imports" — Imports window
- "exports" — Exports window
- "segments" — Segments window
- "types" — Local Types window
- "structs" — Structures window
- "enums" — Enums window
- "names" — Names window（所有命名地址：函数+全局+标签）
- "entries" — Entry points

后续可按需扩展更多 view。

### search(pattern, type?)
统一搜索。type 不指定时 MCP 自动判断：
- 纯 hex 字符 → 字节搜索（ida_bytes.find_bytes）
- 含通配符（?）→ 字节模式搜索
- 否则 → 字符串正则搜索（idautils.Strings + re）

**远期考虑：search everything 模式。**
IDA 本质是基于文本的程序，可以对所有可见文本做全文匹配——
函数名、字符串、反汇编文本、注释、类型名等统一搜索。
实现方式：首次调用时构建全量索引并缓存，后续增量更新。
慢一点没关系，AI 不会等急。

### read(addr, size?, format?)
统一数据读取。IDA 对每个地址都有类型标记，read 利用这一点智能返回。

format 不指定时，根据 IDA 的地址标记（ida_bytes.get_flags）自动判断：
- string → 返回字符串内容
- code / function → 返回反汇编（或提示用 decompile）
- data (byte/word/dword/qword) → 返回对应整数值
- array → 返回数组内容
- struct → 返回结构体字段 + 值
- unknown → 返回 raw hex bytes

显式 format 覆盖自动判断："bytes" | "string" | "int8" | "int16" | "int32" | "int64"

返回中附带 IDA 标记的类型信息，让 AI 知道这个地址上是什么。

**设计备注：read 的核心价值是 IDA 的分析智能（类型检测），不是原始字节 I/O。**
原始字节读写和 patch 不需要经过 IDA——AI 可以直接操作文件。
patch 功能因此不作为独立工具，AI 通过文件操作自行完成。
地址映射见下方 resolve 工具。

### resolve(addr, base?)
三者互转：文件偏移 ↔ IDA VA ↔ 实际内存地址（ASLR）。
高频操作，单独接口。
- resolve(addr="0x401000") → {va, file_offset, rva}
- resolve(addr="0x401000", base="0x7FF600000000") → 附加 runtime_addr（VA + ASLR base）
- resolve(file_offset=0x600) → 反向查 {va, file_offset, rva}

IDA API：segment 信息（start_ea, offset, delta）可算出全部映射。
base 参数让 AI 传入 ASLR 基址后直接得到调试器中的真实地址。

---

## 修改工具

### rename(targets)
智能重命名。targets: [{addr, name}] 或 [{func, var, name}]。
- 只给 addr + name → MCP 判断是函数/全局，调 set_name
- 给 func + var + name → MCP 调 rename_lvar 重命名局部变量/参数
- 失败时返回明确原因 + 建议（如"这可能是局部变量，请提供 func 上下文"）

### set_type(targets)
智能设类型——给已有的东西设置/修改类型。
- {addr, type} → apply_tinfo 到函数/全局
- {func, var, type} → modify_user_lvars 改局部变量/参数类型

### define_type(actions)
定义和构建类型——创建新的结构体/枚举/typedef，或增量编辑已有类型。
逆向核心工作流：边分析边填充 struct。

**整体声明：**
- {declare: "struct Foo { int a; char b; };"} → parse_decls

**增量编辑：**
- {struct, size} → 创建空结构体或调整大小
- {struct, offset, name, type} → 在指定偏移添加/修改字段
- {struct, field, name?, type?} → 按名字修改已有字段
- {struct, field, delete: true} → 删除字段
- 枚举同理：{enum, member, value} 等

示例：
```
define_type([
  {"struct": "VTable", "size": 256},
  {"struct": "VTable", "offset": 0, "name": "destroy", "type": "void (*)(void *)"},
  {"struct": "VTable", "offset": 8, "name": "process", "type": "int (*)(void *, int)"},
])
```

### set_comment(targets)
设置注释。targets 列表，两种模式：
- {addr, comment} → 汇编级注释（idaapi.set_cmt），地址是函数入口则自动设为函数注释
- {func, line, comment} → 反编译伪代码级注释（Hex-Rays user comment），line 是 F5 视图中的行号

### undo()
撤销上一次修改。

---

## 执行工具

### execute_python(code, timeout?) ✅ 已实现
在 idalib 环境中执行任意 IDAPython。
万能后备，覆盖所有上面工具处理不了的场景。
- stdout/stderr 分别捕获返回
- _result 变量作为结构化返回值（保留原始类型，不 str 化）
- 完整 traceback 在 error 字段返回（与 stderr 分离）
- 预注入 idaapi, idc, idautils（IDA Console 标准环境，其他模块 AI 自行 import）
- timeout 是唯一暴露超时参数的工具（AI 脚本复杂度不可预知），默认 60s
- 其他工具的超时由 server 层按命令类型内部设定，不暴露给 AI

实现文件：
- server/tools/python.py — MCP 工具
- worker/handlers/python.py — Worker handler（exec + namespace 构建 + stdout/stderr 重定向）
- protocol.py Method.EXEC_PYTHON + commands.py ExecPython

**超时与取消策略（全局）：** ✅ 已实现
- 超时不等于失败，返回 task_id 供 AI 轮询
- cancel 优先优雅取消（两阶段）：
  - 排队中的命令 → 直接从队列移除
  - 执行中 → SIGUSR1 + sys.setprofile cancel flag（Python 函数调用边界可中断）
  - 5s 看门狗超时 → SIGKILL 强杀（C 扩展阻塞时的兜底）
- survey / list 等可能遍历大量数据的操作，handler 内部应检查 cancel flag 做分段返回

实现文件：
- worker/cancel.py — 取消标志模块（request/is_requested/reset）
- worker/dispatch.py — CancelledError + sys.setprofile hook 安装
- worker/main.py — SIGUSR1 信号注册
- worker_handle.py — send_signal() 方法
- project.py — cancel_task 两阶段 + _delayed_kill 看门狗

---

## 会话工具

**设计决策：**
- 去掉 default project 概念，所有工具都传 project_id，无歧义
- 超上限时 server 自动关最旧的 project，返回提示告知 AI
- 去掉 snapshot 机制。AI 通过 close_database + 文件下载/上传自行管理备份
- project 和 database 拆分：project 是工作上下文，database 是 IDB 生命周期

**项目生命周期：**

### open_project()
创建工作上下文（work_dir, project_id），不打开数据库。

### close_project(project_id)
销毁项目，清理 work_dir。内部自动 close_database。

### projects()
列出所有打开的项目及状态（是否有 database 打开、当前文件路径等）。

**数据库生命周期（在 project 内）：**

### open_database(project_id, path, recovery?)
打开二进制或 IDB。所有文件路由逻辑集中在此：
- path 是二进制 → IDA 创建新 IDB，触发自动分析
- path 是 .i64/.idb → IDA 直接加载已有 IDB，不重新分析
- recovery: "auto" | "recover" | "ignore"（遇到崩溃残留文件的策略）
- 同一 project 可以 close_database 后 open_database 另一个文件

### close_database(project_id, force?)
关闭 worker 释放 IDB 文件锁，project 保持存活。
默认优雅关闭（save + exit），force=true 直接 kill 不保存。
典型工作流：
- 备份：close_database → 下载 IDB
- 恢复：close_database → 上传旧 IDB 覆盖 → open_database 重新打开
- 切换：close_database → open_database(另一个文件)

**异步任务：**

### get_task_result(task_id, project_id)
轮询异步任务结果。

### cancel_task(task_id, project_id)
取消任务。优先优雅取消，降级为 kill + respawn。

---

## 总计

| 类别 | 工具数 | 工具 |
|------|--------|------|
| 分析 | 4 | decompile, disasm, xrefs, survey |
| 查询 | 4 | list, search, read, resolve |
| 修改 | 5 | rename, set_type, define_type, set_comment, undo |
| 执行 | 1 | execute_python |
| 会话 | 7 | open_project, close_project, projects, open_database, close_database, get_task_result, cancel_task |
| **合计** | **21** | 其中分析/查询/修改/执行 = **14 个核心工具** |
