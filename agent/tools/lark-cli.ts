import type { CustomToolFactory } from "@oh-my-pi/pi-coding-agent";

const PROFILE = "omp-user";
const COMMAND = "lark-cli";
const FORBIDDEN_ROOT_COMMANDS: Record<string, true> = {
  api: true,
  config: true,
  profile: true,
  update: true,
};
const READ_ONLY_FALLBACKS: Record<string, true> = {
  "auth check": true,
  "auth qrcode": true,
  "auth status": true,
  doctor: true,
  schema: true,
  "skills list": true,
  "skills read": true,
  whoami: true,
};

type ApprovalTier = "read" | "write" | "exec";
type ToolArgs = { args: string[] };

function parseArgs(value: unknown): string[] {
  if (typeof value !== "object" || value === null || !("args" in value)) {
    return [];
  }

  const args = value.args;
  return Array.isArray(args) && args.every((arg) => typeof arg === "string") ? args : [];
}


function validateArgs(args: string[]): string | undefined {
  if (args.length === 0) {
    return "At least one lark-cli argument is required";
  }
  const rootCommand = args[0].toLowerCase();
  if (rootCommand.startsWith("-")) {
    return "The first argument must be a lark-cli root command, not an option";
  }


  if (args.some((arg) => arg === "--profile" || arg.startsWith("--profile="))) {
    return `Profile overrides are forbidden; this tool always uses ${PROFILE}`;
  }

  for (let index = 0; index < args.length; index += 1) {
    const arg = args[index];
    if (arg === "--as" && args[index + 1]?.toLowerCase() === "bot") {
      return "Bot identity is forbidden; this tool always uses the user identity";
    }
    if (arg.toLowerCase() === "--as=bot") {
      return "Bot identity is forbidden; this tool always uses the user identity";
    }
  }

  if (FORBIDDEN_ROOT_COMMANDS[rootCommand] === true) {
    return `The ${rootCommand} command is forbidden by the Feishu safety profile`;
  }
  if (rootCommand === "auth" && args[1]?.toLowerCase() === "logout") {
    return "The auth logout command is forbidden by the Feishu safety profile";
  }

  return undefined;
}

const factory: CustomToolFactory = (pi) => {
  const riskCache = new Map<string, ApprovalTier>();

  function classifyRisk(args: string[]): ApprovalTier {
    const cacheKey = JSON.stringify(args);
    const cached = riskCache.get(cacheKey);
    if (cached !== undefined) {
      return cached;
    }

    if (validateArgs(args) !== undefined) {
      riskCache.set(cacheKey, "exec");
      return "exec";
    }

    const probe = Bun.spawnSync([COMMAND, "--profile", PROFILE, ...args, "--help"], {
      cwd: pi.cwd,
      env: {
        ...process.env,
        LARKSUITE_CLI_NO_SKILLS_NOTIFIER: "1",
        LARKSUITE_CLI_NO_UPDATE_NOTIFIER: "1",
        LARKSUITE_CLI_PROFILE: PROFILE,
      },
      stderr: "pipe",
      stdout: "pipe",
    });
    const help = `${probe.stdout.toString()}\n${probe.stderr.toString()}`;
    const risk = help.match(/^Risk:\s*(read|write|high-risk-write)\s*$/m)?.[1];

    let tier: ApprovalTier;
    if (risk === "read") {
      tier = "read";
    } else if (risk === "write") {
      tier = "write";
    } else if (risk === "high-risk-write") {
      tier = "exec";
    } else {
      const key = args
        .filter((arg) => !arg.startsWith("-"))
        .slice(0, 2)
        .join(" ");
      tier = READ_ONLY_FALLBACKS[key] === true || READ_ONLY_FALLBACKS[args[0]] === true ? "read" : "exec";
    }

    riskCache.set(cacheKey, tier);
    return tier;
  }

  return {
    name: "lark_cli",
    label: "Lark CLI",
    description:
      "Runs one typed lark-cli command under the fixed omp-user profile without a shell. Pass argv tokens only, excluding the lark-cli executable. Read commands are auto-approved; writes require approval; high-risk writes remain blocked by lark-cli policy.",
    parameters: pi.zod.object({
      args: pi.zod.array(pi.zod.string()).min(1),
    }),
    approval: (value: unknown) => classifyRisk(parseArgs(value)),
    formatApprovalDetails: (value: unknown) => {
      const args = parseArgs(value);
      return [
        `Command: ${COMMAND} --profile ${PROFILE} ${args.map((arg) => JSON.stringify(arg)).join(" ")}`,
        `Risk tier: ${classifyRisk(args)}`,
      ];
    },
    async execute(_toolCallId, params: ToolArgs, _onUpdate, _ctx, signal) {
      const validationError = validateArgs(params.args);
      if (validationError !== undefined) {
        throw new Error(validationError);
      }

      const result = await pi.exec(COMMAND, ["--profile", PROFILE, ...params.args], {
        cwd: pi.cwd,
        signal,
      });
      const output = [result.stdout, result.stderr]
        .map((text) => text.trim())
        .filter(Boolean)
        .join("\n");

      if (result.killed) {
        throw new Error("lark-cli was cancelled");
      }
      if (result.code !== 0) {
        throw new Error(output || `lark-cli exited with code ${result.code}`);
      }

      return {
        content: [{ type: "text", text: output || "lark-cli completed without output" }],
        details: {
          args: params.args,
          exitCode: result.code,
          risk: classifyRisk(params.args),
        },
      };
    },
  };
};

export default factory;
