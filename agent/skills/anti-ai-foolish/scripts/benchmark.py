# -*- coding: utf-8 -*-
"""scripts/benchmark.py —— 用带朱雀真实结果的文章检验本 skill 的门与 Z 分。
用法: python scripts/benchmark.py [benchmark.json]   （默认 validation/benchmark/zhuque_benchmark.json）
文件格式: JSON 数组，每项 {"id", "truth": "AI"|"human"|"unknown", "source", "article": Markdown 原文,
"zhuque": zhuque skill `detect.py --json` 的原样输出（对 article 的读者可见文字检测）}。
只读，不改规则库。输出逐篇对照、整篇门失败数（人味弹药、篇内骨架比），以及 ≥200 字朱雀片段上各标点/词面门的
失败率与 Z 分 AUC。"""
import os, sys, io, json, argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from preflight import check, SKELETON_GATE

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Per-text gates: a mark or a rate, meaningful on any length.
SEGMENT_GATES = ['冒号=0', '破折号=0', '直引号=0', '概念引用腔≤3/千字', '疑问句≤3/千字', '无小节标题']
# Article-level gates: 人味弹药 needs two kinds of signal and 篇内骨架比 needs ≥800-char blocks, so a 200-char
# Zhuque segment cannot be judged by them; they are counted per article instead.
ARTICLE_GATES = ['人味弹药≥2类', SKELETON_GATE]

def main():
    ap = argparse.ArgumentParser(description='anti-ai-foolish 朱雀对照评测')
    ap.add_argument('path', nargs='?', default=os.path.join(HERE, 'validation', 'benchmark', 'zhuque_benchmark.json'))
    a = ap.parse_args()
    entries = json.load(io.open(a.path, encoding='utf-8'))
    print(f"{'id':<20}{'truth':<8}{'朱雀AI率':>8}{'Z':>4}{'门':>6}  判定")
    segs = []  # (zhuque says AI, Z, failed per-text gates)
    arts = []  # (zhuque says AI, failed article-level gates)
    for e in entries:
        z = e['zhuque']
        rate = z['labels_ratio']['1'] + z['labels_ratio']['2']
        rep, gates, verdict = check(e['article'])
        print(f"{e['id']:<20}{e['truth']:<8}{rate:>8.0%}{rep['z_score']:>4}{sum(ok for _, ok, _ in gates):>4}/8  {verdict.split('（')[0]}")
        arts.append((e['truth'], {n for n, ok, _ in gates if not ok}))
        for s in z['segment_labels']:
            if len(s['text']) >= 200:
                r2, g2, _ = check(s['text'], notes=False)
                segs.append((s['label'] != 0, r2['z_score'], {n for n, ok, _ in g2 if not ok}))
    ai = [s for s in segs if s[0]]
    hu = [s for s in segs if not s[0]]
    known = [a for a in arts if a[0] in ('AI', 'human')]
    a_ai = [a for a in known if a[0] == 'AI']
    a_hu = [a for a in known if a[0] == 'human']
    print(f'\n门（整篇）：AI {len(a_ai)} 篇，人工 {len(a_hu)} 篇')
    for g in ARTICLE_GATES:
        print(f"{g:<24}{sum(g in a[1] for a in a_ai):>8}/{len(a_ai)}{sum(g in a[1] for a in a_hu):>10}/{len(a_hu)}")
    print(f'\n≥200 字朱雀片段：AI/疑似AI {len(ai)}，人工 {len(hu)}')
    if not ai or not hu:
        return
    print(f"{'门（标点/词面）':<24}{'AI片段未过':>10}{'人工片段未过':>12}")
    for g in SEGMENT_GATES:
        print(f"{g:<24}{sum(g in s[2] for s in ai) / len(ai):>10.0%}{sum(g in s[2] for s in hu) / len(hu):>12.0%}")
    auc = sum((x[1] > y[1]) + 0.5 * (x[1] == y[1]) for x in ai for y in hu) / (len(ai) * len(hu))
    print(f'Z 分区分 AI/人工片段的 AUC: {auc:.3f}（0.5=无区分，1=完全区分）')

if __name__ == '__main__':
    main()
