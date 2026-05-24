/**
 * Preset switcher extension for omp
 * Migrated from oh-my-opencode-slim's preset system.
 *
 * Usage: /preset <name>
 * Available presets: quick-search, fast-coding, balanced-general, deep-research, ui-polish, critical-review
 */

const PRESETS = {
	"quick-search": {
		default: "hajimi/deepseek-v4-pro",
		slow: "scihub-antigravity/claude-sonnet-4-6",
		smol: "hajimi/deepseek-v4-pro",
		plan: "hajimi/deepseek-v4-pro",
		designer: "scihub-antigravity/claude-sonnet-4-6",
		task: "hajimi/deepseek-v4-pro",
	},
	"fast-coding": {
		default: "scihub-antigravity/claude-sonnet-4-6",
		slow: "scihub-antigravity/claude-sonnet-4-6",
		smol: "hajimi/deepseek-v4-pro",
		plan: "scihub-antigravity/claude-sonnet-4-6",
		designer: "scihub-antigravity/claude-sonnet-4-6",
		task: "hajimi/deepseek-v4-pro",
	},
	"balanced-general": {
		default: "scihub-antigravity/claude-opus-4-6",
		slow: "scihub-antigravity/claude-opus-4-6",
		smol: "scihub-antigravity/claude-sonnet-4-6",
		plan: "scihub-antigravity/claude-opus-4-6",
		designer: "scihub-antigravity/claude-sonnet-4-6",
		task: "scihub-antigravity/claude-sonnet-4-6",
	},
	"deep-research": {
		default: "scihub-antigravity/claude-opus-4-6",
		slow: "scihub-antigravity/claude-opus-4-6",
		smol: "scihub-antigravity/claude-sonnet-4-6",
		plan: "scihub-antigravity/claude-opus-4-6",
		designer: "scihub-antigravity/claude-sonnet-4-6",
		task: "scihub-antigravity/claude-opus-4-6",
	},
	"ui-polish": {
		default: "scihub-antigravity/claude-opus-4-6",
		slow: "scihub-antigravity/claude-opus-4-6",
		smol: "scihub-antigravity/claude-sonnet-4-6",
		plan: "scihub-antigravity/claude-opus-4-6",
		designer: "scihub-antigravity/claude-sonnet-4-6",
		task: "scihub-antigravity/claude-sonnet-4-6",
	},
	"critical-review": {
		default: "scihub-antigravity/claude-opus-4-6",
		slow: "scihub-antigravity/claude-opus-4-6",
		smol: "scihub-antigravity/claude-sonnet-4-6",
		plan: "scihub-antigravity/claude-opus-4-6",
		designer: "scihub-antigravity/claude-sonnet-4-6",
		task: "scihub-antigravity/claude-sonnet-4-6",
	},
};

const THINKING_LEVELS = {
	"quick-search": "medium",
	"fast-coding": "medium",
	"balanced-general": "high",
	"deep-research": "xhigh",
	"ui-polish": "high",
	"critical-review": "xhigh",
};

export default function presetSwitcher(pi) {
	pi.setLabel("Preset Switcher");

	pi.registerCommand("preset", {
		description: "Switch model preset (quick-search, fast-coding, balanced-general, deep-research, ui-polish, critical-review)",
		getArgumentCompletions(prefix) {
			return Object.keys(PRESETS)
				.filter((name) => name.startsWith(prefix))
				.map((name) => ({ label: name, value: name }));
		},
		handler: async (args, ctx) => {
			const name = args.trim();
			const { settings } = pi.pi;

			if (!name) {
				const current = settings.getModelRoles();
				const active = Object.entries(PRESETS).find(
					([, roles]) => JSON.stringify(roles) === JSON.stringify(current)
				);
				ctx.ui.notify(
					`Active: ${active?.[0] ?? "custom"}\nAvailable: ${Object.keys(PRESETS).join(", ")}`,
					"info"
				);
				return;
			}

			const preset = PRESETS[name];
			if (!preset) {
				ctx.ui.notify(
					`Unknown preset "${name}".\nAvailable: ${Object.keys(PRESETS).join(", ")}`,
					"error"
				);
				return;
			}

			// Apply model roles
			settings.overrideModelRoles(preset);

			// Apply thinking level
			const level = THINKING_LEVELS[name] ?? "high";
			pi.setThinkingLevel(level);

			// Switch the main model to the preset's default
			pi.setModel(preset.default);

			ctx.ui.notify(`Preset: ${name} | Thinking: ${level}`, "info");
		},
	});
}
