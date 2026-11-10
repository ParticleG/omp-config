#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tencent Zhuque AIGC text detection via the EdgeOne Makers gateway (@makers/zhuque-text).

Exit codes: 0 = detection succeeded, 1 = key/API/network error, 2 = invalid input.
"""

import argparse
import http.client
import json
import os
import sys
import urllib.error
import urllib.request

# Ensure UTF-8 output on consoles with a non-UTF-8 locale
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

API_URL = "https://ai-gateway.edgeone.link/v1/providers/zhuque-text/classify"
KEY_ENV = "EDGEONE_API_KEY"
KEY_CONSOLE_URL = "https://console.tencentcloud.com/edgeone/makers?tab=models&subTab=apikey"
TIMEOUT_SECONDS = 60
# The Zhuque web detector refuses text shorter than this; the API still scores it, but less reliably.
MIN_RELIABLE_CHARS = 350
LABEL_NAMES = {0: "🟢 人工", 1: "🔴 AI 生成", 2: "🟡 疑似 AI"}


class DetectError(Exception):
    pass


def detect_text(text: str, is_merge: bool) -> dict:
    key = os.environ.get(KEY_ENV)
    if not key:
        raise DetectError(f"未检测到 API Key！请设置环境变量 {KEY_ENV}。\n获取 Key（国际站）: {KEY_CONSOLE_URL}")

    req = urllib.request.Request(
        API_URL,
        data=json.dumps({"text": text, "is_merge": is_merge}).encode("utf-8"),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8", errors="replace")
        except (OSError, http.client.HTTPException):
            body = ""
        raise DetectError(f"HTTP {e.code}: {body.replace(key, '[REDACTED]')}") from None
    except (OSError, http.client.HTTPException) as e:
        raise DetectError(f"网络错误: {getattr(e, 'reason', None) or e!r}") from None

    try:
        return json.loads(body)
    except json.JSONDecodeError:
        raise DetectError(f"响应不是合法 JSON: {body.replace(key, '[REDACTED]')[:300]}") from None


def segment_range(seg: dict):
    """The API returns position as [start, length]; convert it to a [start, end) character range."""
    pos = seg.get("position")
    if isinstance(pos, list) and len(pos) == 2 and all(isinstance(n, int) for n in pos):
        return pos[0], pos[0] + pos[1]
    return None


def format_range(seg: dict) -> str:
    rng = segment_range(seg)
    return f"[{rng[0]}, {rng[1]})" if rng else "-"


def generate_report(result: dict, char_count: int, is_merge: bool) -> str:
    labels_ratio = result.get("labels_ratio") or {}
    human_ratio = (labels_ratio.get("0") or 0) * 100
    ai_ratio = (labels_ratio.get("1") or 0) * 100
    suspect_ratio = (labels_ratio.get("2") or 0) * 100
    softmax_conf = result.get("softmax_confidence") or 0.0
    ratio_conf = result.get("ratio_confidence") or 0.0
    tokens = (result.get("makers_models_usage") or {}).get("total_tokens", "?")

    report = ["### 🔍 朱雀 AIGC 文本检测诊断报告\n"]
    report.append(f"- **送检字数**: `{char_count}`（is_merge={str(is_merge).lower()}）")
    if char_count < MIN_RELIABLE_CHARS:
        report.append(f"- ⚠️ **文本少于 {MIN_RELIABLE_CHARS} 字**：朱雀网页版不检测这么短的文本，本结果稳定性较差，仅供参考")
    report.append(f"- **综合 AI 率 (AI + 疑似 AI)**: `{ai_ratio + suspect_ratio:.1f}%` (确认为 AI: `{ai_ratio:.1f}%`, 疑似 AI: `{suspect_ratio:.1f}%`)")
    report.append(f"- **人工内容占比**: `{human_ratio:.1f}%`")
    report.append(f"- **整体置信度**: `{softmax_conf:.4f}` | **疑似风险占比**: `{ratio_conf:.4f}`")
    report.append(f"- **本次扣减额度 Token**: `{tokens}`\n")

    segments = result.get("segment_labels") or []
    if not segments:
        return "\n".join(report)

    report.append("#### 📑 分段检测详情\n")
    report.append("| 序号 | 判定类型 | 置信度 | 字符区间 | 文本片段摘要 |")
    report.append("| :--- | :--- | :--- | :--- | :--- |")
    for seg in segments:
        seg_text = (seg.get("text") or "").replace("\n", " ").strip()
        if len(seg_text) > 40:
            seg_text = seg_text[:37] + "..."
        seg_text = seg_text.replace("|", "\\|")
        report.append(
            f"| {seg.get('order', '-')} | {LABEL_NAMES.get(seg.get('label'), '未知')} | "
            f"`{seg.get('conf') or 0:.4f}` | {format_range(seg)} | {seg_text} |"
        )

    high_risk = [s for s in segments if s.get("label") in (1, 2)]
    if high_risk:
        report.append("\n#### ⚠️ AI / 疑似 AI 分段全文：")
        for seg in high_risk:
            report.append(
                f"\n> **【分段 #{seg.get('order')}】[{LABEL_NAMES[seg['label']]} | 置信度: {seg.get('conf') or 0:.4f} | 字符区间: {format_range(seg)}]**\n"
                f"> {(seg.get('text') or '').strip().replace(chr(10), chr(10) + '> ')}"
            )
    else:
        report.append("\n> ✅ **没有分段被判为 AI 或疑似 AI。**")

    return "\n".join(report)


def main():
    parser = argparse.ArgumentParser(
        description="Zhuque AIGC text detector. Reads --text, --file, or stdin.",
        epilog="Exit codes: 0 = success, 1 = key/API/network error, 2 = invalid input.",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--text", type=str, help="Text to detect")
    source.add_argument("--file", type=str, help="Path to a UTF-8 text file to detect")
    parser.add_argument("--is-merge", action="store_true", help="Score the whole text as one segment (no localization)")
    parser.add_argument("--json", action="store_true", help="Print the raw API response instead of the Markdown report")
    args = parser.parse_args()

    if args.text is not None:
        content = args.text
    elif args.file:
        try:
            with open(args.file, "r", encoding="utf-8-sig") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError) as e:
            print(f"Error: cannot read '{args.file}': {e}", file=sys.stderr)
            sys.exit(2)
    elif not sys.stdin.isatty():
        content = sys.stdin.read()
    else:
        parser.print_help(sys.stderr)
        sys.exit(2)

    if not content.strip():
        print("Error: empty text provided.", file=sys.stderr)
        sys.exit(2)

    try:
        result = detect_text(content, is_merge=args.is_merge)
    except DetectError as e:
        print(f"### ❌ 朱雀 AI 检测失败\n\n- **错误信息**: {e}", file=sys.stderr)
        sys.exit(1)

    succeeded = result.get("status") == "success"
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    elif succeeded:
        print(generate_report(result, len(content), args.is_merge))
    else:
        print(f"### ❌ 朱雀 AI 检测失败\n\n- **错误信息**: {result.get('msg') or result}", file=sys.stderr)
    sys.exit(0 if succeeded else 1)


if __name__ == "__main__":
    main()
