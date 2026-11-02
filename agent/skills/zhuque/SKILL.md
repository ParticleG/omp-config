---
name: zhuque
description: >
  Run Tencent Zhuque (朱雀) AIGC text detection through the EdgeOne Makers
  built-in model @makers/zhuque-text and report human / AI / suspected-AI
  ratios with per-segment labels. Use when the user asks whether a text is
  AI-generated or what its AI rate is (朱雀检测, 检测AI率, AI率, AIGC检测,
  /zhuque), or wants to compare AI rates before and after a revision.
  Detection only; it never rewrites text.
metadata:
  source-project: ZimingADR/zhuque-skill
  source-commit: 3da7558ef1219d143cfac44336c4c7d6f53031ad
---

# Zhuque AIGC Text Detection

`scripts/detect.py` sends text to Tencent Zhuque through the EdgeOne Makers model gateway (`https://ai-gateway.edgeone.link/v1/providers/zhuque-text/classify`) and prints a Markdown report: overall AI rate, human ratio, confidence, a per-segment table, and the full text of every AI or suspected-AI segment. It uses only the Python standard library.

## When to use

1. Check a text or file for its overall AI rate and confidence.
2. Compare AI rates before and after a manual revision.
3. Locate the paragraphs labeled AI (label 1) or suspected AI (label 2).

## API key

The script reads the key from the `EDGEONE_API_KEY` environment variable only.

- The key is created on the international site: EdgeOne console → Makers → Models → API Key (https://console.tencentcloud.com/edgeone/makers?tab=models&subTab=apikey).
- The user exports it in their shell profile before starting the agent: `export EDGEONE_API_KEY="..."`.
- If the report says the key is missing, ask the user to set `EDGEONE_API_KEY` and restart the agent session. Never ask the user to paste the key into the chat, and never write the key into files or command lines yourself.

Calls count against the Makers free quota (500,000 tokens per month); each report shows the tokens deducted.

## Usage

Resolve `scripts/detect.py` relative to this SKILL.md's directory.

```bash
# Text argument
python3 <skill_dir>/scripts/detect.py --text "text to check"

# File (preferred for long text: no shell quoting issues)
python3 <skill_dir>/scripts/detect.py --file /path/to/article.md

# Raw JSON response instead of the Markdown report
python3 <skill_dir>/scripts/detect.py --file /path/to/article.md --json

# One merged score; the default scores each paragraph separately
python3 <skill_dir>/scripts/detect.py --file /path/to/article.md --is-merge
```

## Report fields

1. **Overall AI rate**: (AI ratio + suspected-AI ratio) × 100%.
2. **Human ratio**: share of content judged human-written.
3. **Overall confidence** (`softmax_confidence`, 0–1): higher means more likely AI. `ratio_confidence` is the overall share of suspected-risk content.
4. **Segment labels** (`segment_labels`): 0 = human, 1 = AI-generated, 2 = suspected AI.
5. **High-risk segments**: every segment labeled 1 or 2, with its order, confidence, and full text.
6. **Tokens** (`makers_models_usage.total_tokens`): Makers free-quota tokens deducted by this call.

Adapted from ZimingADR/zhuque-skill (MIT, see `LICENSE`): the key comes only from `EDGEONE_API_KEY`, `--api-key` was removed, and links point to the international site.
