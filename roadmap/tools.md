# MCP Tools

> 设计哲学：输入宽容，输出诚实。
> 工具 = 高级意图，不是低级 API。MCP 吸收 IDA 内部复杂性。
> 处理不了的返回明确错误 + 补救建议，让 AI 用 execute_python 兜底。

---

## 核心原则

1. **输入宽容** — AI 给模糊意图，MCP 尽力推断正确的 IDA API 路径
2. **输出诚实** — 说人话，明确说做了什么
3. **失败有指导** — 处理不了返回原因 + 补救建议，让 AI 用 execute_python 兜底
4. **统一同类** — rename/set_type 等根据参数组合智能路由到不同 IDA API
5. **无 default project** — 所有工具都传 project_id，无歧义
6. **project/database 分离** — project 是工作上下文，database 是 IDB 生命周期

---

## 工具总览

| 类别 | 工具数 | 工具 |
|------|--------|------|
| 分析 | 4 | decompile, disasm, xrefs, survey |
| 标注 | 3 | rename, get_comment, set_comment |
| 数据 | 2 | examine, get_bytes |
| 列表 | 4 | list_funcs, list_strings, list_imports, list_names |
| 搜索 | 2 | search, search_bytes |
| 类型 | 2 | set_type, define_type |
| 执行 | 1 | execute_python |
| 撤销 | 1 | undo |
| 会话 | 7 | open_project, close_project, projects, open_database, close_database, get_task_result, cancel_task |
| **合计** | **26** | 19 个插件工具 + 7 个会话工具 |

---

## 分析工具

### decompile(func) ✅
反编译函数。func 可以是地址、函数名。最核心的工具。

**待实现：范围/摘要模式。**
大函数（VM dispatcher 等 2000+ 行）截断后无法指定查看局部。
需要支持：行范围（start_line/end_line）或摘要模式（签名+调用+字符串+控制流概览）。

### disasm(addr, count?) ✅
反汇编指令。decompile 失败时的后备。

### xrefs(addr) ✅
交叉引用。第一版实现经典地址 xref（idautils.XrefsTo）。

**待实现：** struct/field xref、type xref、direction to/from、code/data ref 区分。

### survey() ✅
二进制概览。一次返回文件信息、段、入口点、函数统计、导入摘要、字符串数量。

---

## 标注工具

### rename(addr | func+var, new_name) ✅
智能路由：addr → 函数/全局重命名，func+var → 局部变量重命名。

### get_comment(addr | func) ✅
读注释。addr → 汇编行注释，func → 函数头注释。

### set_comment(addr | func, comment) ✅
写注释。addr → 汇编行注释，func → 函数头注释。空字符串清除注释。

---

## 数据读取工具

### examine(addr, size?) ✅
地址自动类型检测：string / code / data (qword/dword/word/byte) / struct / unknown。

### get_bytes(addr, size) ✅
原始字节读取，返回 hex 字符串。

---

## 列表工具

### list_funcs / list_strings / list_imports / list_names ✅
统一分页+过滤（filter, offset, count）。

**待实现：** list_exports, list_segments, list_types, list_structs, list_enums, list_entries

---

## 搜索工具

### search(pattern, type?, count?) ✅
正则搜索。type 可选 all/strings/names/types/disasm。

### search_bytes(pattern, count?) ✅
字节模式搜索，hex + ?? 通配符。

**待实现：** 反编译结果搜索、立即数搜索、注释搜索

---

## 类型系统工具

### set_type(addr+type | func+var+type) ✅
智能路由：
- addr → 函数签名（idc.SetType fallback apply_tinfo）或全局数据类型（apply_tinfo）
- func+var → 局部变量类型（Hex-Rays lvar.set_lvar_type + set_user_type）

内部使用 `_parse_tinfo` 三策略解析：get_named_type → parse_decl(dummy var) → tinfo_t constructor。

### define_type(declare) ✅
C 声明模式（parse_decls）。支持 struct/enum/typedef/union。
重复声明同名类型会更新。返回已创建类型的 name/size/kind。

**设计决策：** 增量编辑（按 offset 添加/修改字段）推迟到后续版本。当前通过整体重声明实现更新。

---

## 执行工具

### execute_python(code, timeout?) ✅
在 idalib 环境中执行任意 IDAPython。
- stdout/stderr 分别捕获返回
- _result 变量作为结构化返回值
- 完整 traceback 在 error 字段返回
- 预注入 idaapi, idc, idautils
- timeout 默认 60s

---

## 撤销工具

### undo(count?) ✅
IDA 9.0+ 原生 undo。返回 undone 操作的 label 列表。
`kind:write` 工具执行前由框架自动创建 undo point。

---

## 会话工具

open_project, close_project, projects, open_database, close_database, get_task_result, cancel_task

---

## 待实现工具

### resolve(addr, base?)
三者互转：文件偏移 ↔ IDA VA ↔ 实际内存地址（ASLR）。

### stack_frame(func)
查看函数栈帧布局。
