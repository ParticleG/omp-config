# -*- coding: utf-8 -*-
"""scripts/abtest.py —— 全量规则在朱雀标签语料上的A/B验证。
判定：confirmed（CI不含0且|d|≥0.10）/ reversed（人味方向过CI）/ no_signal / insufficient（触发<5）。
meta与豁免规则不参与。默认只打印新旧 status 对比；加 --write 才回写 rules/*.json 与 validation/results/abtest_results.json。
语料太小时大部分规则会变成 insufficient，Z分随之失效：作者用的是 52 个 >200 字的片段。回写前先备份 rules/。"""
import os, re, io, json, sys, argparse
from collections import Counter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scanner import load_rules, kilo

ap = argparse.ArgumentParser(description='anti-ai-foolish 规则 A/B 重验')
ap.add_argument('--write', action='store_true', help='把新 status 写回 rules/*.json（会覆盖现有校准）')
args = ap.parse_args()

CORPUS = os.path.join(HERE, 'validation', 'corpus', 'zhuque_corpus.json')
if not os.path.isfile(CORPUS):
    raise SystemExit(f'缺少语料 {CORPUS}\n作者未随包发布 52 片段语料（被 .gitignore 排除）。'
                     '请自备朱雀标签语料：JSON 数组，每项 {"text": 片段原文, "aigc": 朱雀AIGC值0–1}。')
corpus = [c for c in json.load(io.open(CORPUS, encoding='utf-8')) if c['text'] and len(c['text']) > 200]
N = len(corpus); aigc = [c['aigc'] for c in corpus]; texts = [c['text'] for c in corpus]

def stats(fired):
    n1 = sum(fired); n0 = N - n1
    if n1 == 0 or n0 == 0: return None
    m1 = sum(a for a, f in zip(aigc, fired) if f) / n1
    m0 = sum(a for a, f in zip(aigc, fired) if not f) / n0
    v1 = sum((a - m1) ** 2 for a, f in zip(aigc, fired) if f) / n1
    v0 = sum((a - m0) ** 2 for a, f in zip(aigc, fired) if not f) / n0
    se = (v1 / n1 + v0 / n0) ** .5
    diff = m1 - m0; lo, hi = diff - 1.96 * se, diff + 1.96 * se
    sd = (sum((a - sum(aigc) / N) ** 2 for a in aigc) / N) ** .5
    r = (m1 - m0) * ((n1 / N) * (1 - n1 / N)) ** .5 / sd if sd else 0
    return n1, m1, m0, diff, lo, hi, r

rules = load_rules()
results = {}
for r in rules:
    if r.get('mode') == 'meta' or r['category'].startswith('豁免'):
        continue
    try:
        rx = re.compile(r['pattern'], re.M)
    except re.error:
        results[r['id']] = {'status': 'regex_error'}
        continue
    if r['mode'] == 'density':
        fired = [len(rx.findall(t)) / kilo(t) > r.get('threshold', 3) for t in texts]
    else:
        fired = [bool(rx.search(t)) for t in texts]
    st = stats(fired)
    if st is None:
        results[r['id']] = {'status': 'insufficient', 'n': 0}
        continue
    n1, m1, m0, diff, lo, hi, corr = st
    if n1 < 5:
        status = 'insufficient'
    elif diff > 0.10 and lo > 0:
        status = 'confirmed'
    elif diff < -0.10 and hi < 0:
        status = 'reversed'  # 人味方向
    elif abs(diff) >= 0.15:
        status = 'directional'
    else:
        status = 'no_signal'
    results[r['id']] = {'status': status, 'n': n1, 'm1': round(m1, 3), 'm0': round(m0, 3),
                        'diff': round(diff, 3), 'ci': [round(lo, 3), round(hi, 3)], 'r': round(corr, 2)}

old = {r['id']: r.get('status', 'untested') for r in rules if r['id'] in results}
changed_ids = [rid for rid, v in results.items() if v['status'] != 'regex_error' and v['status'] != old[rid]]
print(f'验证规则 {len(results)} 条 | 片段 {N}（作者原语料 52 片段）')
print('原 status:', dict(Counter(old.values())))
print('新 status:', dict(Counter(v['status'] for v in results.values())))
print('Z分所用规则（原 confirmed AI / reversed 人味）的新状态:',
      dict(Counter(results[r['id']]['status'] for r in rules if r['id'] in results
                   and ((r['direction'] == 'AI' and old[r['id']] == 'confirmed') or (r['direction'] == '人味' and old[r['id']] == 'reversed')))))
print(f'将改变 status 的规则: {len(changed_ids)} 条')
print('\n== confirmed（AI信号）TOP15 ==')
for rid, v in sorted(results.items(), key=lambda kv: -kv[1].get('diff', 0))[:15]:
    if v['status'] == 'confirmed':
        print(f"  {rid:<16} n={v['n']:>2} diff={v['diff']:+.3f} CI{v['ci']} r={v['r']:+.2f}")
print('\n== reversed（人味信号）TOP15 ==')
for rid, v in sorted(results.items(), key=lambda kv: kv[1].get('diff', 0))[:15]:
    if v['status'] == 'reversed':
        print(f"  {rid:<16} n={v['n']:>2} diff={v['diff']:+.3f} CI{v['ci']} r={v['r']:+.2f}")

if not args.write:
    print('\n[试运行] 未写入。确认新旧对比可接受、已备份 rules/ 后，加 --write 回写。')
    sys.exit(0)

import glob
for f in glob.glob(os.path.join(HERE, 'rules', 'R_*.json')):
    rs = json.load(io.open(f, encoding='utf-8'))
    changed = False
    for r in rs:
        if r['id'] in results:
            res = results[r['id']]
            if res['status'] == 'regex_error':
                continue
            r['status'] = res['status']
            r['evidence'] = f"AB(n={res['n']}, diff={res.get('diff')}, CI{res.get('ci')}, r={res.get('r')})"
            changed = True
    if changed:
        io.open(f, 'w', encoding='utf-8').write(json.dumps(rs, ensure_ascii=False, indent=1))
io.open(os.path.join(HERE, 'validation', 'results', 'abtest_results.json'), 'w', encoding='utf-8').write(json.dumps(results, ensure_ascii=False, indent=1))
print('\n[已写入] rules/*.json 与 validation/results/abtest_results.json')
