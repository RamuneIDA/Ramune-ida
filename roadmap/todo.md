# Ramune-ida TODO

> 剩余未实现的功能和改进计划。

---

## 新工具

- [ ] resolve — VA ↔ 文件偏移 ↔ ASLR 运行时地址互转
- [ ] stack_frame — 函数栈帧布局查看

---

## listing 扩展

> 当前：list_funcs, list_strings, list_imports, list_names（4 个）。

- [ ] list_exports — 导出函数
- [ ] list_segments — 段信息
- [ ] list_types — 本地类型库
- [ ] list_structs — 结构体列表
- [ ] list_enums — 枚举列表
- [ ] list_entries — 入口点

---

## xrefs 增强

> 当前：xrefs(addr) — XrefsTo 按地址/名称查引用。

- [ ] 区分 code ref / data ref（可选标记）
- [ ] direction 参数：`"to"` / `"from"`（XrefsFrom）
- [ ] xrefs(struct, field) — 结构体成员 xref（依赖 ida_typeinf TID）
- [ ] xrefs(type) — 谁使用了这个类型（遍历函数签名/变量）

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

---

## 远期

- [ ] analysis_progress — 分析进度统计（已命名/已注释/已设类型比例）
- [ ] cluster_funcs — 基于调用图连通分量自动聚类
- [ ] 相似函数检测 — CFG 哈希或字节签名找结构相似函数
- [ ] FLIRT/Lumina 集成 — 自动标记已知库函数
