#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tencent Zhuque AIGC Text Detector via EdgeOne Makers API
"""

import os
import sys
import json
import argparse
import urllib.request
import urllib.error

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

API_URL = "https://ai-gateway.edgeone.link/v1/providers/zhuque-text/classify"

def detect_text(text: str, is_merge: bool = False) -> dict:
    key = os.environ.get("EDGEONE_API_KEY")
    if not key:
        return {
            "status": "error",
            "msg": "未检测到 API Key！请设置环境变量 EDGEONE_API_KEY。\n获取 Key（国际站）: https://console.tencentcloud.com/edgeone/makers?tab=models&subTab=apikey"
        }

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    payload = {
        "text": text,
        "is_merge": is_merge
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(API_URL, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        return {
            "status": "error",
            "code": e.code,
            "msg": f"HTTPError {e.code}: {err_body}"
        }
    except Exception as e:
        return {
            "status": "error",
            "msg": str(e)
        }

def generate_report(result: dict) -> str:
    if result.get("status") != "success":
        return f"### ❌ 朱雀 AI 检测失败\n\n- **错误信息**: {result.get('msg', '未知错误')}\n"

    labels_ratio = result.get("labels_ratio", {})
    human_ratio = labels_ratio.get("0", 0.0) * 100
    ai_ratio = labels_ratio.get("1", 0.0) * 100
    suspect_ratio = labels_ratio.get("2", 0.0) * 100
    total_ai_rate = ai_ratio + suspect_ratio

    softmax_conf = result.get("softmax_confidence", 0.0)
    ratio_conf = result.get("ratio_confidence", 0.0)
    tokens = result.get("makers_models_usage", {}).get("total_tokens", 0)

    report = []
    report.append("### 🔍 朱雀 AIGC 文本检测诊断报告\n")
    report.append(f"- **综合 AI 率 (AI + 疑似 AI)**: `{total_ai_rate:.1f}%` (确认为 AI: `{ai_ratio:.1f}%`, 疑似 AI: `{suspect_ratio:.1f}%`)")
    report.append(f"- **人工内容占比**: `{human_ratio:.1f}%`")
    report.append(f"- **整体置信度**: `{softmax_conf:.4f}` | **疑似风险占比**: `{ratio_conf:.4f}`")
    report.append(f"- **本次消耗 Token**: `{tokens}`\n")

    segment_labels = result.get("segment_labels", [])
    if segment_labels:
        report.append("#### 📑 分段检测详情与高危片段标记\n")
        report.append("| 序号 | 判定类型 | 置信度 | 文本片段摘要 |")
        report.append("| :--- | :--- | :--- | :--- |")

        type_map = {0: "🟢 人工", 1: "🔴 AI 生成", 2: "🟡 疑似 AI"}
        for seg in segment_labels:
            order = seg.get("order", "-")
            lbl = seg.get("label", 0)
            conf = seg.get("conf", 0.0)
            seg_text = seg.get("text", "").replace("\n", " ").strip()
            if len(seg_text) > 40:
                seg_text = seg_text[:37] + "..."
            type_name = type_map.get(lbl, "未知")
            report.append(f"| {order} | {type_name} | `{conf:.4f}` | {seg_text} |")

        # List high-risk segments specifically
        high_risk = [s for s in segment_labels if s.get("label") in (1, 2)]
        if high_risk:
            report.append("\n#### ⚠️ 需重点改写的高危段落清单：")
            for s in high_risk:
                lbl_str = "AI 生成" if s.get("label") == 1 else "疑似 AI"
                report.append(f"\n> **【段落 #{s.get('order')}】[{lbl_str} | 置信度: {s.get('conf', 0):.4f}]**\n> {s.get('text')}")
        else:
            report.append("\n> ✅ **未发现明显 AI 或疑似 AI 特征的高危分段，整体表现良好！**")

    return "\n".join(report)

def main():
    parser = argparse.ArgumentParser(description="Zhuque AIGC Text Detector")
    parser.add_argument("--text", type=str, help="Text to detect")
    parser.add_argument("--file", type=str, help="Path to text file to detect")
    parser.add_argument("--is-merge", action="store_true", default=False, help="Merge paragraphs into single score")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--report", action="store_true", default=True, help="Output formatted markdown report")

    args = parser.parse_args()

    content = ""
    if args.text:
        content = args.text
    elif args.file:
        if not os.path.exists(args.file):
            print(f"Error: file '{args.file}' not found.", file=sys.stderr)
            sys.exit(1)
        with open(args.file, "r", encoding="utf-8") as f:
            content = f.read()
    else:
        if not sys.stdin.isatty():
            content = sys.stdin.read()
        else:
            parser.print_help()
            sys.exit(1)

    if not content.strip():
        print("Error: empty text provided.", file=sys.stderr)
        sys.exit(1)

    result = detect_text(content, is_merge=args.is_merge)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(generate_report(result))

if __name__ == "__main__":
    main()
