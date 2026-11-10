# -*- coding: utf-8 -*-
"""scripts/preflight.py —— 发文前一键快筛（anti-ai-foolish）。
用法: python scripts/preflight.py <文章.md> [--chunks DIR]
流程: 剥信源 → 全规则扫描 → 硬门（冒号/破折号/直引号/概念引用腔/疑问句密度/小节标题/人味弹药/篇内骨架比）→ Z分 → 判定 发/改/停。
--chunks DIR: 另按段落边界把正文切成 ≤2000 字的块，逐块过同一套门，并把每块的读者可见文字写成 DIR/chunk_NN.txt 供朱雀逐块复测。"""
import os, sys, io, re, math, argparse, statistics

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scanner import scan, strip_body, cut_notes, kilo, HEADING, read_article, anomalies, prose

# Formatting marks readers never see in the published article; chunk files drop them before pasting into
# Zhuque. Separator lines go before emphasis so `***` is not read as bold; paired emphasis keeps its text.
# Underscores are left alone: `__` emphasis is rare in Chinese drafts and `____` is usually a typed blank.
BLOCKQUOTE = re.compile(r'^[ \t]{0,3}(?:>[ \t]?)+', re.M)
MARKUP = [(re.compile(r'^ {0,3}(?:(?:-[ \t]*){3,}|(?:\*[ \t]*){3,}|(?:_[ \t]*){3,})$', re.M), ''),
          (re.compile(r'\*\*(?=\S)(.+?)(?<=\S)\*\*'), r'\1'),
          (re.compile(r'~~(?=\S)(.+?)(?<=\S)~~'), r'\1'),
          (re.compile(r'\*\*'), ''),
          (re.compile(r'^ {0,3}(?:[-*+]|\d+[.)])[ \t]+', re.M), '')]

def reader_text(text):
    """Body as a reader sees it: no headings, notes, images, link targets, URLs or Markdown marks.
    Keeps the writer's own characters (no punctuation normalization)."""
    text = BLOCKQUOTE.sub('', prose(HEADING.sub('', cut_notes(text))))
    for rx, repl in MARKUP:
        text = rx.sub(repl, text)
    return text.strip()

# Tencent Cloud docs: one AI-text detection run accepts at most 2000 characters; 350–2000 is recommended.
ZHUQUE_MAX, ZHUQUE_MIN = 2000, 350

# 人味弹药 = methodology gate 6 (references/方法论与证据链.md, 第三层): "person present" signals, at least two
# kinds per block. Generic syntax hits (三连短语, 对仗分句) are human signals for the Z-score only.
AMMO = {'直接引语': {'R6055'}, '专名人物': {'R7011', 'R7012'}, '真实地名': {'R7009'},
        '顶真': {'R6011'}, '实际上': {'R8-词表·libai-203'}}

# Speech verb (optionally with a pronoun object or 记者), colon, opening quote; 「」 counts as a quote mark.
# Simplified verbs only: the skill targets simplified 公众号 text, and R6055 matches 说/告诉 alone.
SPEECH_COLON = re.compile(r'(?:[说道问答讲曰喊叫骂嚷]|回复|告诉)(?:[我你他她]们?|记者)?[ \t]*：[ \t]*[“「"]')

