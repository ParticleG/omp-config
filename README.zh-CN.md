# omp 配置（`~/.omp`）

[English](README.md) | **简体中文**

本仓库对终端编程代理 [oh-my-pi（omp）](https://github.com/can1357/oh-my-pi) 的用户级配置做版本管理。仓库直接位于 omp 的默认配置根目录 `~/.omp`，omp 原地读取其中的文件；`agent/` 是当前生效的 agent 目录（可用 `omp config path` 查看）。配置面向 **omp 18.14**，通过 Arch Linux 软件包 `oh-my-pi` 安装。

Git 只跟踪手工维护的文件：设置、模型路由、提示词文件、一个自定义子代理（subagent）、一个事件 hook、一个自定义工具、技能（skill）、browser-relay 扩展、插件清单以及自托管记忆服务。运行时状态由 `.gitignore` 排除：SQLite 数据库（`agent.db`、`history.db`、`models.db` 等）、会话、blob、缓存、日志、记忆、worktree（`wt/`）以及所有 `node_modules/`。

文中引用的默认值来自 omp 18.14 的设置 schema，通过在空 agent 目录上运行 `omp config list --json` 读取。

## 目录

- [仓库结构](#仓库结构)
- [新机器部署](#新机器部署)
- [agent/agents/fixer.md](#agentagentsfixermd)
- [agent/hooks/post/webhook-notifier.ts](#agenthookspostwebhook-notifierts)
- [agent/rules/lark-cli-tool.md](#agentruleslark-cli-toolmd)
- [agent/skills/](#agentskills)
- [agent/tools/lark-cli.ts](#agenttoolslark-clits)
- [AGENTS.md / APPEND_SYSTEM.md / RULES.md](#agentsmd--append_systemmd--rulesmd)
- [agent/config.yml](#agentconfigyml)
- [agent/models.yml](#agentmodelsyml)
- [browser-relay/extension/](#browser-relayextension)
- [plugins/](#plugins)
- [其他文件](#其他文件)
- [检查生效配置](#检查生效配置)

## 仓库结构

| 路径 | 用途 |
|---|---|
| `agent/config.yml` | 全局设置：模型角色、工具、子代理、记忆、界面 |
| `agent/models.yml` | 自定义 provider、网关路由与模型元数据 |
| `agent/AGENTS.md` | 用户级上下文：项目目录地图 |
| `agent/APPEND_SYSTEM.md` | 追加到系统提示词末尾的内容：语言与工程偏好 |
| `agent/RULES.md` | 随每次请求发送的常驻规则：密码输入与确认安全 |
| `agent/agents/fixer.md` | 自定义子代理 `fixer` |
| `agent/hooks/post/webhook-notifier.ts` | 在运行结束或需要用户操作时发送 webhook 的扩展 |
| `agent/rules/lark-cli-tool.md` | 引导 `lark-*` 技能改用 `lark_cli` 工具的规则 |
| `agent/tools/lark-cli.ts` | 封装飞书/Lark CLI 的自定义工具 `lark_cli` |
| `agent/skills/` | 六个本地技能 |
| `agent/feishu-safe.yml` | 处理飞书事务时按需启用的设置覆盖层（overlay） |
| `agent/mcp.json` | MCP 服务器：Blender、BOSS 直聘 |
| `agent/mem0.yml` | 旧版 mem0 记忆覆盖层 |
| `agent/.clawhub/lock.json` | `easyeda-api` 技能的 ClawHub 安装锁 |
| `browser-relay/extension/` | `omp browser-relay` 使用的 Chrome 扩展 |
| `plugins/` | 插件清单、Bun 锁文件与启用状态 |
| `marketplaces.json` | 已登记的插件市场（`anthropics/claude-plugins-official`） |
| `hindsight/` | Hindsight 记忆服务的 Docker Compose 文件，以及 Mnemopi → Hindsight 迁移工具 |
| `openai-analysis.md` | Artificial Analysis 基准笔记：GPT-5.6 Luna/Sol 各推理档位的成本、耗时与得分 |
| `package.json`、`tsconfig.json`、`bun.lock` | 编辑 `.ts` 文件所需的 TypeScript 类型（`@oh-my-pi/pi-coding-agent`、`@types/bun`） |
| `puppeteer/package.json` | 位于 Puppeteer 下载的 Chrome（`puppeteer/chrome/`，已忽略）旁的空清单 |

## 新机器部署

1. 安装 omp 18.14 或更高版本，并把本仓库克隆到 `~/.omp`。
2. 导出配置引用的凭据：

   | 变量 | 使用方 |
   |---|---|
   | `AMINOS_API_KEY` | `agent/models.yml` 中的 `anthropic` 与 `antigravity` provider |
   | `STUDIO26F_API_KEY` | `openai-codex` 与 `cpa-studio26f` provider；`hindsight/compose.yaml` 中 Hindsight 使用的 LLM |
   | `DEEPSEEK_API_KEY`（或 `/login`） | `smol`、`tiny`、`judge` 角色背后的内置 `deepseek` provider |
   | `OMP_SESSION_WEBHOOK_URL`、`OMP_SESSION_WEBHOOK_TOKEN` | 可选；启用 [webhook-notifier](#agenthookspostwebhook-notifierts) |
   | `EDGEONE_API_KEY` | 可选；`zhuque` 技能调用 EdgeOne Makers 时使用 |

   provider 的 `apiKey` 所指的环境变量未设置时，omp 会把变量名本身当作密钥使用，因此要在启动 omp 之前导出这些变量。
3. 启动记忆服务：`docker compose -f ~/.omp/hindsight/compose.yaml up -d`。服务未运行时，Hindsight 的 recall 与 retain 会因 `ECONNREFUSED` 失败，会话照常进行但没有记忆。
4. 重新安装插件（`plugins/node_modules/` 不受 Git 跟踪）：

   ```bash
   omp plugin install github:ParticleG/omp-keysmith
   omp plugin install github:ParticleG/china-targeted-resume-plugin
   ```

5. 安装 EasyEDA 桥接依赖：`cd ~/.omp/agent/skills/easyeda-api && npm install`。
6. 在 Chrome 中以“加载已解压的扩展程序”方式加载 `~/.omp/browser-relay/extension/`（见 [browser-relay/extension/](#browser-relayextension)）。
7. 可选：为编辑器中的 `.ts` 类型检查安装依赖：`cd ~/.omp && bun install`。

## agent/agents/fixer.md

`fixer` 是一个自定义子代理。omp 扫描 `agent/agents/*.md`，并把其中的 agent 与内置 agent 一起提供给 `task` 工具。`fixer` 面向需求明确、范围有界的工作：编写或更新测试、机械式重构（重命名、模式替换），以及把已知改动应用到多个文件。

| Frontmatter | 值 | 作用 |
|---|---|---|
| `name` | `fixer` | `task` 调用中使用的 agent 名称（`"agent": "fixer"`） |
| `description` | “Fast execution specialist …” | 显示在 `task` 工具的 agent 列表中，父模型据此挑选 agent |
| `model` | `[pi/smol]` | `pi/` 是角色别名的旧前缀（等同 `@smol`），因此模型经由 `modelRoles.smol` 解析，当前为 `deepseek-flash` |
| `thinkingLevel` | `low` | 声明的推理档位。由于开启了 `task.enableEffort`，调用方为单个任务传入的 `effort`（`lo`/`med`/`hi`）在启动时优先 |
| `spawns` | `[explore]` | `fixer` 可以再启动的 agent。omp 18.14 没有名为 `explore` 的 agent（只读探索 agent 是 `scout`），所以这一项实际上不授予任何可用目标 |

Markdown 正文就是该 agent 的系统提示词：拥有完整工具权限；只处理指派的目标及其直接相关的调用点或测试；输出简洁、不附工具记录；先做窄范围查找再读取所需片段；优先修改已有文件；除非明确要求，不新建 Markdown 文件或 mock；需求不清时提问而不是猜测；坚持到任务完成。

**为什么这样设计：** 有界的机械性工作不需要主模型。把它交给廉价的 `smol` 角色（DeepSeek V4.1 Flash），可以把运行在 GPT-6.1 Sol 上的默认 `task` agent 留给开放性工作。

## agent/hooks/post/webhook-notifier.ts

一个 omp 扩展模块：在 agent 运行结束或会话等待用户操作时发送 webhook。omp 会把 `agent/hooks/pre/` 与 `agent/hooks/post/` 下所有 `.ts`/`.js` 工厂函数通过扩展管线加载；目录名只是发现用的元数据。该工厂用 `pi.on(...)` 订阅生命周期事件，是纯粹的被动观察者：从不阻塞或修改事件，从不执行工具，也从不读取消息正文或凭据文件。它基于 omp 18.12.6 编写，只发送第 2 版负载。

### 事件

| 事件 | 发送时机 | `status` |
|---|---|---|
| `omp.run_finished` | 一次 agent 运行结束，且没有待续的回合或后台任务 | `completed`、`failed`、`aborted` 或 `unknown` |
| `omp.action_required` | 在交互式界面中，工具审批提示、计划评审或 `ask` 调用出现 150 ms 后仍未处理 | `action_required` |

- 状态取自最后一条助手消息的停止原因（`stop` → `completed`，`error` → `failed`，`aborted` → `aborted`）。自动重试期间，结果会等待重试结论；重试失败则报告 `failed`。
- 正常完成的子代理运行不会单独发送，而是出现在根运行的 `subagentTimeline` 中；失败、中止或状态未知的子代理结束会单独发送。
- 切换会话、分支或树导航、退出以及 24 小时过期，都会以 `unknown` 状态关闭未结束的运行，并在 `cycle.reasons` 中记录原因。
- 无界面（headless）会话只为等待时间线记录交互，从不发送 `action_required`。

### 配置

| 变量 | 必需 | 含义 |
|---|---|---|
| `OMP_SESSION_WEBHOOK_URL`（后备 `ONEBOT_WEBHOOK_URL`） | 是 | `http`/`https` 地址，不得包含用户凭据、查询串或片段 |
| `OMP_SESSION_WEBHOOK_TOKEN`（后备 `ONEBOT_WEBHOOK_TOKEN`） | 是 | Bearer 令牌，最长 4096 字符，不含换行 |
| `OMP_SESSION_WEBHOOK_TIMEOUT_MS`（后备 `ONEBOT_WEBHOOK_TIMEOUT_MS`） | 否 | 单次尝试超时，100–30000 之间的整数，默认 5000 |
| `OMP_SESSION_WEBHOOK_INSTANCE` | 否 | 写入负载 `instance` 字段的标签 |

URL 或令牌缺失、无效时，模块记录 `configuration_missing` 或 `configuration_invalid`，不发送任何内容。

### 请求与负载

每条通知都是带 JSON 正文的 `POST` 请求，请求头为 `Authorization: Bearer <token>`、`X-OMP-Event: <event>` 和 `User-Agent: omp-webhook-notifier-v2`，不跟随重定向。

```json
{
  "event": "omp.run_finished",
  "version": 2,
  "id": "6f1c0d2e9a8b4c7d5e3f1a2b3c4d5e6f",
  "emittedAt": "2026-11-02T07:41:39.183Z",
  "session": { "ref": "<hmac>", "scope": "root", "name": "Fix login bug", "cwdName": "my-app" },
  "cycle": {
    "ref": "<random>", "timeBasis": "receipt_monotonic", "partial": false, "reasons": [],
    "startedAt": "2026-11-02T07:40:18.001Z", "endedAt": "2026-11-02T07:41:39.183Z", "durationMs": 81182,
    "model": "openai-codex/gpt-6.1-sol", "thinking": "max"
  },
  "status": "completed",
  "subagentTimeline": { "version": 1, "items": [] },
  "userWaitTimeline": { "version": 1, "intervals": [] }
}
```

- `session.scope` 为 `root`、`subagent` 或 `unknown`；omp 提供 agent 名称时，`session.agent` 会携带它。
- `omp.action_required` 额外包含 `interaction: { ref, kind }`，`kind` 为 `approval`、`plan_review` 或 `ask`。
- 只有根运行的 `omp.run_finished` 携带两条时间线（上例已省略内容）：各子代理片段的偏移、时长、模型与推理档位，以及用户等待区间。每条最多 64 项，体积上限分别为 23 KiB 和 11 KiB；`partial`、`partialReasons`、`truncated` 标记观测缺口。
- `cycle.partial` 与 `cycle.reasons`（`missing_start`、`session_changed`、`shutdown`、`expired`、`capacity`、`unpaired_interaction`、`incomplete_metadata`、`clock_changed`）标记不完整的观测。

### 投递

- 有界队列最多 64 个任务，同时最多 2 个请求在途。
- 遇到 HTTP 429、5xx、超时和网络错误时最多尝试 3 次。第一次失败后等待 250 ms，第二次失败后等待 1 s；若 429 的 `Retry-After` 更长则采用它（上限 5 s）。其他 4xx 不重试。
- 重试会复用同一个 `id`，接收端应把 `id` 当作幂等键。
- 若用户在发送前已经处理了交互，对应的 `action_required` 通知会被丢弃。
- 结果以带 `category` 的 `OMP webhook` 警告写入日志。接收端以 `{"code": 0, "message": "ok", "data": {"delivered": true, "retryable": false}}` 表示成功；模块还识别 `message: "skipped"`（`data.skip_reason` 为 `idempotency_replay` 时记为 `replayed`，`data.skipped` 为 `true` 时记为 `policy_skipped`）、`partial_delivery` 和 `partial_failure`。超过 8 KiB 的响应正文不会被解析。

### 隐私

- 会话与 agent 标识替换为 HMAC-SHA256 摘要，密钥是每个进程随机生成的盐，因此不同 omp 进程之间的引用无法关联。
- 文本字段会去除 ANSI 与控制字符并截断（96 字符；模型 id 为 128），看起来像 URL 或文件系统路径的值会被丢弃。工作目录只发送目录名。
- 不包含消息文本、工具参数或凭据。

## agent/rules/lark-cli-tool.md

用户级规则文件，omp 会扫描 `agent/rules/*.md`。它规定 `lark-*` 技能应如何调用飞书/Lark CLI：

- `lark-*` 技能需要运行 `lark-cli` 时，调用自定义工具 `lark_cli`（[agent/tools/lark-cli.ts](#agenttoolslark-clits)）；
- 在 `args` 中传入 argv 词元，不带 `lark-cli` 可执行文件名，也不做 shell 转义；
- 不通过 Bash、Eval、Task 或生成的脚本运行 `lark-cli`；
- 保持固定的 `omp-user` profile 与用户身份；
- 读命令可自动批准，写命令需要审批，高风险写操作仍由 CLI 自身策略拦截。

`lark-*` 技能本身位于 `~/.agents/skills/`，不在本仓库中。

> **加载注意事项。** omp 按 frontmatter 给规则文件分类：`alwaysApply: true` 会把正文注入每个系统提示词；有 `description` 的规则会列入规则手册（rulebook），由模型按需读取；`condition`、`astCondition` 或 `question` 会使其成为流式触发规则（TTSR）。本文件没有 frontmatter，omp 18.14 不会把它归入任何一类，模型也就看不到它。加上 `alwaysApply: true` 或 `description` 即可生效。

## agent/skills/

omp 扫描每个 `agent/skills/<name>/SKILL.md`，在系统提示词中列出技能名称和描述；任务匹配时，模型通过 `skill://<name>` 读取完整内容。

| 技能 | 用途 | 触发条件 | 内容与依赖 | 来源 |
|---|---|---|---|---|
| `anti-ai-foolish` | 中文公众号/自媒体长文发布前的“AI 味”终检 | 仅在用户明确要求去AI味/降AI率、发文前终检，或稿件被腾讯朱雀标记、被微信打回时使用；不用于一般润色、小说、学术、法律或英文文本 | `scripts/preflight.py`：六道硬门槛（冒号、破折号、直引号均为 0；概念引用腔与疑问句各不超过每千字 3 处；无小节标题）加 Z 分；`scripts/scanner.py`：13 个规则库共 1,108 条规则，每条都用 52 个带朱雀标签的片段做过 A/B 测试；`scripts/abtest.py`：重新验证。流程：机械预检 → 三项人工判断 → 分块“七刀手术” → 复检，最后分块送朱雀检测（目标 ≤ 0.40）。仅需 Python 3.8+ 标准库，完全离线 | v0.1.0，来自 skillhub.360.com（`forrestneo/anti-ai-foolish`），MIT |
| `codemap` | 为陌生仓库生成分层的 `codemap.md` 文档 | 仅在明确要求梳理或记录代码库时使用（开销大） | `scripts/codemap.mjs`（`init`、`changes`、`update`）把文件哈希保存在 `.slim/codemap.json`（会迁移旧的 `.slim/cartography.json`）；每个目录由一个 task agent 撰写该目录的 `codemap.md`；根目录的总图汇总各目录；在项目的 `AGENTS.md` 中加入 `## Repository Map` 小节。需要 Node.js | — |
| `easyeda-api` | 嘉立创EDA（EasyEDA Pro）API 参考与实时控制 | “嘉立创EDA，启动！”、“EDA，启动！”，或 EasyEDA、PCB、原理图、封装等关键词 | API 参考（120 个类、62 个枚举、70 个接口、19 个类型别名）、文档源码格式规范（工程、原理图、PCB）、扩展开发指南；`scripts/bridge-server.mjs` 是 WebSocket 桥接服务，占用 49620–49629 中第一个空闲端口，在已连接的嘉立创EDA 窗口内执行 JavaScript。需要 Node.js 18+、`npm install`（`ws`）以及嘉立创EDA 中的 `run-api-gateway` 扩展。桥接服务会在打开的设计中执行任意代码：先备份工程，用完即停 | v1.1.3，来自 ClawHub（`yanranxiaoxi/easyeda-api`） |
| `glab` | 正确、非交互地使用 GitLab CLI | 任何 GitLab 操作 | issue、MR、CI 速查；评论与线程回复；`glab api` 占位符及 `-f`/`-F`/`--form`/`--input` 的语义；常见错误（会打开编辑器的参数、`glab ci retry` 接收 job ID、`mr create` 必须带 `--push`） | 随 GitLab CLI 分发（`gitlab-org/cli`） |
| `simplify` | 保持行为不变的代码简化 | 理解行为之后，为提升可读性、降低复杂度时使用 | 五项原则（严格保持行为、遵循项目约定、清晰优于炫技、把握平衡、只改动相关范围）、四步流程与验证清单 | — |
| `zhuque` | 腾讯朱雀 AIGC 文本检测 | 用户想知道一段文本是否由 AI 生成、AI 率是多少（朱雀检测、检测AI率、AIGC检测、`/zhuque`），或想对比修改前后的 AI 率时使用；只检测，从不改写 | `scripts/detect.py` 把 `--text` 或 `--file` 输入发送给 EdgeOne Makers 模型 `@makers/zhuque-text`，输出 Markdown 报告：整体 AI 率（AI + 疑似 AI）、人工占比、置信度、分段标签（0 人工、1 AI、2 疑似 AI）以及被标记段落的全文；`--json` 返回原始响应，`--is-merge` 把全文作为一段评分。仅用 Python 标准库；密钥只从 `EDGEONE_API_KEY` 读取；调用消耗 Makers 免费额度（每月 50 万 token）。它把 `anti-ai-foolish` 需要手工粘贴的朱雀检测自动化了 | 改编自 `ZimingADR/zhuque-skill`（提交 `3da7558`），MIT |

会话中的技能列表还会出现 `lark-*`、`ssh`、`humanizer-zh` 和 `github-review-pr`；它们由 omp 从 `~/.agents/skills/` 加载，本仓库不跟踪。

## agent/tools/lark-cli.ts

omp 在 `agent/tools/` 中发现的自定义工具工厂（`CustomToolFactory`）。它注册 `lark_cli` 工具（标签为 “Lark CLI”）；`tools.xdev` 开启时（默认开启），模型通过 `xd://lark_cli` 设备调用它。

- **输入：** `{ "args": ["<root-command>", "…"] }`，至少一个 argv 词元。
- **执行：** 在会话工作目录中通过 `pi.exec` 运行 `lark-cli --profile omp-user <args…>`。不经过 shell，因此不存在转义、通配或命令拼接。返回去除首尾空白的 stdout 与 stderr；被取消或退出码非 0 时报错。

**执行前校验，不通过即拒绝：**

| 规则 | 目的 |
|---|---|
| 第一个词元必须是根命令，不能是选项 | 解析无歧义 |
| 禁止 `--profile` 与 `--profile=…` | profile 固定为 `omp-user` |
| 禁止 `--as bot` 与 `--as=bot` | 只允许用户身份 |
| 禁止根命令 `api`、`config`、`profile`、`update` 以及 `auth logout` | 飞书安全配置：不允许原始 API 调用、修改 CLI 配置（包括风控）、切换 profile、自我更新或登出 |

**审批等级（approval tier）。** 每次调用前，工具先运行 `lark-cli --profile omp-user <args…> --help`，读取 lark-cli 为该命令打印的 `Risk:` 行：

| `Risk:` 行 | omp 等级 |
|---|---|
| `read` | `read` |
| `write` | `write` |
| `high-risk-write` | `exec` |
| 缺失 | `auth check`、`auth qrcode`、`auth status`、`doctor`、`schema`、`skills list`、`skills read`、`whoami` 为 `read`，其余为 `exec` |

未通过校验的参数一律归为 `exec`。等级按参数列表缓存，直到进程结束；探测时会关闭 lark-cli 的更新提示与技能提示。

等级只在会弹出提示的审批模式下起作用。`config.yml` 没有修改 `tools.approvalMode`，保持默认的 `yolo`，所有等级都不询问直接执行；下文的 `feishu-safe.yml` 覆盖层切换到 `always-ask`，只有 `read` 命令无需确认。

**为什么这样设计：** 类型化的 argv 工具消除了 shell 注入和转义错误，固定了 profile 与身份，并让 lark-cli 自带的逐命令风险元数据驱动 omp 的审批提示，而不必手工维护白名单。

### agent/feishu-safe.yml

配套的覆盖层。omp 不会自动加载它，需要按进程启用：`omp --config ~/.omp/agent/feishu-safe.yml`。

| 设置 | 效果 |
|---|---|
| `tools.approvalMode: always-ask` | 只有 `read` 等级的调用无需确认 |
| `tools.approval.bash: prompt`、`tools.approval.eval: prompt` | shell 与代码执行一律询问 |
| `tools.approval.task: deny` | 禁止子代理：子代理以 `yolo` 模式无界面运行，会绕过审批提示 |
| `bash.patterns`：对 `*lark-cli*` 一律 `deny`（并单独拒绝 `config risk-control off` 与 `api`） | 所有飞书调用都必须经过 `lark_cli` |
| `secrets.enabled: true` | 文本发往模型 provider 之前，脱敏疑似密钥的环境变量值与凭据格式的令牌 |

## AGENTS.md / APPEND_SYSTEM.md / RULES.md

`agent/` 下的三个用户级提示词文件，加载方式各不相同：

| 文件 | omp 的加载方式 | 是否传给 `task` 子代理 | 内容 |
|---|---|---|---|
| `AGENTS.md` | 用户级上下文文件，渲染在主会话与 advisor 的项目说明 `<repo-rules>` 块中 | 否 | 按技术栈列出 `~/coding` 子目录（WebStorm：TypeScript/Vue/Angular/Bun 等，GoLand：Go，CLion：C++23/CMake/vcpkg，PyCharm：Python/FastAPI 等，OtherProjects：Tauri/Rust/Terraform/Docker 等，DataGrip：SQL，OfficeAddinProjects：Office.js/React，WritersideProjects：文档）；查找项目的规则（忽略大小写与分隔符、支持部分匹配、优先在对应技术栈目录查找、多个匹配时询问）；IDA Pro 逆向分析请求的技能路由 |
| `APPEND_SYSTEM.md` | 原样追加在默认系统提示词与项目上下文之后，默认提示词保持完整 | 否 | 交互使用简体中文；代码、注释和项目文档使用英文；不翻译符号、命令、路径和配置键；遵循项目风格，与官方风格有实质冲突时先确认；Plan Mode 输出使用中文；工程范围规则：尊重明确决定、选择最简单的完整方案、只在有具体需求时加闸门或回退、移除 agent 自行添加的多余内容、保持兼容性契约、按比例验证、满足验收标准即停止 |
| `RULES.md` | 名为 `RULES` 的常驻 always-apply 规则：完整正文随每次请求发送，会话开始以及 `/new`、`/clear` 时重新读取，无法改成条件规则 | 是 | 需要输入密码的命令（`sudo`、`su`、`ssh`）只能在前台 `pty: true` 的 Bash 调用中运行；禁止 `sudo -S`；密码不得出现在命令、环境变量、管道、文件或日志中；没有 PTY 时停止；只能在同一个 PTY 调用中用 `sudo -v` 复用凭据；工具无法确定的破坏性操作、权限/安全、数据迁移、外部接口、架构方向与 UI/UX 取舍必须先确认；优先使用 `ask` 工具并给出 2–5 个选项 |

**为什么分成三个文件：** omp 建议把长期背景放进 `AGENTS.md`，把少量必须在长对话中保持可见的硬性要求放进 `RULES.md`。`APPEND_SYSTEM.md` 在默认提示词之上叠加偏好，而不是像 `SYSTEM.md` 那样替换它。`task` 子代理会丢弃 `AGENTS.md` 与 `APPEND_SYSTEM.md`，但保留 `RULES.md`，因此密码与确认相关的安全规则对委派任务同样有效。

> `AGENTS.md` 的 IDA Pro 小节仍指向 `skill://ida-pro-mcp`。该技能已在提交 `2ad5d80` 中删除，omp 18.14 中没有同名技能。

## agent/config.yml

全局设置层。项目 `.omp/config.yml`、`--config` 覆盖层以及环境变量和 CLI 覆盖都位于它之上；上层的数组会整体替换而不是追加。本文件共设置 69 个键：40 个修改了内置默认值，29 个与默认值相同，用于在上游默认值变化时固定行为。

### 模型角色（`modelRoles`）

| 角色 | 选择器 | 用途 | 原因 |
|---|---|---|---|
| `default` | `gpt-6.1-sol:max` | 主对话模型 | 在 Codex 模型中，GPT-6.1 Sol 的默认上下文窗口最大（50 万 token，其余为 27.2 万），标价处于中档（每百万 token 输入 2 美元、输出 10 美元）；主编码循环使用 `max` 档位 |
| `task` | `gpt-6.1-sol:auto` | `task` 子代理的默认模型 | 与 `default` 同一模型；`:auto` 让 omp 的分类器按回合选择档位，最高到 `max`（见 `providers.autoThinkingMaxEffort`），避免常规子任务承担 `max` 档的延迟 |
| `plan` | `gpt-6-astra:max` | Plan Mode | GPT-6 Astra 是目录中最贵的模型（标价为 GPT-6.1 Sol 的 5 倍），用在推理质量比调用量更重要的地方 |
| `slow` | `gpt-6-astra:max` | 深度推理角色，属于模型切换循环（`smol` → `default` → `slow`） | 同 `plan` |
| `advisor` | `gpt-6-astra:max` | 审阅主回合的 advisor（`advisor.enabled`） | 由另一个更强的模型审阅主模型的工作，得到独立的第二意见 |
| `commit` | `gpt-6.1-sol:xhigh` | 生成提交信息与更新 changelog（`omp commit`） | 强模型，档位比 `max` 低一级以控制延迟 |
| `vision` | `gpt-6.1-sol:xhigh` | 图像分析，例如 `read screenshot.png?q=…` | GPT-6.1 Sol 支持图像输入；`xhigh` 控制延迟 |
| `smol` | `deepseek-flash:max` | 快速廉价角色：prewalk 交接目标、`fixer` agent、增强语音改写、`tiny` 的指向目标 | DeepSeek V4.1 Flash 有 100 万 token 窗口，每百万 token 输入 0.30 美元、输出 1.20 美元，闲时再打五折，所以 `max` 档位依然便宜 |
| `tiny` | `"@smol"` | 会话标题等后台工作 | 显式固定为 `smol` 模型的别名 |
| `judge` | `deepseek-flash:max` | 判定调用（Eval 的 `judge()`、TTSR 的 `question` 规则） | 用廉价模型做是/否判断 |
| `web` | `web/exa` | `web_search` 工具的后端 | 无需密钥即可通过 Exa 的公共 MCP 端点使用（设置 `EXA_API_KEY` 或 `/login exa` 后改走 API）；回退链见 `retry.fallbackChains.web` |

未设置的角色保持内置解析：`memory` → `@tiny`，`widget` → 与 `smol` 相同，`image` → 内置图像优先级列表。`--smol`、`--slow`、`--plan` 参数和 `PI_*_MODEL` 环境变量可在单次运行中覆盖角色。

### 推理与模型路由

| 键 | 值 | 默认值 | 作用 | 原因 |
|---|---|---|---|---|
| `defaultThinkingLevel` | `max` | `high` | 选择器未带 `:level` 后缀时，支持推理的模型所用的档位 | 质量优先；上面每个角色本身已固定档位 |
| `providers.autoThinkingMaxEffort` | `max` | `xhigh` | `:auto` 选择器（此处为 `modelRoles.task`）的档位上限 | 允许分类器在它判定为特殊的回合使用 `max` |
| `modelProviderOrder` | `openai-codex`、`deepseek`、`ltcraft-aws-anthropic`、`ltcraft-kiro-anthropic`、`hajimi` | `[]` | 同一个裸模型 id 存在于多个 provider 时的优先顺序 | 让 `gpt-6.1-sol` 这类裸 id 优先解析到 Codex 网关，其次是 DeepSeek。后三个 provider 已在提交 `5c83bf0` 中从 `models.yml` 删除，目前不匹配任何对象 |
| `retry.fallbackChains.web` | 28 个候选 | `{}` | `web` 角色失败或不可用时按序回退：Perplexity；经三条 Google 路由的 Gemini 2.5 Flash；Claude Haiku 4.5；GPT-5.6 Luna；Grok 4.5；17 个 `web/*` 搜索后端（Z.ai、TinyFish、Jina、Kagi、Tavily、Firecrawl、Brave、Kimi、Parallel、Synthetic、SearXNG、Startpage、DuckDuckGo、Ecosia、Google、Mojeek、public）；经 Codex 的 GPT-5.6/GPT-5.5；经 xAI OAuth 的 Grok；Ollama | 搜索逐级降级而不是直接失败：不可用的候选（例如缺少凭据）会被跳过。omp 加载时会把旧的 `openai-codex/gpt-5.6` 和 `openai-codex/gpt-5.5` 规范化为 `openai-codex/gpt-5.6-sol`，实际生效 27 个候选 |

### 子代理

| 键 | 值 | 默认值 | 作用 | 原因 |
|---|---|---|---|---|
| `task.maxConcurrency` | `32` | 相同 | 同时运行的子代理上限 | 固定默认值；允许大范围并行 |
| `task.maxRecursionDepth` | `2` | 相同 | 子代理可再派生子代理的层数 | 固定默认值 |
| `task.enableEffort` | `true` | `false` | 开放单个任务的 `effort` 参数（`lo`、`med`、`hi`） | 调用方可按子任务调整推理强度 |
| `task.enableLsp` | `true` | `false` | 子代理可以使用 `lsp` 工具 | 在委派的代码工作中，定义、引用和诊断信息值得额外的 token |
| `task.isolation.enabled` | `true` | `false` | 允许 `isolated: true` 的任务在克隆的 worktree 中工作，成功的改动再应用回来 | 多个子代理并行改代码时互不干扰同一份检出 |
| `isolation.backend` | `auto` | 相同 | 克隆后端：`apfs`、`btrfs`、`zfs`、`reflink`、`overlayfs`、`projfs`、`block-clone` 或 `rcopy` | 固定默认值；由 omp 选择可用的最佳后端 |
| `task.prewalk` | `true` | `false` | 通用 `task` 子代理先用解析到的模型规划并开始实现，第一次编辑或写入时交接给 `smol` 角色 | 贵模型负责思考，便宜模型负责落笔 |
| `task.agentAdvisor` | `{task: "on"}` | `{}` | 为通用 `task` 子代理配一个 advisor（`advisor` 角色） | 子代理无人值守地运行，审阅者能发现没人实时看到的错误 |
| `task.softRequestBudget` | `200` | 相同 | 每次子代理运行在收到收尾提醒前可发出的请求数，达到 1.5 倍时强制停止 | 固定默认值 |
| `task.softRequestBudgetNotice` | `true` | 相同 | 发送上述收尾提醒 | 固定默认值 |
| `task.showResolvedModelBadge` | `true` | `false` | 在任务组件中显示每个子代理实际使用的模型 | 角色别名、prewalk 交接与回退会让实际模型不直观 |

### Advisor 与 prewalk

| 键 | 值 | 默认值 | 作用 | 原因 |
|---|---|---|---|---|
| `advisor.enabled` | `true` | `false` | 由第二个模型（`advisor` 角色，GPT-6 Astra）审阅主回合并注入意见 | 对主模型的工作做独立审阅 |
| `advisor.syncBacklog` | `"3"` | `off` | 待处理的审阅达到 3 条及以上时暂停主 agent，最长 30 秒 | 让意见在仍然相关时送达；上限避免长时间卡住 |
| `tier.advisor` | `inherit` | `none` | advisor 跟随主 agent 当前按模型家族设置的服务等级 | 开启 `/fast` 的会话会得到同样快的 advisor |
| `prewalk.auto` | `suggest` | `off` | 对每个新任务询问 `judge` 角色是否值得 prewalk 交接，只报告结论 | 先观察分类器的判断，再考虑让它切换模型（`on`）。auto-prewalk 只使用原生判定后端（TypeSafe Jev、OpenRouter、OpenAI Decisions、Workers AI Clef）；`judge` 目前是聊天模型 `deepseek-flash`，因此不会分类也不会报告任何内容 |

### 上下文与记忆

| 键 | 值 | 默认值 | 作用 | 原因 |
|---|---|---|---|---|
| `compaction.enabled` | `true` | 相同 | 自动维护上下文 | 固定默认值 |
| `compaction.methodOrder` | `[remote, soft]` | `[remote, snapcompact, handoff, shake, soft]` | 先用 provider 原生的服务端压缩，再用模型原地总结 | 只保留两条基于文本的压缩路径；不使用位图归档（`snapcompact`）、交接文档（`handoff`）和 `shake` 删减 |
| `contextPromotion.enabled` | `false` | 相同 | 溢出时切换到模型的 `contextPromotionTarget` | `models.yml` 没有设置 `contextPromotionTarget`；溢出由压缩处理 |
| `memory.backend` | `hindsight` | `off` | 远程 Hindsight 记忆：`recall`、`retain`、`reflect` 工具，以及自动召回与保存 | 跨项目共享的长期记忆，由 `hindsight/` 中的本地容器提供 |
| `hindsight.apiUrl` | `http://127.0.0.1:8888` | `http://localhost:8888` | Hindsight 地址 | 与 `hindsight/compose.yaml` 一致：端口只发布在 IPv4 回环地址上 |
| `hindsight.bankId` | `omp-mnemopi-import` | 未设置（项目名） | 记忆库（bank） | 接收 Mnemopi 导入数据的记忆库（`hindsight/migrate_mnemopi.py`） |
| `hindsight.scoping` | `per-project-tagged` | 相同 | 共用一个记忆库，写入带 `project:<name>` 标签，召回时合并项目记忆与全局记忆 | 固定默认值 |
| `hindsight.autoRecall`、`hindsight.autoRetain` | `true` | 相同 | 首个回合自动召回；每 3 个回合及会话边界自动保存 | 固定默认值 |
| `hindsight.mentalModelsEnabled`、`hindsight.mentalModelAutoSeed` | `true` | 相同 | 把整理好的 mental model 载入提示词；缺失时创建内置集合（`project-conventions`、`project-decisions`、`user-preferences`） | 固定默认值 |
| `mnemopi.scoping` | `per-project-tagged` | `per-project` | 本地 Mnemopi 后端的作用域；`memory.backend` 为 `hindsight` 时不生效 | 若通过 `hindsight/mnemopi-rollback-config.yml` 回退，作用域模型与 Hindsight 保持一致 |

### 工具

| 键 | 值 | 默认值 | 作用 | 原因 |
|---|---|---|---|---|
| `web_search.enabled` | `true` | 相同 | `web_search` 工具 | 固定默认值 |
| `lsp.enabled` | `true` | 相同 | `lsp` 工具 | 固定默认值 |
| `lsp.diagnosticsOnWrite` | `true` | 相同 | 写入代码后返回诊断信息 | 固定默认值 |
| `astGrep.enabled` | `true` | `false` | `ast_grep` 结构化搜索 | 对代码而言，语法感知的搜索比正则更准确 |
| `astEdit.enabled` | `true` | 相同 | `ast_edit` 结构化改写 | 固定默认值 |
| `todo.enabled` | `true` | 相同 | `todo` 工具 | 固定默认值 |
| `todo.eager` | `default` | 相同 | 由模型决定何时建立待办列表 | 固定默认值 |
| `todo.remindersMax` | `5` | `3` | omp 放弃前提醒未完成待办的次数 | 多提醒几次，督促完成多步骤工作 |
| `checkpoint.enabled` | `true` | `false` | `checkpoint` 与 `rewind` 工具 | 先尝试有风险的路径，必要时回滚上下文 |
| `github.enabled` | `true` | `false` | `github` 工具：仓库、issue、PR、diff、搜索、检出、推送、Actions 监视 | 结构化的 GitHub 访问 |
| `generate_image.enabled` | `true` | `false` | `generate_image` 工具；`modelRoles.image` 未设置时使用内置优先级列表 | 按需生成与编辑图像 |
| `security.enabled` | `true` | `false` | 安全扫描工具与只读的 `security://` 命名空间 | 按需做漏洞审查 |
| `speechgen.enabled` | `true` | `false` | `tts` 工具：通过本地 Kokoro 或 xAI Grok Voice 生成语音文件 | 按需输出语音 |
| `speech.enhanced` | `true` | `false` | 朗读输出前，先用 tiny/smol 模型把它改写成口语化文本 | 为朗读功能预先配置；朗读本身（`speech.enabled`）仍关闭 |
| `bash.autoBackground.enabled` | `true` | 相同 | 长时间运行的 Bash 命令转入后台，稍后回报结果 | 固定默认值 |
| `bashInterceptor.enabled` | `true` | `false` | 拦截与专用工具重复的 shell 命令（如 `cat`、`grep`） | 专用工具返回结构化输出，并让文件访问受审批机制约束 |
| `providers.fetch` | `auto` | 相同 | URL 读取后端顺序：native、trafilatura、lynx、parallel、firecrawl、jina | 固定默认值 |
| `providers.openaiWebsockets` | `auto` | 相同 | Codex 的 WebSocket 传输遵循模型默认设置 | 固定默认值 |

### 会话行为与维护

| 键 | 值 | 默认值 | 作用 | 原因 |
|---|---|---|---|---|
| `features.unexpectedStopDetection` | `smart` | `mechanical` | 对没有可见输出的停止自动重试，并用小模型对纯文本停止做分类 | 减少长时间自主运行中的无声停顿 |
| `autoResume` | `false` | 相同 | 启动新会话，而不是恢复上一个会话 | 固定默认值；需要时用 `/resume` 显式恢复 |
| `startup.checkUpdate` | `false` | `true` | 启动时不检查更新 | omp 通过 pacman（`oh-my-pi` 软件包）更新 |
| `marketplace.autoUpdate` | `notify` | 相同 | 启动时检查插件市场更新并提示 | 固定默认值；不会静默安装 |
| `collab.autoStart` | `off` | 相同 | 只有执行 `/collab` 时才共享会话 | 固定默认值；不会隐式公开任何内容 |
| `dev.autoqaConsent` | `granted` | `unset` | 预先同意自动上报工具问题（`xd://report_issue`，发送到 `qa.omp.sh`） | 工具缺陷可直接反馈给上游，不会弹出打断会话的确认 |
| `setupVersion` | `2` | `0` | omp 写入的内部标记，没有界面或说明 | 保持不变 |

### 外观

| 键 | 值 | 默认值 | 作用 | 原因 |
|---|---|---|---|---|
| `theme.dark`、`theme.light` | `titanium`、`light` | 相同 | 深色与浅色终端使用的主题 | 固定默认值 |
| `symbolPreset` | `nerd` | `unicode` | 图标使用 Nerd Font 字形 | 图标更丰富；需要 Nerd Font 或支持 Glyph Protocol 的终端 |
| `statusLine.preset` | `nerd` | `default` | 信息最全、带 Nerd Font 图标的状态栏 | 与 `symbolPreset` 保持一致 |
| `statusLine.separator` | `powerline-thin` | 相同 | 分段分隔符 | 固定默认值 |
| `statusLine.transparent` | `true` | `false` | 状态栏使用终端背景色，并去掉 powerline 端帽 | 与终端主题融为一体 |
| `composer.shape` | `rule` | `band` | “Top Rule Dock”：输入框上方一条横线，状态信息停靠其上 | 布局偏好 |
| `display.shimmer` | `classic` | 相同 | 加载动画 | 固定默认值 |
| `display.showTokenUsage` | `true` | `false` | 在助手消息上显示每回合 token 用量 | 大多数角色以 `max` 运行，需要看到成本 |
| `display.subagentLivePreview` | `true` | `false` | 显示每个固定子代理当前的工具调用 | 跟踪并行任务进度 |
| `hideThinkingBlock` | `false` | 相同 | 保持显示思考块 | 固定默认值 |
| `tui.mouse` | `true` | `false` | 点击即可聚焦子代理卡片与 HUD 行；原生文本选择改为 Shift+拖动 | 用鼠标浏览运行中的子代理 |

## agent/models.yml

`models.yml` 只定义 provider 与模型元数据，角色分配位于 `config.yml`（`modelRoles`）。omp 会把本文件与内置目录合并：内置 provider 的条目覆盖其路由，新的 provider id 则新增自定义 provider。

### 结构

```yaml
providers:
  <provider-id>:              # 内置 id → 覆盖；新 id → 自定义 provider
    baseUrl: https://…        # API 根地址
    api: openai-responses     # 传输协议：anthropic-messages、google-generative-ai、openai-responses 等
    auth: apiKey              # apiKey（默认）、none 或 oauth
    apiKey: SOME_ENV_VAR      # 先当作环境变量名解析，未设置时按字面值使用
    authHeader: true          # 额外发送 Authorization: Bearer <key>
    models:                   # 存在即为完整自定义 provider（需要 baseUrl、apiKey、api）
      - id: model-id          # 必填
        name: Display Name
        kind: image           # 可选；默认为 chat
        reasoning: true
        thinking:
          mode: effort        # effort、budget、google-level、anthropic-adaptive、anthropic-budget-effort
          efforts: [low, high, max]   # 从低到高排列
          defaultLevel: high
          requiresEffort: true        # 只有后端确认接受关闭推理时才设为 false
        supportsTools: true
        input: [text, image]
        contextWindow: 256000
        maxTokens: 128000
        compat: { … }         # 稀疏的传输兼容性覆盖
```

没有 `models` 的 provider 是覆盖项：只改变该 provider 内置模型的路由或认证。自定义模型省略的元数据，会从内置目录中同 id 的参考模型补全（若存在）。

### 本文件中的 provider

| Provider | 类型 | 端点 | API | 凭据 | 模型 |
|---|---|---|---|---|---|
| `anthropic` | 覆盖内置 provider | `cpa.a-minos.org` 网关 | `anthropic-messages` | `AMINOS_API_KEY`，以 Bearer 发送 | 内置 Anthropic 目录 |
| `antigravity` | 自定义 provider | `cpa.a-minos.org/v1beta` | `google-generative-ai` | `AMINOS_API_KEY`，以 Bearer 发送 | `claude-sonnet-5-5-high`、`claude-opus-5-5-high`、`gemini-4-argon-high`、`gemini-3.8-flash-high`、`gemini-3.5-flash-lite`、`gemini-3.1-flash-lite`、`gemini-3-flash`、`gpt-oss-120b-medium`，以及图像模型 `gemini-3.1-flash-image`（`kind: image`） |
| `openai-codex` | 覆盖内置 provider | `cpa.studio26f.org:8443/backend-api` | 内置（`openai-codex-responses`） | `STUDIO26F_API_KEY` | 内置 Codex 目录：`gpt-6.1-sol`、`gpt-6-astra` 等，供 `default`、`task`、`plan`、`slow`、`advisor`、`commit`、`vision` 角色使用 |
| `cpa-studio26f` | 自定义 provider | `cpa.studio26f.org:8443/v1` | `openai-responses` | `STUDIO26F_API_KEY` | 五个模型，见下表 |

`antigravity` 有意使用独立的 provider id。正如文件中的注释所说，这样可以把网关的 CLIProxyAPI 模型 id 与 omp 原生的 `google-antigravity` OAuth 路由区分开。它的条目只写了 `id`，元数据由 omp 从内置参考模型补全。

`cpa-studio26f` 完整声明了每个模型：

| 模型 id | 名称 | 输入 | 上下文窗口 | 最大输出 | 推理档位 | 备注 |
|---|---|---|---|---|---|---|
| `intern-s2` | 书生-S2 | 文本、图像 | 256,000 | 128,000 | low、medium、high | 必须指定档位 |
| `Atria-Dawn-Preview` | Atria Dawn Preview | 文本 | 256,000 | 128,000 | low、medium、high | 必须指定档位 |
| `Agents-A1` | Agents A1 | 文本、图像 | 256,000 | 128,000 | low、medium、high | 必须指定档位 |
| `deepseek-v4-flash-vision` | DeepSeek V4 Flash Vision | 文本、图像 | 1,048,576 | 393,216 | low、high、max（默认 high） | 可关闭推理；`compat`：`statefulResponses: false`（以 `store: false` 重放完整上下文，而不是用 `previous_response_id` 串联）、`supportsReasoningSummary: false`（不发送 `reasoning.summary`）、`supportsImageDetailOriginal: true`（允许 `detail: "original"` 图像） |
| `glm-5.3` | GLM-5.3 | 文本 | 1,000,000 | 131,072 | low、high、max（默认 max） | 必须指定档位 |

多个条目的注释引用了厂商官方文档中的限制，并注明网关行为未经验证。

**为什么这样设计：** Anthropic、Google 系与 Codex 的流量经过两个 API 网关，每个网关对应一把密钥；`smol` 与 `judge` 使用的 DeepSeek 走内置 provider。覆盖内置的 `anthropic` 与 `openai-codex` provider，可以保留 omp 精选目录中的元数据（窗口、价格、推理档位），只改变路由与凭据。目录中没有的模型则写成完整的自定义条目。

## browser-relay/extension/

“OMP Browser Relay” Chrome 扩展（Manifest V3，版本 0.1.0，MIT 许可，作者 Stencil Labs），由 `omp browser-relay install` 生成，该命令的默认安装目录正是 `~/.omp/browser-relay/extension`。它让 omp 的 Eval `browser` API 通过本地 Chrome DevTools Protocol（CDP）中继，操作你日常使用的 Chrome 配置中的标签页，并沿用其中的登录状态与 cookie。

| 文件 | 作用 |
|---|---|
| `manifest.json` | 权限 `debugger`、`tabs`、`tabGroups`、`storage`、`alarms`；后台 service worker；选项页 |
| `background.js` | 中继客户端：WebSocket 连接、RPC 处理、事件转发 |
| `options.html`、`options.js` | 设置中继端口（默认 9224）与可选令牌的页面 |
| `LICENSE`、`THIRD-PARTY-NOTICES.txt` | omp 的 MIT 许可证与汇总的第三方声明 |

工作方式：

1. service worker 连接 `ws://127.0.0.1:<port>/ext`，设置了令牌时附加 `?token=…`。工具栏徽标显示 `on` 或 `off`；点击图标打开选项页。
2. 连接后发送 `hello`，包含持久化的实例 id、浏览器版本、所有标签页以及已附加调试器的标签页。之后每 20 秒发送一次心跳，断线后以 1 秒到 10 秒的退避重连；Chrome 挂起 worker 后，每 30 秒触发的 alarm 会重新建立连接。
3. 执行中继下发的 RPC：附加与分离调试器（`attach`/`detach`，CDP 1.3）、发送 CDP 命令（`send`，含子会话）、`createTab`、`removeTab`、`activateTab`，以及把可控标签页归入或移出带标题的标签组（`group`/`ungroup`）。
4. 把 CDP 事件、调试器分离以及标签页创建、更新、关闭事件转发给中继。连接断开时，解散 omp 的标签组。

使用方法：

```bash
omp browser-relay install        # 重新生成本目录并打印安装步骤
omp browser-relay                # 在 127.0.0.1:9224 上运行中继
omp browser-relay -p 9333 --token s3cret
```

在 `chrome://extensions` 中开启开发者模式，选择“加载已解压的扩展程序”并指向本目录；选项页中的端口和令牌必须与中继的启动参数一致。`config.yml` 保持 `browser.relay` 为 `false`，因此只有调用时传入 `app: { relay: true }` 或设置了 `PI_BROWSER_RELAY=1`，会话才会使用中继；若设为 `browser.relay: true`，中继会成为默认浏览器后端，并在 browser prelude 需要时由 omp 自动启动中继服务。`debugger` 权限让驱动中继的一方完全控制已附加的标签页。扩展只连接 `127.0.0.1`，`--token` 则让中继拒绝没有出示令牌的扩展。

## plugins/

`plugins/` 是 omp 的用户插件根目录。Git 跟踪清单与状态文件；`node_modules/`（已忽略）由 `omp plugin install` 生成。

| 文件 | 作用 |
|---|---|
| `package.json` | 插件依赖，由 omp 内置的 Bun 安装 |
| `bun.lock` | 锁定的提交：`omp-keysmith#e1e092a`、`china-targeted-resume-plugin#da9cc56`（以及 `ajv`、`ajv-formats`） |
| `omp-plugins.lock.json` | 运行时状态：两个插件均已启用，使用默认功能集（`enabledFeatures: null`），没有插件设置 |
| `cache/marketplaces/` | 插件市场目录缓存（已忽略） |

### omp-keysmith（0.1.1）

[`ParticleG/omp-keysmith`](https://github.com/ParticleG/omp-keysmith) 以版本化、带完整性校验的方式部署系统提示词附加内容。每个回合，它的 `before_agent_start` 处理器把选中的提示词作为额外的系统提示词块追加进去，omp 自身的提示词、上下文文件、工具、技能和规则保持不变。它从不修改 `SYSTEM.md`、`APPEND_SYSTEM.md`、`config.yml` 或 `hooks/`。

- 命令：`/keysmith status`、`preview`、`deploy`（压入一层部署并开启注入）、`enable` / `disable`（持久开关）、`uninstall`（别名 `rollback`，弹出最新一层）、`recover`、`doctor [--fix]`。
- 存储：`agent/keysmith/`（本仓库已忽略），包含 `state.json` 以及按 SHA-256 寻址的提示词 blob，采用原子写入与跨进程锁；每次注入前都会校验当前 blob。
- 内置默认提示词是 [Jia-Ethan/codex-keysmith](https://github.com/Jia-Ethan/codex-keysmith) 中的 `BUILTIN_GPT_UNRESTRICTED_MD`。上游文档说明，它会抑制拒绝与警告措辞，并在安全、成人、化学、药理和武器类请求上重新解释授权边界。部署前请先审阅。

### china-targeted-resume-plugin（1.0.1）

[`ParticleG/china-targeted-resume-plugin`](https://github.com/ParticleG/china-targeted-resume-plugin) 把只读的 Markdown 职业知识库转换成针对特定公司与岗位、有证据支撑且适配 ATS 的简历。默认运行在源目录之外新建带时间戳的目录，生成面向招聘方的一页版与面向技术面试官的两页版 PDF，以及需求、证据映射、差距与审计等产物。

- 命令：`/resume-help`、`/resume-init`（默认只用元数据；`--reviewed-semantic` 用于授权读取的源文片段）、`/resume-discover`、`/resume-analyze`、`/resume-generate`、`/resume-audit`、`/resume-status`。
- 每个阶段都由类型化工具把关：`resume_discover_structure`、`resume_read_source_slice`、`resume_validate_source_map`、`resume_validate_role_ir`、`resume_validate_evidence_ir`、`resume_lock_approved_claims`、`resume_compose_variants`、`resume_render_variants`、`resume_inspect_variants`、`resume_write_growth_roadmap`。插件还捆绑了若干 agent 与 `china-targeted-resume` 技能。
- 需要 OMP 17.3.7+ 与 Bun 1.3+；完整生成流程还需要 `uv`、Python 3.14+、Playwright Chromium 和一款 CJK 字体。

仓库根目录的 `marketplaces.json` 登记了 `claude-plugins-official` 插件市场（`anthropics/claude-plugins-official`）。目前没有安装任何市场插件；`marketplace.autoUpdate: notify` 只提示更新。

## 其他文件

| 路径 | 说明 |
|---|---|
| `agent/mcp.json` | MCP 服务器：`blender`（`uvx --python 3.11 blender-mcp`，只用 uv 管理的 Python）与 `boss-agent-cli`（本地 `boss-mcp` 程序，BOSS 直聘求职者角色，超时 120 秒） |
| `agent/mem0.yml` | 把记忆切换到自托管 mem0 服务的覆盖层。omp 18.14 的 `memory.backend` 只接受 `off`、`local`、`hindsight`、`mnemopi` 和 `sharpshooter`，因此该文件对当前版本没有作用 |
| `agent/.clawhub/lock.json` | ClawHub 锁文件，记录来自 `yanranxiaoxi` 的 `easyeda-api` 1.1.3 |
| `hindsight/compose.yaml` | 以 `omp-hindsight` 容器运行 Hindsight 0.9.2（`ghcr.io/vectorize-io/hindsight`）：端口 8888 与 9999 绑定在 `127.0.0.1`，LLM 为经 `cpa.studio26f.org` Responses 端点访问的 `gpt-5.4-mini`（`STUDIO26F_API_KEY`），数据存放在 `omp-hindsight-data` 卷中 |
| `hindsight/migrate_mnemopi.py` | 失败即停、可断点续跑的 Mnemopi → Hindsight 迁移脚本：`prepare`、`import --phase canary/all`、`verify`、`finalize`；测试位于 `test_migrate_mnemopi.py`。运行目录（`migrations/`）与 `.env` 已忽略 |
| `hindsight/mnemopi-rollback-config.yml` | 恢复 `memory.backend: mnemopi` 的覆盖层（`omp --config hindsight/mnemopi-rollback-config.yml`） |
| `openai-analysis.md` | Artificial Analysis Intelligence Index v4.1 中 GPT-5.6 Luna 与 Sol 各档位的数据：单任务成本、单任务耗时、输出速度、端到端延迟 |
| `package.json`、`tsconfig.json`、`bun.lock` | 私有包 `omp-config`，开发依赖为 `@oh-my-pi/pi-coding-agent`（^16.3.11）与 `@types/bun`；严格的 ESNext/bundler TypeScript 设置并启用 `noEmit`，仅用于编辑器支持 |

## 检查生效配置

```bash
omp config path                    # 当前 agent 目录（~/.omp/agent）
omp config list --scope=global     # agent/config.yml 设置的键（解析后）
omp config get <key>               # 单个键的生效值
omp models                         # 应用 models.yml 后各 provider 的聊天模型
omp plugin list && omp plugin doctor
omp browser-relay -v               # 运行中继并记录流量日志
```
