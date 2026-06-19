# 项目目录

主目录：`~/coding`

| 子目录 | 技术栈 |
|---|---|
| `WebStormProjects/` | TypeScript, Vue 3, Quasar, Angular, Elysia, Fastify, Electron, Bun, Node.js, Drizzle ORM |
| `GolandProjects/` | Go |
| `ClionProjects/` | C/C++ (C++23), CMake, vcpkg, Windows DLL 工具 |
| `PycharmProjects/` | Python 3, FastAPI, Flask, SQLAlchemy v2, pandas, mitmproxy |
| `OtherProjects/` | Tauri, Rust, Terraform, Docker, 游戏 Mod, 混合项目 |
| `DataGripProjects/` | PostgreSQL, MySQL, SQLite |
| `OfficeAddinProjects/` | TypeScript, React 18, Office.js, Fluent UI |
| `WritersideProjects/` | JetBrains Writerside 技术文档 |

查找项目时：忽略大小写和分隔符差异，支持部分匹配，根据技术栈关键词优先在对应子目录查找。多项目匹配时询问用户。

# IDA Pro 逆向分析（MCP）

使用 IDA Pro MCP 工具进行逆向工程分析时，遵循以下规范：

## 分析流程

1. **首先调用 `survey_binary`** 获取二进制概览（文件信息、段布局、入口点、关键字符串/函数、导入分类、调用图摘要），不要单独调 `list_funcs`/`imports`/`find_regex` 做初筛
2. **反编译分析** — 仔细检查伪代码输出，添加注释记录发现
3. **提升可读性** — 重命名变量/函数为有意义的名称；修正变量、参数类型（尤其是指针和数组类型）
4. **深入汇编** — 反编译不够清晰时查看反汇编，添加底层行为注释
5. **组件分析** — 对关联函数使用 `analyze_component` 做整体分析
6. **产出报告** — 分析完成后整理发现和步骤

## 关键约束

- **绝对不要自行做进制转换** — 必须使用 `int_convert` MCP 工具
- **不要暴力破解** — 所有结论必须从反汇编/反编译中推导，辅以简单 Python 脚本验证
- **混淆代码先处理** — 字符串加密、导入哈希、控制流平坦化、代码加密、反反编译手段等，应先（自动）去除再让 LLM 分析
- **利用签名匹配** — 使用 Lumina/FLIRT 解析开源库和 C++ STL 代码，减少噪声
- **善用批量操作** — `rename`（批量重命名）、`set_comments`（批量注释）、`type_apply_batch`（批量类型）等支持一次操作多个目标

## 工具使用提示

- `survey_binary` → 初始分析入口
- `analyze_function` / `analyze_batch` → 单函数/多函数深度分析
- `analyze_component` → 关联函数组分析
- `decompile` / `disasm` → 伪代码/反汇编
- `xrefs_to` / `xref_query` / `trace_data_flow` → 交叉引用与数据流追踪
- `callgraph` → 调用图
- `find_bytes` / `find_regex` / `search_text` / `insn_query` → 模式搜索
- `rename` → 批量重命名（函数/全局变量/局部变量/栈变量）
- `set_type` / `infer_types` → 类型应用与推断
- `diff_before_after` → 重命名/改类型后对比前后伪代码，验证改善效果
- `int_convert` → 进制转换（**唯一允许的方式**）
- `py_eval` → 在 IDA 上下文中执行任意 Python 代码
- `make_signature` / `find_xref_signatures` → 生成字节签名
