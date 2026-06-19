---
name: ida-pro-mcp
description: "Use for IDA Pro reverse-engineering tasks with mrexodia/ida-pro-mcp or idalib-mcp: binary analysis, decompilation, disassembly, imports/exports, strings, xrefs, call graphs, type recovery, renaming, comments, IDB annotation, obfuscation triage, and debugger-backed IDA workflows."
---

# IDA Pro MCP workflow

This skill targets `mrexodia/ida-pro-mcp` and its `idalib-mcp` headless mode. Prefer the MCP tools exposed in the current OMP session. Do not invent tools from other IDA integrations.

## Server modes

1. **Headless `idalib-mcp` supervisor**
   - Management tools include `idb_open`, `idb_list`, and `idb_save`.
   - Open or adopt a database with `idb_open(input_path, preferred_session_id=...)` unless `idb_list` already shows the desired session.
   - Every per-database tool call must pass `database=<session_id>` from `idb_open`/`idb_list`. Paths and filenames are not database IDs.
   - Use `server_health(database=<session_id>)` and optionally `server_warmup(database=<session_id>, ...)` before heavy analysis.

2. **GUI/proxy `ida-pro-mcp`**
   - IDA must have the MCP plugin/server running from the GUI (`Edit -> Plugins -> MCP`, commonly `Ctrl+Alt+M`).
   - Discovery/selection tools can include `list_instances`, `select_instance`, `open_file`, `server_health`, and `server_warmup`.
   - Use the tool schemas exposed by the active MCP server; do not add a `database` argument unless the schema requires it.

If no IDA MCP tools are available, say exactly what is missing: IDA Pro 8.3+ / 9.x, Python 3.11+, `uv` or Python package install, `ida-pro-mcp`/`idalib-mcp`, started GUI MCP plugin, or OMP MCP configuration.

## Core tool map

Use the currently exposed names, but for mrexodia/ida-pro-mcp expect these capabilities:

- Session/health: `idb_open`, `idb_list`, `idb_save`, `server_health`, `server_warmup`, `list_instances`, `select_instance`, `open_file`
- Function discovery: `lookup_funcs`, `list_funcs`, `analyze_funcs`, `callees`
- Decompiler/disassembly: `decompile`, `disasm`, `basic_blocks`
- Xrefs: `xrefs_to`, `xrefs_to_field`
- Imports/globals/strings/search: `imports`, `list_globals`, `find_regex`, `find_bytes`, `find_insns`, `find`
- Memory/data reads: `get_bytes`, `get_int`, `get_string`, `get_global_value`
- Types/structs/stack: `declare_type`, `set_type`, `infer_types`, `search_structs`, `read_struct`, `stack_frame`, `declare_stack`, `delete_stack`
- IDB annotation/mutation: `rename`, `set_comments`, `add_bookmark`, `define_func`, `define_code`, `undefine`
- Patching: `patch_asm`, `patch`, `put_int`
- Graph/export/Python: `callgraph`, `export_funcs`, `py_eval`
- Conversion: `int_convert`
- Debugger extension: `dbg_start`, `dbg_exit`, `dbg_continue`, `dbg_run_to`, `dbg_step_into`, `dbg_step_over`, `dbg_bps`, `dbg_add_bp`, `dbg_delete_bp`, `dbg_toggle_bp`, `dbg_regs*`, `dbg_stacktrace`, `dbg_read`, `dbg_write`

Useful MCP resources, if exposed: `ida://idb/metadata`, `ida://idb/segments`, `ida://idb/entrypoints`, `ida://cursor`, `ida://selection`, `ida://types`, `ida://structs`, `ida://import/{name}`, `ida://export/{name}`, `ida://xrefs/from/{addr}`.

## Standard analysis flow

1. **Establish context**
   - Identify the target binary/IDB and server mode.
   - Open/adopt the database if using headless mode.
   - Run `server_health`; warm Hex-Rays/string caches if available.
   - Inspect metadata, segments, entrypoints, imports, exports, and strings before deep function work.

