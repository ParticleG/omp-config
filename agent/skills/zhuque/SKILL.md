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

`scripts/detect.py` sends text to Tencent Zhuque through the EdgeOne Makers model gateway (`https://ai-gateway.edgeone.link/v1/providers/zhuque-text/classify`) and prints a Markdown report: character count, overall AI rate, human ratio, confidence, a per-segment table with character ranges, and the full text of every AI or suspected-AI segment. It uses only the Python standard library.

## When to use

1. Check a text or file for its overall AI rate and confidence.
2. Compare AI rates before and after a manual revision.
3. Locate the passages labeled AI (label 1) or suspected AI (label 2).
4. The platform test in `anti-ai-foolish` Step 4: run this script on each chunk instead of asking the user to paste into the web detector.

## Before sending text

- The text leaves the machine and goes to Tencent. If it is marked confidential or internal, or contains personal data, ask the user before sending it.
- Send the text as it will be published. Drop non-body material such as YAML front matter or editor notes; keep everything else unchanged, because segment ranges are offsets into exactly what was sent.

## API key

The script reads the key from the `EDGEONE_API_KEY` environment variable only.

- The key is created on the international site: EdgeOne console → Makers → Models → API Key (https://console.tencentcloud.com/edgeone/makers?tab=models&subTab=apikey).
- The user exports it in their shell profile before starting the agent: `export EDGEONE_API_KEY="..."`.
- If the script reports a missing key, ask the user to set `EDGEONE_API_KEY` and restart the agent session. Never ask the user to paste the key into the chat, and never write the key into files or command lines yourself.

## Usage

Resolve `scripts/detect.py` relative to this SKILL.md's directory.

```bash
# File (preferred)
python3 <skill_dir>/scripts/detect.py --file /path/to/article.md

# Text pasted in chat: use a quoted heredoc on stdin, never --text, so quotes and $ survive intact
python3 <skill_dir>/scripts/detect.py <<'EOF'
text to check
EOF

# Raw JSON response instead of the Markdown report
python3 <skill_dir>/scripts/detect.py --file /path/to/article.md --json

# Whole text as a single segment (no localization)
python3 <skill_dir>/scripts/detect.py --file /path/to/article.md --is-merge
```

Exit codes: `0` success, `1` key/API/network error (message on stderr), `2` invalid input. On exit 1, report the error to the user; do not loop retries. Tencent's enterprise Model Pro gateway documentation lists `401` as an invalid key, `429` as rate limiting, and `5xx` as an upstream failure to retry later; the built-in model gateway likely behaves the same, but only `401` was observed here. Whether an exhausted free quota also returns `429` is unverified; check Makers → Overview → Model Usage.

## Reading the result

Behavior below was measured against the live API on 2026-11-10.

- **Segments are not paragraphs.** By default (`is_merge=false`) the model cuts the text into windows: an 810-character text came back as 3 windows of 267–273 characters, a 3,000-character Markdown text as 8 windows of 277–608 characters, and texts up to at least 381 characters as one segment. Window boundaries fall at punctuation, sometimes at a paragraph break and sometimes mid-paragraph, so they cannot be predicted from the paragraph layout. A human-written paragraph inside a flagged window is labeled with the window. With `--is-merge` the whole text is one segment; `labels_ratio` was identical in both modes.
- **Character ranges**: the API's `position` is `[start, length]`; the report shows it as `[start, end)`, offsets in Unicode code points (emoji count as one) into the submitted text. Use the segment text to find the passage in the source file.
- **Short text**: below 350 characters the web detector refuses to run; the API still returns a score, and the report warns that it is less reliable.
- **Deterministic within a session**: a 96-character text sent three times and an 810-character text sent twice returned identical scores and segments, so re-running unchanged text only spends quota. Even trivial edits move the score: prepending two emoji to the 96-character text moved its confidence from 0.6068 to 0.6282. Third-party guides say the detector model is updated monthly, so the same text may score differently on another day. Compare before/after runs in the same mode and on the same day.
- Tencent describes AIGC detection results as auxiliary reference only. Never present a score as proof of who wrote a text.

Report fields:

1. **Overall AI rate**: (AI ratio + suspected-AI ratio) × 100%, from `labels_ratio`.
2. **Human ratio**: share of content judged human-written.
3. **Overall confidence** (`softmax_confidence`, 0–1): higher means more likely AI. `ratio_confidence` is the overall share of suspected-risk content.
4. **Segment labels** (`segment_labels`): 0 = human, 1 = AI-generated, 2 = suspected AI.
5. **Tokens** (`makers_models_usage.total_tokens`): free-quota tokens deducted by this call.

## Quota

Each call deducts `ceil(characters × 5 / 3)` tokens from the account's Makers free quota of 500,000 tokens per month, shared by all keys on the account (exact on 12 measured calls from 10 to 3,000 characters). That is about 300,000 characters per month. Before detecting more than about 30,000 characters in one task, tell the user the estimated deduction.

Adapted from ZimingADR/zhuque-skill (MIT, see `LICENSE`): the key comes only from `EDGEONE_API_KEY`, `--api-key` and `--report` were removed, errors set a non-zero exit code, and the report adds character count, character ranges, and a short-text warning.
