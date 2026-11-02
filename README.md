# omp configuration (`~/.omp`)

**English** | [简体中文](README.zh-CN.md)

Version-controlled user configuration for [oh-my-pi (omp)](https://github.com/can1357/oh-my-pi), a terminal coding agent. The checkout lives at `~/.omp`, omp's default configuration root, so omp reads every file in place; `agent/` is the active agent directory (`omp config path`). The configuration targets **omp 18.14**, installed from the Arch Linux package `oh-my-pi`.

Git tracks only hand-maintained files: settings, model routing, prompt files, a custom subagent, an event hook, a custom tool, skills, the browser-relay extension, the plugin manifest and the self-hosted memory server. `.gitignore` keeps runtime state out: SQLite databases (`agent.db`, `history.db`, `models.db`, …), sessions, blobs, caches, logs, memories, worktrees (`wt/`) and every `node_modules/`.

Defaults quoted in this document come from the omp 18.14 settings schema, read with `omp config list --json` against an empty agent directory.

## Contents

- [Repository layout](#repository-layout)
- [Setting up a new machine](#setting-up-a-new-machine)
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
- [Other files](#other-files)
- [Checking the effective configuration](#checking-the-effective-configuration)

## Repository layout

| Path | Purpose |
|---|---|
| `agent/config.yml` | Global settings: model roles, tools, subagents, memory, UI |
| `agent/models.yml` | Custom providers, gateway routes and model metadata |
| `agent/AGENTS.md` | User-level context: project directory map |
| `agent/APPEND_SYSTEM.md` | Text appended to the system prompt: language and engineering preferences |
| `agent/RULES.md` | Sticky rule sent with every request: password-prompt and confirmation safety |
| `agent/agents/fixer.md` | Custom `fixer` subagent |
| `agent/hooks/post/webhook-notifier.ts` | Extension that posts run-finished and action-required webhooks |
| `agent/rules/lark-cli-tool.md` | Rule steering `lark-*` skills to the `lark_cli` tool |
| `agent/tools/lark-cli.ts` | Custom `lark_cli` tool wrapping the Feishu/Lark CLI |
| `agent/skills/` | Six local skills |
| `agent/feishu-safe.yml` | Opt-in settings overlay for Feishu work |
| `agent/mcp.json` | MCP servers: Blender, BOSS Zhipin |
| `agent/.clawhub/lock.json` | ClawHub install lock for the `easyeda-api` skill |
| `browser-relay/extension/` | Chrome extension used by `omp browser-relay` |
| `plugins/` | Plugin manifest, Bun lockfile and enablement state |
| `marketplaces.json` | Registered plugin marketplace (`anthropics/claude-plugins-official`) |
| `hindsight/` | Docker Compose file for the Hindsight memory server, plus the Mnemopi → Hindsight migration |
| `openai-analysis.md` | Artificial Analysis benchmark notes: cost, latency and score of GPT-5.6 Luna/Sol per effort level |
| `package.json`, `tsconfig.json`, `bun.lock` | TypeScript typings (`@oh-my-pi/pi-coding-agent`, `@types/bun`) for editing the `.ts` files |
| `puppeteer/package.json` | Empty manifest next to Puppeteer's downloaded Chrome (`puppeteer/chrome/`, ignored) |

## Setting up a new machine

1. Install omp 18.14 or later and clone this repository to `~/.omp`.
2. Export the credentials the configuration references:

   | Variable | Used by |
   |---|---|
   | `AMINOS_API_KEY` | `anthropic` and `antigravity` providers in `agent/models.yml` |
   | `STUDIO26F_API_KEY` | `openai-codex` and `cpa-studio26f` providers; the Hindsight LLM in `hindsight/compose.yaml` |
   | `DEEPSEEK_API_KEY` (or `/login`) | Built-in `deepseek` provider behind the `smol`, `tiny` and `judge` roles |
   | `OMP_SESSION_WEBHOOK_URL`, `OMP_SESSION_WEBHOOK_TOKEN` | Optional; enable [webhook-notifier](#agenthookspostwebhook-notifierts) |
   | `EDGEONE_API_KEY` | Optional; the `zhuque` skill's EdgeOne Makers calls |

   When the variable named by a provider's `apiKey` is unset, omp uses the variable name itself as the key, so export the keys before starting omp.
3. Start the memory server: `docker compose -f ~/.omp/hindsight/compose.yaml up -d`. Without it, Hindsight recall and retain fail with `ECONNREFUSED` and sessions continue without memory.
4. Reinstall the plugins; `plugins/node_modules/` is not tracked:

   ```bash
   omp plugin install github:ParticleG/omp-keysmith
   omp plugin install github:ParticleG/china-targeted-resume-plugin
   ```

5. Install the EasyEDA bridge dependency: `cd ~/.omp/agent/skills/easyeda-api && npm install`.
6. Load `~/.omp/browser-relay/extension/` in Chrome as an unpacked extension (see [browser-relay/extension/](#browser-relayextension)).
7. Install the MCP server prerequisites: `uv` (provides `uvx`) for `blender`, and the `boss-mcp` binary at `~/.local/bin/boss-mcp` for `boss-agent-cli`. When an executable is missing, omp logs `MCP tool load failed` for that server and starts without its tools.
8. Optional, for type checking the `.ts` files in an editor: `cd ~/.omp && bun install`.

## agent/agents/fixer.md

`fixer` is a custom subagent. omp discovers `agent/agents/*.md` and offers each agent to the `task` tool next to the bundled ones. `fixer` targets well-specified, bounded work: writing or updating tests, mechanical refactors (renames, pattern replacements) and applying a known change across several files.

| Frontmatter | Value | Effect |
|---|---|---|
| `name` | `fixer` | Agent name used in `task` calls (`"agent": "fixer"`) |
| `description` | "Fast execution specialist …" | Shown in the `task` tool's agent roster; the parent model picks agents by it |
| `model` | `[pi/smol]` | `pi/` is the legacy role-alias prefix (same as `@smol`), so the model resolves through `modelRoles.smol`, currently `deepseek-flash` |
| `thinkingLevel` | `low` | Declared reasoning effort. Because `task.enableEffort` is on, a caller's per-task `effort` (`lo`/`med`/`hi`) takes precedence at launch |
| `spawns` | `[scout]` | Agents `fixer` may start: the bundled read-only `scout`, for codebase lookups during a task |

The Markdown body is the agent's system prompt: full tool access; stay on the assigned target and its directly required callsites or tests; concise output without tool transcripts; narrow lookups before reading ranges; prefer editing existing files; no new Markdown files or mocks unless asked; ask instead of guessing; keep going until the assignment is complete.

**Why:** bounded mechanical work does not need the main model. Routing it to the inexpensive `smol` role (DeepSeek V4.1 Flash) leaves the default `task` agent, which runs on GPT-6.1 Sol, for open-ended work.

## agent/hooks/post/webhook-notifier.ts

An omp extension module that sends a webhook when an agent run finishes or when the session waits for the user. omp loads every `.ts`/`.js` factory under `agent/hooks/pre/` and `agent/hooks/post/` through the extension pipeline; the directory name is only discovery metadata. The factory subscribes to lifecycle events with `pi.on(...)` and acts as a passive observer: it never blocks or alters an event, never executes tools, and never reads message content or credential files. It was written against omp 18.12.6 and sends payload version 2 only.

### Events

| Event | Sent when | `status` |
|---|---|---|
| `omp.run_finished` | An agent run ends without a pending continuation or background work | `completed`, `failed`, `aborted` or `unknown` |
| `omp.action_required` | A tool-approval prompt, a plan review or an `ask` call is still open 150 ms after it appears in an interactive UI | `action_required` |

- Status comes from the last assistant stop reason (`stop` → `completed`, `error` → `failed`, `aborted` → `aborted`). During an automatic retry the result waits for the retry outcome; a failed retry reports `failed`.
- Subagent runs that complete normally are not sent on their own; they appear in the root run's `subagentTimeline`. Failed, aborted or unknown subagent endings are sent individually.
- Session switch, branch or tree navigation, shutdown and a 24-hour expiry close open runs with status `unknown` and a reason in `cycle.reasons`.
- Headless sessions record interactions for the wait timeline but never send `action_required`.

### Configuration

| Variable | Required | Meaning |
|---|---|---|
| `OMP_SESSION_WEBHOOK_URL` (fallback `ONEBOT_WEBHOOK_URL`) | Yes | `http`/`https` endpoint without credentials, query string or fragment |
| `OMP_SESSION_WEBHOOK_TOKEN` (fallback `ONEBOT_WEBHOOK_TOKEN`) | Yes | Bearer token, at most 4096 characters, no line breaks |
| `OMP_SESSION_WEBHOOK_TIMEOUT_MS` (fallback `ONEBOT_WEBHOOK_TIMEOUT_MS`) | No | Per-attempt timeout, integer 100–30000; default 5000 |
| `OMP_SESSION_WEBHOOK_INSTANCE` | No | Label copied into the payload's `instance` field |

Without a valid URL and token the module logs `configuration_missing` or `configuration_invalid` and sends nothing.

### Request and payload

Each notification is a `POST` with a JSON body and the headers `Authorization: Bearer <token>`, `X-OMP-Event: <event>` and `User-Agent: omp-webhook-notifier-v2`; redirects are not followed.

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

- `session.scope` is `root`, `subagent` or `unknown`; `session.agent` carries the agent name when omp provides one.
- `omp.action_required` adds `interaction: { ref, kind }` with `kind` = `approval`, `plan_review` or `ask`.
- Only the root `omp.run_finished` carries the two timelines (abridged above): per-subagent spans with offsets, durations, model and thinking level, and user-wait intervals. Each holds at most 64 entries and 23 KiB / 11 KiB; `partial`, `partialReasons` and `truncated` flag gaps.
- `cycle.partial` and `cycle.reasons` (`missing_start`, `session_changed`, `shutdown`, `expired`, `capacity`, `unpaired_interaction`, `incomplete_metadata`, `clock_changed`) mark incomplete observations.

### Delivery

- Bounded queue of 64 jobs, at most 2 requests in flight.
- Up to 3 attempts on HTTP 429, 5xx, timeouts and network errors. The wait is 250 ms after the first attempt and 1 s after the second, or a 429 `Retry-After` value (capped at 5 s) when longer. Other 4xx responses are not retried.
- Retries resend the same `id`, so receivers should treat `id` as an idempotency key.
- An `action_required` notification is dropped if the user answers before it is sent.
- Outcomes are logged as `OMP webhook` warnings with a `category`. A receiver reports success with `{"code": 0, "message": "ok", "data": {"delivered": true, "retryable": false}}`; the module also recognizes `message: "skipped"` (`replayed` when `data.skip_reason` is `idempotency_replay`, `policy_skipped` when `data.skipped` is `true`), `partial_delivery` and `partial_failure`. Response bodies larger than 8 KiB are not parsed.

### Privacy

- Session and agent identifiers are replaced by HMAC-SHA256 digests keyed with a random per-process salt, so references cannot be correlated across omp processes.
- Text fields are stripped of ANSI and control characters, truncated (96 characters; model ids 128) and dropped when they look like URLs or filesystem paths. Only the basename of the working directory is sent.
- No message text, tool arguments or credentials are included.

## agent/rules/lark-cli-tool.md

A user-level rule file; omp discovers `agent/rules/*.md`. It tells the agent how `lark-*` skills must reach the Feishu/Lark CLI:

- call the `lark_cli` custom tool ([agent/tools/lark-cli.ts](#agenttoolslark-clits)) whenever a `lark-*` skill needs `lark-cli`;
- pass argv tokens in `args`, without the `lark-cli` executable or shell quoting;
- never run `lark-cli` through Bash, Eval, Task or a generated script;
- keep the fixed `omp-user` profile and the user identity;
- expect read commands to be auto-approved, write commands to need approval, and high-risk writes to stay blocked by the CLI's own policy.

The `lark-*` skills themselves live in `~/.agents/skills/`, outside this repository.

The frontmatter sets `alwaysApply: true`, so omp injects the full body into the `<generic-rules>` block of every system prompt, in main sessions and subagents alike (the rule has no `agents` filter). A rule file without `alwaysApply`, a `description` or a trigger condition is never shown to the model.

## agent/skills/

omp discovers each `agent/skills/<name>/SKILL.md`, lists the skill's name and description in the system prompt, and the model reads the full file through `skill://<name>` when a task matches.

| Skill | Purpose | Trigger | Contents and requirements | Source |
|---|---|---|---|---|
| `anti-ai-foolish` | Pre-publish "AI flavor" gate for Chinese WeChat/self-media long-form articles | Only on explicit requests to remove AI flavor (去AI味/降AI率), a final pre-publish check, or a draft flagged by Tencent Zhuque or rejected by WeChat; not for general proofreading, fiction, academic, legal or English text | `scripts/preflight.py`: six hard gates (no colons, dashes or straight quotes; at most 3 concept quotes and 3 questions per 1,000 characters; no section headings) plus a Z-score; `scripts/scanner.py`: 1,108 rules in 13 libraries, each A/B-tested against 52 Zhuque-labelled fragments; `scripts/abtest.py`: re-validation. Workflow: preflight → three human-judgment checks → "seven-knife" block surgery → re-check, then chunked Zhuque test (target ≤ 0.40). Python 3.8+ standard library, offline | v0.1.0 from skillhub.360.com (`forrestneo/anti-ai-foolish`), MIT |
| `codemap` | Hierarchical `codemap.md` documentation for unfamiliar repositories | Explicit requests to map or document a codebase (expensive) | `scripts/codemap.mjs` (`init`, `changes`, `update`) keeps file hashes in `.slim/codemap.json` (migrates legacy `.slim/cartography.json`); one task agent per folder writes that folder's `codemap.md`; a root atlas aggregates them; a `## Repository Map` section is added to the project's `AGENTS.md`. Requires Node.js | — |
| `easyeda-api` | EasyEDA Pro (嘉立创EDA) API reference and live control | "嘉立创EDA，启动！", "EDA，启动！" or EasyEDA, PCB, schematic, footprint keywords | API reference (120 classes, 62 enums, 70 interfaces, 19 type aliases), document source format specs (project, schematic, PCB), extension-development guide; `scripts/bridge-server.mjs` WebSocket bridge on the first free port in 49620–49629 that runs JavaScript inside a connected EasyEDA Pro window. Requires Node.js 18+, `npm install` (`ws`) and the `run-api-gateway` extension in EasyEDA Pro. The bridge executes arbitrary code in the open design: back up projects and stop it after use | v1.1.3 from ClawHub (`yanranxiaoxi/easyeda-api`) |
| `glab` | Correct, non-interactive GitLab CLI usage | Any GitLab operation | Quick reference for issues, MRs and CI; notes and threaded replies; `glab api` placeholders, `-f`/`-F`/`--form`/`--input` semantics; common mistakes (editor-opening flags, `glab ci retry` takes a job ID, always `--push` on `mr create`) | Bundled with the GitLab CLI (`gitlab-org/cli`) |
| `simplify` | Behavior-preserving code simplification | After behavior is understood, for readability and complexity reduction | Five principles (preserve behavior exactly, follow project conventions, clarity over cleverness, balance, scope to what changed), a four-step process and a verification checklist | — |
| `zhuque` | Tencent Zhuque (朱雀) AIGC text detection | Requests to check whether a text is AI-generated or its AI rate (朱雀检测, 检测AI率, AIGC检测, `/zhuque`), or to compare AI rates before and after a revision; detection only, never rewrites | `scripts/detect.py` sends `--text` or `--file` input to the EdgeOne Makers model `@makers/zhuque-text` and prints a Markdown report: overall AI rate (AI + suspected AI), human ratio, confidence, per-segment labels (0 human, 1 AI, 2 suspected AI) and the full text of flagged segments; `--json` returns the raw response, `--is-merge` scores the text as one piece. Python standard library only; the key comes solely from `EDGEONE_API_KEY`; calls draw on the Makers free quota (500,000 tokens per month). Automates the Zhuque check that `anti-ai-foolish` otherwise leaves to a manual paste | Adapted from `ZimingADR/zhuque-skill` (commit `3da7558`), MIT |

The skill list in a session also shows `lark-*`, `ssh`, `humanizer-zh` and `github-review-pr`; omp loads those from `~/.agents/skills/`, which this repository does not track.

## agent/tools/lark-cli.ts

A custom tool factory (`CustomToolFactory`) that omp discovers in `agent/tools/`. It registers the `lark_cli` tool (label "Lark CLI"); with `tools.xdev` on (the default) the model reaches it as the `xd://lark_cli` device.

- **Input:** `{ "args": ["<root-command>", "…"] }`, at least one argv token.
- **Execution:** runs `lark-cli --profile omp-user <args…>` through `pi.exec` in the session's working directory. There is no shell, so no quoting, globbing or command chaining. It returns trimmed stdout and stderr, and fails on cancellation or a non-zero exit code.

**Validation, rejected before execution:**

| Rule | Purpose |
|---|---|
| The first token must be a root command, not an option | Unambiguous parsing |
| No `--profile` or `--profile=…` | The profile is always `omp-user` |
| No `--as bot` or `--as=bot` | Only the user identity is allowed |
| No `api`, `config`, `profile` or `update` root commands, no `auth logout` | Feishu safety profile: no raw API calls, no CLI reconfiguration (risk control included), no profile switching, self-update or logout |

**Approval tier.** Before a call, the tool runs `lark-cli --profile omp-user <args…> --help` and reads the `Risk:` line that lark-cli prints for that command:

| `Risk:` line | omp tier |
|---|---|
| `read` | `read` |
| `write` | `write` |
| `high-risk-write` | `exec` |
| absent | `read` for `auth check`, `auth qrcode`, `auth status`, `doctor`, `schema`, `skills list`, `skills read` and `whoami`; `exec` otherwise |

Arguments that fail validation are classified `exec`. Tiers are cached per argument list for the life of the process, and the probe disables lark-cli's update and skills notifiers.

The tier only matters under a prompting approval mode. `config.yml` leaves `tools.approvalMode` at its default, `yolo`, which runs every tier without asking; the `feishu-safe.yml` overlay below switches to `always-ask`, so only `read` commands run unprompted.

**Why:** a typed argv tool removes shell injection and quoting failures, pins the profile and identity, and lets lark-cli's per-command risk metadata drive omp's approval prompts instead of a hand-maintained allowlist.

### agent/feishu-safe.yml

The companion overlay. omp does not load it automatically; opt in per process with `omp --config ~/.omp/agent/feishu-safe.yml`.

| Setting | Effect |
|---|---|
| `tools.approvalMode: always-ask` | Only `read`-tier calls run without a prompt |
| `tools.approval.bash: prompt`, `tools.approval.eval: prompt` | Shell and code execution always ask |
| `tools.approval.task: deny` | No subagents; they run headless in `yolo` mode and would bypass the prompts |
| `bash.patterns`: `deny` for `*lark-cli*` (and explicitly for `config risk-control off` and `api`) | Every Feishu call must go through `lark_cli` |
| `secrets.enabled: true` | Secret-looking environment values and credential-shaped tokens are redacted before text reaches the model provider |

## AGENTS.md / APPEND_SYSTEM.md / RULES.md

Three user-level prompt files in `agent/`, each loaded differently:

| File | How omp loads it | Reaches `task` subagents | Content |
|---|---|---|---|
| `AGENTS.md` | User-level context file, rendered in the `<repo-rules>` block of the generated project instructions for main sessions and advisors | No | Map of `~/coding` subdirectories by tech stack (WebStorm: TypeScript/Vue/Angular/Bun…, GoLand: Go, CLion: C++23/CMake/vcpkg, PyCharm: Python/FastAPI…, OtherProjects: Tauri/Rust/Terraform/Docker…, DataGrip: SQL, OfficeAddinProjects: Office.js/React, WritersideProjects: docs); project lookup rules (ignore case and separators, allow partial matches, prefer the stack's directory, ask when several match) |
| `APPEND_SYSTEM.md` | Appended verbatim after the default system prompt and project context; the default prompt stays intact | No | Interaction in Simplified Chinese; code, comments and project docs in English; never translate symbols, commands, paths or keys; follow project style and confirm material conflicts with official style; Plan Mode output in Chinese; engineering scope rules: honor explicit decisions, prefer the simplest complete solution, add gates/fallbacks only for concrete needs, remove agent-invented extras, preserve compatibility contracts, validate proportionately, stop when acceptance criteria pass |
| `RULES.md` | Sticky always-apply rule named `RULES`: the full body travels with every request, is re-read at session start and on `/new` or `/clear`, and cannot be made conditional | Yes | Password prompts (`sudo`, `su`, `ssh`) only in a foreground `pty: true` Bash call; never `sudo -S`; never put passwords in commands, environment, pipes, files or logs; stop when no PTY is available; reuse sudo credentials only via `sudo -v` inside the same PTY call; confirm destructive, permission/security, migration, external-interface, architecture and UI/UX decisions that tools cannot settle; prefer the `ask` tool with 2–5 options |

**Why three files:** omp recommends `AGENTS.md` for durable background and `RULES.md` for a few hard requirements that must stay visible in long conversations. `APPEND_SYSTEM.md` layers preferences on top of the default prompt instead of replacing it, as `SYSTEM.md` would. Task subagents drop `AGENTS.md` and `APPEND_SYSTEM.md` but keep `RULES.md`, so the password and confirmation safety rules also bind delegated work.

## agent/config.yml

The global settings layer. Project `.omp/config.yml` files, `--config` overlays and environment or CLI overrides sit above it; arrays in higher layers replace, not append. The file sets 68 keys: 39 change a built-in default and 29 restate one, pinning the behavior against upstream default changes.

### Model roles (`modelRoles`)

| Role | Selector | Used for | Why |
|---|---|---|---|
| `default` | `gpt-6.1-sol:max` | Main conversation model | GPT-6.1 Sol has the largest default window among the Codex models (500K tokens versus 272K) at a mid-range list price ($2 input / $10 output per million tokens); `max` effort for the main coding loop |
| `task` | `gpt-6.1-sol:auto` | Default model of `task` subagents | Same model as `default`; `:auto` lets omp's classifier pick the effort per turn, up to `max` (see `providers.autoThinkingMaxEffort`), so routine subtasks avoid max-effort latency |
| `plan` | `gpt-6-astra:max` | Plan mode | GPT-6 Astra is the premium catalog model (list price 5× GPT-6.1 Sol), spent where reasoning quality outweighs volume |
| `slow` | `gpt-6-astra:max` | Deep-reasoning role in the model-switcher cycle (`smol` → `default` → `slow`) | Same as `plan` |
| `advisor` | `gpt-6-astra:max` | The advisor that reviews main turns (`advisor.enabled`) | A different, stronger model gives an independent second opinion on the main model's work |
| `commit` | `gpt-6.1-sol:xhigh` | Commit messages and changelog updates (`omp commit`) | Strong model, one effort tier below `max` for latency |
| `vision` | `gpt-6.1-sol:xhigh` | Image analysis, e.g. `read screenshot.png?q=…` | GPT-6.1 Sol accepts image input; `xhigh` bounds latency |
| `smol` | `deepseek-flash:max` | Fast, inexpensive role: prewalk hand-off target, the `fixer` agent, enhanced speech rewriting, target of `tiny` | DeepSeek V4.1 Flash has a 1M-token window and costs $0.30 / $1.20 per million tokens with a 50% off-peak discount, so `max` effort stays cheap |
| `tiny` | `"@smol"` | Background work such as session titles | Pins the alias explicitly to the `smol` model |
| `judge` | `deepseek-flash:max` | Judgment calls (Eval `judge()`, TTSR `question` rules) | Inexpensive model for yes/no decisions |
| `web` | `web/exa` | Backend of the `web_search` tool | Works without a key through Exa's public MCP endpoint (`EXA_API_KEY` or `/login exa` switches to the API); fallbacks in `retry.fallbackChains.web` |

Unset roles keep their built-in resolution: `memory` → `@tiny`, `widget` → like `smol`, `image` → the built-in image priority list. `--smol`, `--slow`, `--plan` and the `PI_*_MODEL` environment variables override roles for one run.

### Reasoning and model routing

| Key | Value | Default | Effect | Why |
|---|---|---|---|---|
| `defaultThinkingLevel` | `max` | `high` | Effort for thinking-capable models when a selector has no `:level` suffix | Quality first; every role above pins its own level anyway |
| `providers.autoThinkingMaxEffort` | `max` | `xhigh` | Ceiling for `:auto` selectors (here `modelRoles.task`) | Lets the classifier spend `max` on turns it judges exceptional |
| `modelProviderOrder` | `openai-codex`, `deepseek` | `[]` | Preferred provider when a bare model id exists under several providers | Bare ids such as `gpt-6.1-sol` resolve to the Codex gateway first, then DeepSeek |
| `retry.fallbackChains.web` | 28 candidates | `{}` | Ordered fallbacks when the `web` role fails or is unavailable: Perplexity; Gemini 2.5 Flash via three Google routes; Claude Haiku 4.5; GPT-5.6 Luna; Grok 4.5; 17 `web/*` search backends (Z.ai, TinyFish, Jina, Kagi, Tavily, Firecrawl, Brave, Kimi, Parallel, Synthetic, SearXNG, Startpage, DuckDuckGo, Ecosia, Google, Mojeek, public); GPT-5.6/GPT-5.5 via Codex; Grok via xAI OAuth; Ollama | Search degrades instead of failing: unavailable candidates, such as ones without credentials, are skipped. omp normalizes the legacy `openai-codex/gpt-5.6` and `openai-codex/gpt-5.5` entries to `openai-codex/gpt-5.6-sol` on load, leaving 27 effective candidates |

### Subagents

| Key | Value | Default | Effect | Why |
|---|---|---|---|---|
| `task.maxConcurrency` | `32` | same | Maximum subagents running at once | Pinned default; allows wide fan-out |
| `task.maxRecursionDepth` | `2` | same | How deep subagents may spawn their own subagents | Pinned default |
| `task.enableEffort` | `true` | `false` | Exposes the per-task `effort` parameter (`lo`, `med`, `hi`) | The caller sizes reasoning per subtask |
| `task.enableLsp` | `true` | `false` | Subagents may use the `lsp` tool | Definitions, references and diagnostics in delegated code work are worth the extra tokens |
| `task.isolation.enabled` | `true` | `false` | Allows `isolated: true` tasks, which work in a cloned worktree and apply successful changes back | Parallel editing subagents without trampling one checkout |
| `isolation.backend` | `auto` | same | Clone backend: `apfs`, `btrfs`, `zfs`, `reflink`, `overlayfs`, `projfs`, `block-clone` or `rcopy` | Pinned default; omp picks the best available |
| `task.prewalk` | `true` | `false` | The generic `task` subagent plans and starts on its resolved model, then hands off to the `smol` role at its first edit or write | The expensive model does the thinking, the cheap one types the edits |
| `task.agentAdvisor` | `{task: "on"}` | `{}` | Attaches an advisor (the `advisor` role) to generic `task` subagents | Subagents run unattended; a reviewer catches mistakes nobody watches live |
| `task.softRequestBudget` | `200` | same | Requests per subagent run before a wrap-up notice; forced stop at 1.5× | Pinned default |
| `task.softRequestBudgetNotice` | `true` | same | Sends that wrap-up notice | Pinned default |
| `task.showResolvedModelBadge` | `true` | `false` | Shows each subagent's actual model in the task widget | Role aliases, prewalk hand-offs and fallbacks hide the real model otherwise |

### Advisor

| Key | Value | Default | Effect | Why |
|---|---|---|---|---|
| `advisor.enabled` | `true` | `false` | A second model (`advisor` role, GPT-6 Astra) reviews primary turns and injects notes | Independent review of the main model's work |
| `advisor.syncBacklog` | `"3"` | `off` | Pauses the main agent, for at most 30 s, while 3 or more reviews are pending | Advice arrives while still relevant; the cap bounds the stall |
| `tier.advisor` | `inherit` | `none` | The advisor uses the main agent's live per-family service tier | A `/fast` session gets an equally fast advisor |

### Context and memory

| Key | Value | Default | Effect | Why |
|---|---|---|---|---|
| `compaction.enabled` | `true` | same | Automatic context maintenance | Pinned default |
| `compaction.methodOrder` | `[remote, soft]` | `[remote, snapcompact, handoff, shake, soft]` | Provider-native server compaction first, then an in-place model summary | Keeps compaction to two text-based paths; skips bitmap history archives (`snapcompact`), handoff documents and `shake` elision |
| `contextPromotion.enabled` | `false` | same | Would switch to a model's `contextPromotionTarget` on overflow | `models.yml` sets no `contextPromotionTarget`; compaction handles overflow |
| `memory.backend` | `hindsight` | `off` | Remote Hindsight memory: `recall`, `retain` and `reflect` tools plus automatic recall and retain | Long-term memory shared across projects, served by the local container in `hindsight/` |
| `hindsight.apiUrl` | `http://127.0.0.1:8888` | `http://localhost:8888` | Hindsight endpoint | Matches `hindsight/compose.yaml`, which publishes the port on IPv4 loopback only |
| `hindsight.bankId` | `omp-mnemopi-import` | unset (project name) | Memory bank | The bank that received the Mnemopi import (`hindsight/migrate_mnemopi.py`) |
| `hindsight.scoping` | `per-project-tagged` | same | One shared bank; writes carry a `project:<name>` tag; recall merges project and global memories | Pinned default |
| `hindsight.autoRecall`, `hindsight.autoRetain` | `true` | same | Recall on the first turn; retain every 3 turns and at session boundaries | Pinned defaults |
| `hindsight.mentalModelsEnabled`, `hindsight.mentalModelAutoSeed` | `true` | same | Load curated mental models into the prompt; create the built-in set (`project-conventions`, `project-decisions`, `user-preferences`) when missing | Pinned defaults |
| `mnemopi.scoping` | `per-project-tagged` | `per-project` | Scoping of the local Mnemopi backend, inactive while `memory.backend` is `hindsight` | A rollback through `hindsight/mnemopi-rollback-config.yml` keeps the same scoping model as Hindsight |

### Tools

| Key | Value | Default | Effect | Why |
|---|---|---|---|---|
| `web_search.enabled` | `true` | same | `web_search` tool | Pinned default |
| `lsp.enabled` | `true` | same | `lsp` tool | Pinned default |
| `lsp.diagnosticsOnWrite` | `true` | same | Returns diagnostics after code writes | Pinned default |
| `astGrep.enabled` | `true` | `false` | `ast_grep` structural search | Syntax-aware search is more precise than regex for code |
| `astEdit.enabled` | `true` | same | `ast_edit` structural rewrites | Pinned default |
| `todo.enabled` | `true` | same | `todo` tool | Pinned default |
| `todo.eager` | `default` | same | The model decides when to create a todo list | Pinned default |
| `todo.remindersMax` | `5` | `3` | Reminders about unfinished todos before omp gives up | More nudges to finish multi-step work |
| `checkpoint.enabled` | `true` | `false` | `checkpoint` and `rewind` tools | Try a risky path, then roll the context back |
| `github.enabled` | `true` | `false` | `github` tool: repositories, issues, pull requests, diffs, search, checkout, push, Actions watch | Structured GitHub access |
| `generate_image.enabled` | `true` | `false` | `generate_image` tool; with `modelRoles.image` unset it uses the built-in priority list | Image generation and editing on demand |
| `security.enabled` | `true` | `false` | Security scan tool and the read-only `security://` namespace | On-demand vulnerability review |
| `speechgen.enabled` | `true` | `false` | `tts` tool: speech files via on-device Kokoro or xAI Grok Voice | Spoken output on request |
| `speech.enhanced` | `true` | `false` | Before output is read aloud, the tiny/smol model rewrites it into spoken prose | Preset for read-aloud, which itself stays off (`speech.enabled`) |
| `bash.autoBackground.enabled` | `true` | same | Long-running Bash commands move to the background and report later | Pinned default |
| `bashInterceptor.enabled` | `true` | `false` | Blocks shell commands that duplicate dedicated tools (such as `cat` or `grep`) | Dedicated tools return structured output and keep file access approval-aware |
| `providers.fetch` | `auto` | same | URL reader order: native, trafilatura, lynx, parallel, firecrawl, jina | Pinned default |
| `providers.openaiWebsockets` | `auto` | same | Codex WebSocket transport follows the model's default | Pinned default |

### Session behavior and maintenance

| Key | Value | Default | Effect | Why |
|---|---|---|---|---|
| `features.unexpectedStopDetection` | `smart` | `mechanical` | Retries stops without a visible message, and a small model also classifies text-only stops | Fewer silent stalls in long autonomous runs |
| `autoResume` | `false` | same | Start a new session instead of resuming the last one | Pinned default; resume explicitly with `/resume` |
| `startup.checkUpdate` | `false` | `true` | No update check at startup | omp is updated through pacman (`oh-my-pi` package) |
| `marketplace.autoUpdate` | `notify` | same | Check marketplace plugins at startup and notify about updates | Pinned default; nothing installs silently |
| `collab.autoStart` | `off` | same | A session is shared only when `/collab` runs | Pinned default; nothing is published implicitly |
| `dev.autoqaConsent` | `granted` | `unset` | Pre-answers the consent prompt for automated tool-issue reports (`xd://report_issue`, sent to `qa.omp.sh`) | Tool bugs reach upstream without an interrupting prompt |
| `setupVersion` | `2` | `0` | Internal marker written by omp; no UI or description | Leave unchanged |

### Appearance

| Key | Value | Default | Effect | Why |
|---|---|---|---|---|
| `theme.dark`, `theme.light` | `titanium`, `light` | same | Themes for dark and light terminals | Pinned defaults |
| `symbolPreset` | `nerd` | `unicode` | Nerd Font glyphs for icons | Richer icons; needs a Nerd Font or a Glyph Protocol terminal |
| `statusLine.preset` | `nerd` | `default` | Status line with the most segments and Nerd Font icons | Matches `symbolPreset` |
| `statusLine.separator` | `powerline-thin` | same | Segment separator | Pinned default |
| `statusLine.transparent` | `true` | `false` | Status line uses the terminal background; powerline end caps are dropped | Blends with the terminal theme |
| `composer.shape` | `rule` | `band` | "Top Rule Dock": a single rule above the input with the status docked on it | Layout preference |
| `display.shimmer` | `classic` | same | Loading animation | Pinned default |
| `display.showTokenUsage` | `true` | `false` | Per-turn token usage on assistant messages | Cost visibility when most roles run at `max` |
| `display.subagentLivePreview` | `true` | `false` | Shows each pinned subagent's current tool call | Follow fan-out progress |
| `hideThinkingBlock` | `false` | same | Thinking blocks stay visible | Pinned default |
| `tui.mouse` | `true` | `false` | Click to focus subagent cards and HUD rows; native text selection moves to Shift+drag | Mouse navigation of live subagents |

## agent/models.yml

`models.yml` defines providers and model metadata only. Role assignments live in `config.yml` (`modelRoles`). omp merges this file with its bundled catalog: entries for built-in providers override routing, and new provider ids add custom providers.

### Structure

```yaml
providers:
  <provider-id>:              # built-in id → override; new id → custom provider
    baseUrl: https://…        # API root
    api: openai-responses     # transport: anthropic-messages, google-generative-ai, openai-responses, …
    auth: apiKey              # apiKey (default), none or oauth
    apiKey: SOME_ENV_VAR      # read as an environment variable name first, else used literally
    authHeader: true          # also send Authorization: Bearer <key>
    models:                   # present → full custom provider (baseUrl, apiKey, api required)
      - id: model-id          # required
        name: Display Name
        kind: image           # optional; defaults to chat
        reasoning: true
        thinking:
          mode: effort        # effort, budget, google-level, anthropic-adaptive, anthropic-budget-effort
          efforts: [low, high, max]   # list lowest first
          defaultLevel: high
          requiresEffort: true        # false only if the backend accepts reasoning "off"
        supportsTools: true
        input: [text, image]
        contextWindow: 256000
        maxTokens: 128000
        compat: { … }         # sparse transport-compatibility overrides
```

A provider without `models` is an override: it reroutes or re-authenticates the built-in models of that provider. Omitted metadata on a custom model is filled from a bundled reference model with the same id, when one exists.

### Providers in this file

| Provider | Kind | Endpoint | API | Credential | Models |
|---|---|---|---|---|---|
| `anthropic` | Override of the built-in provider | `cpa.a-minos.org` gateway | `anthropic-messages` | `AMINOS_API_KEY`, sent as Bearer | Built-in Anthropic catalog |
| `antigravity` | Custom provider | `cpa.a-minos.org/v1beta` | `google-generative-ai` | `AMINOS_API_KEY`, sent as Bearer | `claude-sonnet-5-5-high`, `claude-opus-5-5-high`, `gemini-4-argon-high`, `gemini-3.8-flash-high`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-3-flash`, `gpt-oss-120b-medium`, and the image model `gemini-3.1-flash-image` (`kind: image`) |
| `openai-codex` | Override of the built-in provider | `cpa.studio26f.org:8443/backend-api` | Built-in (`openai-codex-responses`) | `STUDIO26F_API_KEY` | Built-in Codex catalog: `gpt-6.1-sol`, `gpt-6-astra` and others, used by the `default`, `task`, `plan`, `slow`, `advisor`, `commit` and `vision` roles |
| `cpa-studio26f` | Custom provider | `cpa.studio26f.org:8443/v1` | `openai-responses` | `STUDIO26F_API_KEY` | Five models, see below |

`antigravity` deliberately uses its own provider id. As the file's comment says, it keeps the gateway's CLIProxyAPI model ids separate from omp's native `google-antigravity` OAuth routes. Its entries list only `id`, so omp fills their metadata from bundled references.

`cpa-studio26f` declares every model in full:

| Model id | Name | Input | Context window | Max output | Efforts | Notes |
|---|---|---|---|---|---|---|
| `intern-s2` | 书生-S2 | text, image | 256,000 | 128,000 | low, medium, high | Effort required |
| `Atria-Dawn-Preview` | Atria Dawn Preview | text | 256,000 | 128,000 | low, medium, high | Effort required |
| `Agents-A1` | Agents A1 | text, image | 256,000 | 128,000 | low, medium, high | Effort required |
| `deepseek-v4-flash-vision` | DeepSeek V4 Flash Vision | text, image | 1,048,576 | 393,216 | low, high, max (default high) | Reasoning may be turned off; `compat`: `statefulResponses: false` (replay full context with `store: false` instead of `previous_response_id` chaining), `supportsReasoningSummary: false` (no `reasoning.summary`), `supportsImageDetailOriginal: true` (allow `detail: "original"` images) |
| `glm-5.3` | GLM-5.3 | text | 1,000,000 | 131,072 | low, high, max (default max) | Effort required |

Comments on several entries cite the vendors' official documentation for these limits and note that the gateway's behavior is unverified.

**Why this layout:** Anthropic, Google-family and Codex traffic goes through two API gateways, one per key; DeepSeek, used by `smol` and `judge`, is reached through its built-in provider. Overriding the built-in `anthropic` and `openai-codex` providers keeps omp's curated catalog metadata (windows, pricing, effort ladders) while changing only the route and credential. Models the catalog does not know get full custom entries.

## browser-relay/extension/

The "OMP Browser Relay" Chrome extension (Manifest V3, version 0.1.0, MIT, by Stencil Labs), written by `omp browser-relay install`, whose default install directory is exactly `~/.omp/browser-relay/extension`. It lets omp's Eval `browser` API drive tabs in your everyday Chrome profile, with its logins and cookies, through a local Chrome DevTools Protocol (CDP) relay.

| File | Role |
|---|---|
| `manifest.json` | Permissions `debugger`, `tabs`, `tabGroups`, `storage`, `alarms`; background service worker; options page |
| `background.js` | Relay client: WebSocket connection, RPC handler, event forwarding |
| `options.html`, `options.js` | Settings page for the relay port (default 9224) and an optional token |
| `LICENSE`, `THIRD-PARTY-NOTICES.txt` | omp's MIT license and aggregated third-party notices |

How it works:

1. The service worker connects to `ws://127.0.0.1:<port>/ext`, appending `?token=…` when a token is set. The toolbar badge shows `on` or `off`; clicking the icon opens the options page.
2. On connect it sends `hello` with a persistent instance id, the browser version, every tab and the tabs that already have a debugger attached. It pings every 20 s, reconnects with backoff from 1 s to 10 s, and a 30-second alarm restarts the connection after Chrome suspends the worker.
3. It executes relay RPCs: `attach` and `detach` the debugger (CDP 1.3), `send` CDP commands (including to child sessions), `createTab`, `removeTab`, `activateTab`, and `group`/`ungroup` controllable tabs into a titled tab group.
4. It forwards CDP events, debugger detaches and tab created/updated/removed events to the relay. When the connection drops, it ungroups omp's tab group.

Usage:

```bash
omp browser-relay install        # (re)writes this directory and prints setup steps
omp browser-relay                # serves the relay on 127.0.0.1:9224
omp browser-relay -p 9333 --token s3cret
```

Load the directory via `chrome://extensions` → Developer mode → Load unpacked; the port and token in the options page must match the relay's flags. `config.yml` leaves `browser.relay` at `false`, so a session uses the relay only when a call passes `app: { relay: true }` or `PI_BROWSER_RELAY=1` is set; with `browser.relay: true`, the relay becomes the default browser backend and omp starts the relay server when the browser prelude needs it. The `debugger` permission gives whatever drives the relay full control of attached tabs. The extension connects only to `127.0.0.1`, and `--token` makes the relay reject extensions that do not present the token.

## plugins/

`plugins/` is omp's user plugin root. Git tracks the manifest and state files; `omp plugin install` materializes `node_modules/` (ignored).

| File | Role |
|---|---|
| `package.json` | Plugin dependencies, installed by omp's embedded Bun |
| `bun.lock` | Pinned commits: `omp-keysmith#e1e092a`, `china-targeted-resume-plugin#da9cc56` (plus `ajv` and `ajv-formats`) |
| `omp-plugins.lock.json` | Runtime state: both plugins enabled, default feature set (`enabledFeatures: null`), no plugin settings |
| `cache/marketplaces/` | Marketplace catalog cache (ignored) |

### omp-keysmith (0.1.1)

[`ParticleG/omp-keysmith`](https://github.com/ParticleG/omp-keysmith) deploys versioned, integrity-checked system-prompt additions. On every turn its `before_agent_start` handler appends the selected prompt as an extra system-prompt block, leaving omp's own prompt, context files, tools, skills and rules intact. It never edits `SYSTEM.md`, `APPEND_SYSTEM.md`, `config.yml` or `hooks/`.

- Commands: `/keysmith status`, `preview`, `deploy` (pushes a layer and enables injection), `enable` / `disable` (persistent switch), `uninstall` (alias `rollback`; pops the newest layer), `recover`, `doctor [--fix]`.
- Storage: `agent/keysmith/` (ignored here), holding `state.json` plus prompt blobs addressed by SHA-256, with atomic writes and a cross-process lock; the active blob is verified before each injection.
- The bundled default prompt is `BUILTIN_GPT_UNRESTRICTED_MD` from [Jia-Ethan/codex-keysmith](https://github.com/Jia-Ethan/codex-keysmith). Upstream documents that it suppresses refusal and warning framing and reinterprets authorization boundaries across security, adult, chemistry, pharmacology and weapons requests. Review it before deploying.

### china-targeted-resume-plugin (1.0.1)

[`ParticleG/china-targeted-resume-plugin`](https://github.com/ParticleG/china-targeted-resume-plugin) turns a read-only Markdown career knowledge base into evidence-grounded, ATS-friendly resumes for a specific company and role. The default run produces a recruiter one-page and a technical two-page PDF, together with requirement, evidence-map, gap and audit artifacts, in a new timestamped directory outside the source tree.

- Commands: `/resume-help`, `/resume-init` (metadata-only by default; `--reviewed-semantic` for authorized source slices), `/resume-discover`, `/resume-analyze`, `/resume-generate`, `/resume-audit`, `/resume-status`.
- Typed tools gate each stage: `resume_discover_structure`, `resume_read_source_slice`, `resume_validate_source_map`, `resume_validate_role_ir`, `resume_validate_evidence_ir`, `resume_lock_approved_claims`, `resume_compose_variants`, `resume_render_variants`, `resume_inspect_variants`, `resume_write_growth_roadmap`. It also bundles agents and the `china-targeted-resume` skill.
- Requires OMP 17.3.7+ and Bun 1.3+; full generation also needs `uv`, Python 3.14+, Playwright Chromium and a CJK font.

`marketplaces.json` at the repository root registers the `claude-plugins-official` marketplace (`anthropics/claude-plugins-official`). No marketplace plugin is installed; `marketplace.autoUpdate: notify` only reports updates.

## Other files

| Path | Description |
|---|---|
| `agent/mcp.json` | MCP servers: `blender` (`uvx --python 3.11 blender-mcp`, uv-managed Python only; needs `uv`) and `boss-agent-cli` (local `~/.local/bin/boss-mcp` binary for BOSS Zhipin in the candidate role, 120 s timeout). omp skips a server whose executable is missing |
| `agent/.clawhub/lock.json` | ClawHub lock recording `easyeda-api` 1.1.3 from `yanranxiaoxi` |
| `hindsight/compose.yaml` | Hindsight 0.9.2 (`ghcr.io/vectorize-io/hindsight`) as container `omp-hindsight`: ports 8888 and 9999 on `127.0.0.1`, LLM `gpt-6-luna` via the gateway's Responses endpoint `cpa.studio26f.org:8443/v1` (`STUDIO26F_API_KEY`) for fact extraction and mental-model refresh, data in the `omp-hindsight-data` volume; restarts with the Docker daemon (`restart: unless-stopped`) |
| `hindsight/migrate_mnemopi.py` | Fail-closed, resumable Mnemopi → Hindsight migration: `prepare`, `import --phase canary/all`, `verify`, `finalize`; tested by `test_migrate_mnemopi.py`. Run directories (`migrations/`) and `.env` are ignored |
| `hindsight/mnemopi-rollback-config.yml` | Overlay restoring `memory.backend: mnemopi` (`omp --config hindsight/mnemopi-rollback-config.yml`) |
| `openai-analysis.md` | Artificial Analysis Intelligence Index v4.1 data for GPT-5.6 Luna and Sol per effort level: cost per task, time per task, output speed, end-to-end latency |
| `package.json`, `tsconfig.json`, `bun.lock` | Private `omp-config` package with dev dependencies `@oh-my-pi/pi-coding-agent` (^16.3.11) and `@types/bun`; strict ESNext/bundler TypeScript settings with `noEmit`, for editor support only |

## Checking the effective configuration

```bash
omp config path                    # active agent directory (~/.omp/agent)
omp config list --scope=global     # keys set by agent/config.yml, as parsed
omp config get <key>               # effective value of one key
omp models                         # chat models per provider after models.yml is applied
omp plugin list && omp plugin doctor
omp browser-relay -v               # serve the relay with traffic logging
```
