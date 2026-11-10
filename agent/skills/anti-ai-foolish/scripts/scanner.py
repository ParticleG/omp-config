# -*- coding: utf-8 -*-
"""scanner.py —— anti-ai-foolish 规则引擎。
用法:
  python scripts/scanner.py <文本.md/txt> [--json out.json]
加载 rules/ 全部分库 → 剥信源备注 → 逐条扫描 → 报告（按severity分层，含fix建议）。
输出 Z分（confirmed AI规则命中 − reversed 人味方向规则命中，与作者发布版引擎一致）。"""
import os, re, io, json, sys, argparse

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_DIR = os.path.join(HERE, 'rules')

def load_rules():
    rules = []
    for f in sorted(os.listdir(RULES_DIR)):
        if f.startswith('R_') and f.endswith('.json'):
            rules.extend(json.load(io.open(os.path.join(RULES_DIR, f), encoding='utf-8')))
    return rules

# Notes-section detection. Labels within the first 200 characters are ignored, and sentences such as
# 参考资料显示… are never labels.
_LABEL = '(?:信源备注|处理说明|参考资料|参考文献|资料来源|数据来源)'
# A label on its own: plain, or bold with the colon inside or outside the bold.
_LABEL_ONLY = rf'(?:\*\*{_LABEL}[ \t]*[：:]?\*\*|{_LABEL})[ \t]*[：:]?[ \t]*'
# Starts the notes section wherever it appears: bold 信源备注/处理说明, a heading whose whole text is a label,
# or a line that is only a label (indentation, including full-width spaces, allowed).
NOTES_HEADER = re.compile(r'\*\*(?:信源备注|处理说明)[：:]?\*\*'
                          rf'|^ {{0,3}}#{{1,6}}[ \t]+{_LABEL_ONLY}(?:#+[ \t]*)?$'
                          rf'|^[ \t\u3000]*{_LABEL_ONLY}$', re.M)
# `label：text` on one line is also a chart caption (数据来源：国家统计局) inside the body, so it starts the
# notes section only when every later non-empty line looks like a citation entry.
NOTES_INLINE = re.compile(rf'^[ \t\u3000]*(?:\*\*{_LABEL}[ \t]*[：:]\*\*|(?:\*\*)?{_LABEL}(?:\*\*)?[ \t]*[：:])[ \t]*\S.*$', re.M)
# A citation entry is a numbered/bulleted/URL/label line of at most 120 characters (URLs excluded) with at most
# one sentence end, or a short line that does not end like a sentence. `3.5亿…` is not a number marker, and a
# numbered line holding several sentences is a prose paragraph.
CITATION_MARK = re.compile(rf'(?:\[\d+\]|\d+[.、)）](?!\d)|[-*+][ \t]|https?://|(?:\*\*)?{_LABEL})')
SHORT_LINE = re.compile(r'(?!.*[。！？…”"]$).{1,60}$')

def _citation(line):
    if CITATION_MARK.match(line):
        return len(prose(line)) <= 120 and len(re.findall('[。！？]', line)) <= 1
    return bool(SHORT_LINE.match(line))

def cut_notes(text):
    """Drop the notes section (see NOTES_HEADER / NOTES_INLINE)."""
    starts = [m.start() for m in NOTES_HEADER.finditer(text) if m.start() > 200]
    for m in NOTES_INLINE.finditer(text):
        if m.start() > 200 and all(_citation(l.strip()) for l in text[m.end():].splitlines() if l.strip()):
            starts.append(m.start())
            break
    return text[:min(starts)] if starts else text

# CommonMark ATX heading line, also inside a blockquote (`> ## 小标题` renders as a heading).
HEADING = re.compile(r'^ {0,3}(?:(?:>[ \t]?)+ {0,3})?#{1,6}(?:[ \t].*)?$', re.M)