2. **Triage without guessing**
   - Use `imports` for API families: file, registry, process, crypto, compression, network, UI, anti-debug, VM, and platform runtime.
   - Use `list_funcs`/`lookup_funcs` for likely entry and domain names: `main`, `WinMain`, `start`, `init`, `verify`, `check`, `decrypt`, `decode`, `hash`, `crypto`, `network`, `handler`.
   - Use `find_regex` for visible strings and error messages; paginate until the relevant result set is exhausted.
   - Use `callgraph`/`callees` from entrypoints or suspicious functions to bound the component.

3. **Analyze functions from evidence**
   - Start with `analyze_funcs` when available for a broad bundle: decompilation, assembly, xrefs, callees/callers, strings, constants, and basic blocks.
   - Use `decompile` for semantics and `disasm`/`basic_blocks` when control flow, flags, calling convention, stack layout, or decompiler output is unclear.
   - Use `xrefs_to` and `xrefs_to_field` to validate who reads/writes important functions, globals, strings, and structure fields.
   - Use `get_bytes`, `get_int`, `get_string`, and `get_global_value` to confirm data instead of inferring it from names.

4. **Improve the IDB deliberately**
   - Rename functions, globals, locals, and stack variables with `rename` only after evidence supports the name.
   - Add concise factual comments with `set_comments`; comments should state behavior, invariants, data formats, and unresolved uncertainty.
   - Apply types with `set_type`, `declare_type`, and `infer_types` when they improve decompilation or document real structure.
   - Prefer batch operations for related renames/comments/types, but keep each batch reviewable.
   - After mutating the IDB, re-read the affected decompilation/disassembly or exported prototype to verify the improvement.

5. **Handle obfuscation first, safely**
   - Identify the mechanism before interpreting behavior: string encryption, import hashing, control-flow flattening, code encryption, anti-debug, anti-decompiler tricks, or packed regions.
   - Use `py_eval` or local scripts to reproduce decoders and produce intermediate evidence. Keep scripts simple and deterministic.
   - Do not modify the original binary by default. Patch the IDB only when the user asks, or when non-destructive analysis patches are clearly required and reversible.
   - Prefer Lumina/FLIRT/type libraries when available to remove library/STL noise before analyzing custom code.

6. **Convert and calculate safely**
   - Never convert number bases, byte order, ASCII, or packed integers mentally. Use `int_convert`.
   - For non-trivial arithmetic, checksums, hashing, or crypto experiments, use a small script and report inputs/outputs.
   - Do not brute force secrets unless the user explicitly asks. Derive conclusions from decompilation/disassembly and use scripts only to verify or replay identified logic.

7. **Debug only when static analysis is insufficient**
   - Enable/use debugger tools only when the MCP server exposes the debug extension and the task needs runtime state.
   - Set minimal breakpoints, read registers/stack/memory, and avoid changing process state unless required.
   - Treat debugger writes and patches as mutating operations; explain the reason before using them.

## Pagination, batching, and evidence

- Paginated tools use offsets/cursors. Continue only while relevant and stop when the tool reports done or the result set is no longer useful.
- Batch APIs often return per-item `{error}` fields. Check every item, not just the top-level response.
- Connectivity errors may mean the GUI plugin stopped or the headless worker expired. Re-run health/listing before retrying a mutating operation.
- Do not present guesses as facts. Ground every claim in a tool result, decompiler line, disassembly behavior, import/string/xref, runtime observation, or script output.

## Reporting

- If the user asks for a report file, create concise `RE/*.md` or the requested path with findings, evidence, renamed symbols/types, and open questions.
- If no report file is requested, answer in chat with: target, key findings, evidence, IDB changes made, verification performed, and remaining uncertainty.
- Do not create `report.md` or other documentation files solely because a generic prompt says to; create files only when requested or necessary for the task.