def check(text, notes=True):
    """Run the hard gates and the Z-score on one text; return (scan report, gates, verdict).
    notes=False for chunks: they come from reader_text, so the notes section is already gone."""
    body = strip_body(text, notes)
    rep = scan(text, notes)
    gates = []
    # A colon after a speech verb that opens a quotation (他说：“…”, 先生问他：“…”) is direct speech, which the rule
    # set counts as a human signal (R6055); every other colon, including 关键词：“内卷”, counts against the gate.
    quoted = len(SPEECH_COLON.findall(body))
    colon = body.count('：') - quoted
    gates.append(('冒号=0', colon == 0, f'{colon}处' + (f'（另有{quoted}处说话引语前冒号不计）' if quoted else '')))
    dash = body.count('——')
    gates.append(('破折号=0', dash == 0, f'{dash}处'))
    dq = body.count('"')
    gates.append(('直引号=0', dq == 0, f'{dq}处'))
    concept = len(re.findall(r'[“"][^”"]{2,7}[”"]', body)) / kilo(body)
    gates.append(('概念引用腔≤3/千字', concept <= 3, f'{concept:.1f}/千字'))
    q = body.count('？') + body.count('?')
    qd = q / kilo(body)
    gates.append(('疑问句≤3/千字', qd <= 3, f'{qd:.1f}/千字'))
    md = (cut_notes(text) if notes else text).lstrip()
    if re.match(r'#(?:[ \t]|$)', md, re.M):  # a leading H1 is the article title, not a section
        md = md.partition('\n')[2]
    sec_titles = len(HEADING.findall(md)) + len(re.findall(r'[一二三四五六七八九十]+、', body))
    gates.append(('无小节标题', sec_titles == 0, f'{sec_titles}处'))
    fired = {h['id'] for h in rep['humane_hits']}
    ammo = [kind for kind, ids in AMMO.items() if ids & fired]
    gates.append(('人味弹药≥2类', len(ammo) >= 2, f"{len(ammo)}类命中（{'、'.join(ammo) or '无'}）"))
    skel_warn = skeleton_check(body)
    gates.append((SKELETON_GATE, not skel_warn, skel_warn or '各块骨架均衡'))
    passed = sum(1 for _, ok, _ in gates if ok)
    if skel_warn and all(ok for name, ok, _ in gates if name != SKELETON_GATE):
        verdict = '⚠️ 标点已净但存在概念骨架块——需换骨架（挂人挂事），不是继续改标点'
    elif passed == len(gates) and rep['z_score'] < 0:
        verdict = '✅ 可发（朱雀切块复测后发布）'
    elif passed >= len(gates) - 2:
        verdict = '⚠️ 改后复检'
    else:
        verdict = '❌ 停下手术'
    return rep, gates, verdict

SKELETON_GATE = '篇内骨架比（无纯概念块）'

def skeleton_check(body):
    """Upstream v3.3.0 gate. Split the body into ~1200-char blocks; a block of ≥800 chars whose argument
    signals are ≥5/千字 while its lived-experience signals are ≤ max(2/千字, the median of all blocks) is a
    concept-skeleton block. Returns a description of the worst such block, or '' when there is none.
    Argument = concept words + 2×所以 + self-answered questions; lived = experiential 我 + time anchors +
    direct quotes + concrete measure details (all per 千字). Evidence: one Zhuque pair (z21: 0.63 vs 0.40)."""
    paras = [p.strip() for p in body.split('\n') if p.strip()]
    blocks, cur, size = [], [], 0
    for p in paras:
        cur.append(p)
        size += len(p)
        if size >= 1200:
            blocks.append('\n'.join(cur))
            cur, size = [], 0
    if cur:
        blocks.append('\n'.join(cur))
    if len(blocks) < 2:
        return ''
    def metrics(t):
        k = kilo(t)
        arg = (sum(t.count(w) for w in ('标准', '系统', '结构', '符号', '谱系', '权力', '审美', '话语', '叙事', '语境')) / k
               + 2 * t.count('所以') / k
               + len(re.findall(r'[？?][^。]{0,20}(?:是|因为|答案)', t)) / k)
        nar = (len(re.findall(r'我(?:前几天|那天|把|写|走|看|越想|小时候|以前|刚刚)', t))
               + len(re.findall(r'半小时后|那天|前几天|当时', t))
               + len(re.findall(r'告诉我|说[：，]', t))
               + len(re.findall(r'[0-9一二三四五六七八九十]+(?:分钟|米|号|岁|个字|年)', t))) / k
        return arg, nar
    ms = [metrics(b) for b in blocks]
    nar_med = statistics.median(m[1] for m in ms)
    worst, worst_desc = None, ''
    for i, (arg, nar) in enumerate(ms):
        if len(blocks[i]) >= 800 and arg >= 5.0 and nar <= max(2.0, nar_med):
            if worst is None or arg > worst:
                worst = arg
                worst_desc = f'第{i+1}块（{len(blocks[i])}字）：论证指标{arg:.1f}/千字、经历信号{nar:.1f}/千字——概念骨架块'
    return worst_desc