# Markdown that readers never see as text: image tags, link targets, bare URLs, HTML tags, code backticks.
# Left in, URL query strings count as question marks and inflate character counts.
NON_TEXT = [(re.compile(r'!\[[^\]\n]*\]\([^)\n]*\)'), ''),
            (re.compile(r'\[([^\]\n]*)\]\([^)\n]*\)'), r'\1'),
            (re.compile(r"https?://[A-Za-z0-9\-._~:/?#@!$&'*+,;=%]+"), ''),  # ASCII only: text after a URL stays
            (re.compile(r'</?[A-Za-z][A-Za-z0-9-]*(?:[ \t/][^<>\n]*)?>'), ''),  # not 收入<GDP增速…>
            (re.compile(r'`([^`\n]+)`'), r'\1')]

def prose(text):
    for rx, repl in NON_TEXT:
        text = rx.sub(repl, text)
    return text

# Half-width punctuation next to CJK text and zero-width characters are a known way to shift detector
# scores without changing structure; gates and rules see them as the full-width marks they stand for.
ZERO_WIDTH = re.compile('[\u200b-\u200d\u2060\ufeff]')
_CJK = '\u4e00-\u9fff\u3000-\u303f\uff00-\uffef“”‘’'
# `.` only after CJK and not before a letter, digit or another dot, so 报告.docx and ... stay as they are.
HALF_PUNCT = re.compile(f'(?<=[{_CJK}])(?:[,:;?!]|\\.(?![A-Za-z0-9.]))|[,:;?!](?=[{_CJK}])')
HALF_DASH = re.compile(f'(?<=[{_CJK}])(?:-{{2,}}|—)(?=[{_CJK}])')
FULL_WIDTH = {',': '，', ':': '：', ';': '；', '?': '？', '!': '！', '.': '。'}

def normalize(text):
    text = ZERO_WIDTH.sub('', text)
    return HALF_DASH.sub('——', HALF_PUNCT.sub(lambda m: FULL_WIDTH[m.group()], text))

def anomalies(text):
    """Count zero-width characters and CJK-adjacent half-width punctuation/dashes in the body."""
    raw = prose(HEADING.sub('', cut_notes(text)))
    zw = len(ZERO_WIDTH.findall(raw))
    raw = ZERO_WIDTH.sub('', raw)
    return {'半角标点': len(HALF_PUNCT.findall(raw)), '半角破折号': len(HALF_DASH.findall(raw)), '零宽字符': zw}

def strip_body(text, notes=True):
    """Body text for checking. notes=False keeps every line (for chunks already cut from a whole article)."""
    return normalize(prose(HEADING.sub('', cut_notes(text) if notes else text))).strip()

def kilo(t):
    return max(len(t) / 1000, 0.3)

HUMANE_DIRECTIONS = ('人味', 'HUMAN')