SENTENCE = re.compile(r'[^。！？；]*[。！？；]+[”’」』）)"]*|[^。！？；]+')

def split_blocks(body, limit=ZHUQUE_MAX):
    """Split body text into balanced blocks of at most `limit` characters. Every line break is a paragraph
    boundary (plain-text drafts put one paragraph per line); a paragraph longer than `limit` is split into
    sentences, and a sentence longer than `limit` is cut at `limit`."""
    pieces = []  # (separator before the piece, text)
    for p in (p.strip() for p in body.split('\n')):
        if not p:
            continue
        parts = [p] if len(p) <= limit else [s for s in SENTENCE.findall(p) if s]
        for j, s in enumerate(parts):
            for k in range(0, len(s), limit):
                pieces.append(('\n\n' if j == 0 and k == 0 else '', s[k:k + limit]))
    if not pieces:
        return []
    total = sum(len(sep) + len(t) for sep, t in pieces) - len(pieces[0][0])
    target = total / math.ceil(total / limit)
    blocks, cur = [], ''
    for sep, t in pieces:
        if cur and (len(cur) + len(sep) + len(t) > limit or len(cur) >= target):
            blocks.append(cur)
            cur = ''
        cur = cur + sep + t if cur else t
    blocks.append(cur)
    if len(blocks) > 1 and len(blocks[-1]) < ZHUQUE_MIN and len(blocks[-2]) + 2 + len(blocks[-1]) <= limit:
        blocks[-2:] = [blocks[-2] + '\n\n' + blocks[-1]]  # a too-short tail joins the previous block when it fits
    return blocks

def main():
    ap = argparse.ArgumentParser(description='anti-ai-foolish 发文前快筛')
    ap.add_argument('article', help='待检查的 .md/.txt/.markdown 文件')
    ap.add_argument('--chunks', metavar='DIR', help='逐块检查，并把每块写成 DIR/chunk_NN.txt（不覆盖已有文件）')
    a = ap.parse_args()
    text = read_article(a.article)
    rep, gates, verdict = check(text)
    print(f"# Preflight — {os.path.basename(a.article)}")
    print(f"正文 {rep['chars']} 字 | Z分 {rep['z_score']}（AI确认{rep['z_components']['AI确认命中']} − 人味确认{rep['z_components']['人味确认命中']}）")
    for name, ok, detail in gates:
        print(f"  {'✓' if ok else '✗'} {name}: {detail}")
    print(f"门通过 {sum(ok for _, ok, _ in gates)}/{len(gates)} → {verdict}")
    found = {k: v for k, v in anomalies(text).items() if v}
    if found:
        print('⚠️ ' + '、'.join(f'{k}{v}处' for k, v in found.items())
              + '：已按全角标点/删除零宽字符后检查。发布稿请改回规范中文标点并删除零宽字符，标点替换不改变文章骨架。')
    if not a.chunks:
        return
    blocks = split_blocks(reader_text(text))
    os.makedirs(a.chunks, exist_ok=True)
    print(f"\n## 分块（每块 ≤{ZHUQUE_MAX} 字，朱雀建议 {ZHUQUE_MIN}–{ZHUQUE_MAX} 字）")
    for i, block in enumerate(blocks, 1):
        out = os.path.join(a.chunks, f'chunk_{i:02d}.txt')
        try:
            with io.open(out, 'x', encoding='utf-8') as f:
                f.write(block + '\n')
        except FileExistsError:
            raise SystemExit(f'已存在，未覆盖: {out}')
        brep, bgates, bverdict = check(block, notes=False)
        failed = '、'.join(n for n, ok, _ in bgates if not ok) or '无'
        short = f' ⚠️ 少于{ZHUQUE_MIN}字，朱雀结果不可靠' if len(block) < ZHUQUE_MIN else ''
        print(f"- 块{i:02d} {len(block)}字 → {out} | Z分 {brep['z_score']} | 门 {sum(ok for _, ok, _ in bgates)}/{len(bgates)}（未过：{failed}）→ {bverdict}{short}")

if __name__ == '__main__':
    main()