def scan(text, notes=True):
    body = strip_body(text, notes)
    rules = load_rules()
    hits, humane, info = [], [], []
    z_ai = z_hu = 0
    for r in rules:
        if r.get('mode') == 'meta':
            info.append((r['id'], r['name'], r['fix']))
            continue
        try:
            rx = re.compile(r['pattern'], re.M)
        except re.error:
            continue
        if r['mode'] == 'density':
            val = len(rx.findall(body)) / kilo(body)
            fired = val > r.get('threshold', 3)
            detail = f'{val:.1f}/千字 (阈值{r["threshold"]})'
        else:
            m = rx.search(body)
            fired = bool(m)
            detail = (m.group(0)[:24] if m else '')
        if not fired:
            continue
        entry = {'id': r['id'], 'name': r['name'], 'category': r['category'], 'severity': r['severity'],
                 'direction': r['direction'], 'status': r.get('status', 'untested'), 'detail': detail,
                 'fix': r.get('fix', ''), 'source': r.get('source', '')}
        # Z counts the same rules as the author's shipped engine: confirmed AI-direction rules minus reversed
        # 人味-direction rules. Other reversed or HUMAN-direction rules are listed as human signals only;
        # adding them to Z would be an uncalibrated combination.
        if r.get('status') == 'reversed' or r['direction'] in HUMANE_DIRECTIONS:
            humane.append(entry)
            if r.get('status') == 'reversed' and r['direction'] == '人味':
                z_hu += 1
        elif r['direction'] == 'AI':
            hits.append(entry)
            if r.get('status') == 'confirmed':
                z_ai += 1
        else:
            info.append((r['id'], r['name'], r.get('fix', '')))
    return {
        'chars': len(body),
        'z_score': z_ai - z_hu,
        'z_components': {'AI确认命中': z_ai, '人味确认命中': z_hu},
        'AI_hits_by_severity': {sev: [h for h in hits if h['severity'] == sev] for sev in ('high', 'mid', 'low')},
        'AI_hit_total': len(hits),
        'humane_hits': humane,
        'meta': info,
        'verdict': '高危（建议逐条处理high）' if any(h['severity'] == 'high' and h['status'] == 'confirmed' for h in hits)
                   else ('中危（处理high+mid）' if [h for h in hits if h['severity'] == 'high'] else '低危'),
    }

def render(rep, path):
    out = [f"# anti-ai-foolish 扫描报告 — {os.path.basename(path)}", '',
           f"正文 {rep['chars']} 字 | **Z分 = {rep['z_score']}**（AI确认{rep['z_components']['AI确认命中']} − 人味确认{rep['z_components']['人味确认命中']}；Z>0判AI侧）",
           f"AI向命中 {rep['AI_hit_total']} 条 | 人味命中 {len(rep['humane_hits'])} 条 | 结论：{rep['verdict']}", '']
    for sev, title in (('high', '高危（实测确认项优先处理）'), ('mid', '中危'), ('low', '低危/参考')):
        hs = rep['AI_hits_by_severity'].get(sev, [])
        if hs:
            out.append(f"## {title} ({len(hs)})")
            for h in hs[:80]:
                st = {'confirmed': '✓实测', 'directional': '~方向性', 'no_signal': '—无信号', 'insufficient': '□未覆盖', 'untested': '○未测'}.get(h['status'], h['status'])
                out.append(f"- **{h['id']} {h['name']}** [{st}] {h['detail']} → {h['fix'] or '见规则库'}（{h['category']}）")
            out.append('')
    hh = rep['humane_hits']
    if hh:
        out.append(f"## 人味命中 ({len(hh)}) — 保留，勿修")
        for h in hh[:40]:
            st = {'reversed': '✓实测' + ('·计入Z' if h['direction'] == '人味' else ''), 'directional': '~方向性'}.get(h['status'], '未确证')
            out.append(f"- {h['id']} {h['name']} [{st}] {h['detail']}")
    return '\n'.join(out)

def read_article(path):
    """Read a .md/.txt/.markdown article; exit with a message for anything else."""
    p = os.path.abspath(os.path.realpath(path))
    if not os.path.isfile(p) or os.path.splitext(p)[1].lower() not in ('.md', '.txt', '.markdown'):
        raise SystemExit('输入必须是存在的 .md/.txt/.markdown 文件: %s' % p)
    return io.open(p, encoding='utf-8-sig').read()  # Windows editors prepend a BOM that hides the title heading

if __name__ == '__main__':
    ap = argparse.ArgumentParser(description='anti-ai-foolish 全规则扫描报告')
    ap.add_argument('article', help='待扫描的 .md/.txt/.markdown 文件')
    ap.add_argument('--json', metavar='OUT', help='另存完整扫描结果为 JSON')
    a = ap.parse_args()
    rep = scan(read_article(a.article))
    print(render(rep, a.article))
    if a.json:
        io.open(a.json, 'w', encoding='utf-8').write(json.dumps(rep, ensure_ascii=False, indent=1))
        print(f'\n[json → {a.json}]')
