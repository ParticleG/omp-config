---
name: anti-ai-foolish
description: Pre-publish AI-flavor check for Chinese 公众号/自媒体 long-form articles, used only when the user explicitly asks to remove AI flavor (去AI味/降AI率), asks for an AI-flavor final check (终检) before publishing, or says a draft was flagged by Zhuque (朱雀) or rejected by WeChat (微信打回) as AI-generated. Runs offline punctuation and structure gates plus a Z-score built from rules the author A/B-tested on 52 Zhuque-labeled commentary fragments, then guides block-level revision. Not for general proofreading or style polishing without an AI-detection concern, or for fiction, academic, legal or English text.
---

# anti-ai-foolish — 去AI味终检

Publishing gatekeeper for Chinese articles. It answers one question: **is this draft safe to publish, or does it still read as AI-generated?** It decides with mechanical gates (punctuation, quoting habits, question density, people-present signals, block skeleton), a rule-count Z-score, and three human-judgment checks that regex cannot see.

Evidence base: the author A/B-tested the 1,108 rules against 52 fragments with real Zhuque detector labels (95% CI). Only 8 rules came out as confirmed AI signals and 10 as validated human signals (`reversed`); 981 had too few hits to judge, 68 showed no signal, 13 were directional and 28 are meta/exemption entries. Statuses live in each rule JSON; see `references/评测报告.md` for the author's own validation report.

## When to use

Only for Chinese 公众号/自媒体 long-form articles where the concern is AI detection:

- User wants a draft checked for AI flavor before publishing (去AI味终检 / 发文前AI味检查).
- User says a draft "太AI了", was flagged by WeChat, or scored high on a detector.
- User wants an AI-flavored draft rewritten/surgically repaired (七刀手术).

**Do not use** for: general proofreading or style polishing with no AI-detection concern ("这篇文章帮我看看" alone is not enough), fiction/web-novel dialogue polishing (different genre rules), academic or legal writing (cohesion is required there), English text (corpus is Chinese commentary).

## Workflow

### Step 1 — Mechanical preflight (always run first)

```bash
python scripts/preflight.py <article.md>
```

Read the output:
- **8/8 gates + Z < 0 → ✅ 可发**. Still run Step 2 before publishing.
- **Gates failed → ❌ 停下手术**. Go to Step 3.
- Z-score = hits of the 8 confirmed AI-direction rules − hits of the 3 reversed 人味-direction rules (直接引语, 顶真, 叙事重复排比), exactly as the author's shipped engine computes it. Positive means AI-side. The other reversed rules (实际上, 我说, 可能, 真实地名, 三连短语, 对仗分句) are listed as human signals but not counted; the author's 97% recall / 53% specificity were most likely measured with this shipped computation.

The six hard gates: 冒号=0, 破折号=0, 直引号=0, 概念引用腔≤3/千字, 疑问句≤3/千字, 无小节标题. 冒号=0 does not count a colon that follows a speech verb and opens a quotation (`他说：“…”`, `先生问他：“…”`, `她回复：“…”`; verbs 说 道 问 答 讲 曰 喊 叫 骂 嚷 回复 告诉, optionally followed by a pronoun or 记者; `「` counts as a quotation mark): that is direct speech, which the rule set counts as a human signal (R6055), so it is reported separately. Every other colon counts, including one before a quoted term (`关键词：“内卷”`). Rule R5001 in the Z-score still counts every colon, as the author calibrated it. The seventh gate, 人味弹药≥2类, needs at least two kinds of the methodology's "person present" signals (gate 6): 直接引语, 专名人物, 真实地名, 顶真, 实际上. For the full-rule report with per-hit fixes, run `python scripts/scanner.py <article.md>`.

The eighth gate, 篇内骨架比 (from upstream v3.3.0), splits the body into ~1,200-char blocks and flags a block of ≥800 characters whose argument signals (concept words such as 结构/系统/话语, 所以, self-answered questions) reach 5/千字 while its lived-experience signals (experiential 我, time anchors, direct quotes, concrete measures) stay at or below max(2/千字, the article median). Such a concept-skeleton block is not fixed by punctuation surgery; send it to knife 7. Evidence is a single Zhuque pair (z21: concept block 0.63 vs lived block 0.40 after all six mechanical gates passed), and its concept-word list comes from the author's cultural-commentary essays, so treat it as a pointer, not a measurement.

Half-width punctuation next to Chinese text (`,` `:` `;` `?` `!`, a `.` after a Chinese character, `--` or a single `—` between characters) is read as the full-width mark it stands for, and zero-width characters are removed before checking; preflight reports how many it found. Swapping punctuation width or inserting invisible characters only disguises the text and must be reverted in the published draft.

Scan scope: the body ends where the notes section starts. A bold `**信源备注**`/`**处理说明**`, a heading whose whole text is a source label (`## 参考资料`; `## 数据来源之争` is an ordinary heading), or a line that is only a source label (参考资料, 参考文献, 资料来源, 数据来源, 信源备注, 处理说明; plain or bold, indented or not, with an optional colon inside or after the bold such as `**参考资料：**`) starts it wherever it appears. A one-line `label：text` such as `数据来源：国家统计局` is usually a chart caption, so it starts the notes section only when every later non-empty line looks like a citation entry: a line of at most 120 characters (URLs not counted) with at most one 。！？ that starts with `[1]`, `1.`, `1、`, a list bullet, a URL or another source label (`3.5亿…` is not a number marker), or a short line of at most 60 characters that does not end like a sentence. Otherwise the body continues past it. Labels within the first 200 characters are ignored, and sentences like 参考资料显示… are not labels. Text after `---` separators is still body text. Image tags, link targets, bare URLs, HTML tags (an ASCII tag name followed by a space, `/` or `>`, so `收入<GDP增速` is text) and code backticks are not body text (a WeChat image URL's `?wx_fmt=` would otherwise count as a question mark); link text and text right after a URL stay. Half-width punctuation between two Latin letters or digits (`3:2`, `1,000`) stays as it is. A leading H1 (`# 标题`, a UTF-8 BOM is ignored) is the article title; every later ATX heading (`#`–`######` after up to 3 spaces, followed by a space or tab, also inside a `>` quote such as `> ## 小标题`) is removed from the body and, like every 一、/二、 numbering marker in the body, counts against 无小节标题.

### Step 2 — Human judgment (regex cannot do these three)

Check each 1,000–2,000-char block:

1. **Experiential-"I" vs performative-"I"** — "我已经学了二十多年市场营销" (real, checkable experience → human, measured 0.0036) vs "你以为你独立思考" / "我称之为" (pose → AI, measured 0.998).
2. **Are people the subject?** — If concrete people only appear as an opening example and the body is concept/data reasoning, it still reads AI (measured 0.997) even with a named person in it.
3. **Symmetrical argument triples** — "可以X，却不能Y" ×3. Colloquial repetition ("降价了，降价了") is human and must be kept; only the argument-symmetry kind gets broken.

### Step 3 — Seven-knife surgery (per 1,000–2,000-char block, in effect-size order)

Split the body into blocks and gate each one:

```bash
python scripts/preflight.py <article.md> --chunks <dir>
```

This splits the body into balanced blocks of at most 2,000 characters. Every line break is a paragraph boundary (plain-text drafts put one paragraph per line); a paragraph longer than 2,000 characters is split at sentence ends, with a closing quote kept on its sentence. Each block's reader-visible text goes to `<dir>/chunk_NN.txt`: headings, notes, images, URLs, `**`/`~~` emphasis, `>` markers, list bullets and separator lines (`---`, `***`, `* * *`) are removed, and the writer's own characters, underscores included, are otherwise unchanged; existing files are never overwritten. It prints per-block Z-score and gates; blocks are checked as they are, without looking for a notes section again, so a caption at a block's end counts the same as in the whole-article check. Work block by block.

1. 冒号 — strongest single AI signal (r=+0.43). Replace definition-style colons (真相是：, X：Y, 关键词：“…”) with commas or split sentences. A colon after a speech verb that introduces a direct quotation (他说：“…”) stays. Source-note sections exempt.
2. 概念引用腔 — quoting your own jargon ("信息阶层") is a 5.5× AI habit. Keep ≤1 quoted term per article.
3. 数据罗列 — three or more bare numbers in sequence get folded into events ("门票六百多，不到一双专项鞋的一半"). Numbers attached to people/actions are fine; bare number ladders are not.
4. 金句对称收尾 — delete symmetrical aphorism endings ("不是坏账，是没人信"). Keep the judgment, drop the symmetry.
5. 结构 — remove section headings, break uniform paragraph lengths, scatter enumeration chains.
6. 轻词表 — only real hits; 90+ word-list rules failed validation on this corpus.
7. **换骨架 (treats the cause)** — make lived experience / named people with direct quotes / un-inventable details the *skeleton* of each block, not decoration. This is the difference between 0.75 and 0.09 in the paired-sample test.

After surgery, re-run Step 1 until ✅.

### Step 4 — Platform test

Test each `chunk_NN.txt` from Step 3 separately, never the whole article (auto-chunking merges theory into data blocks). If the `zhuque` skill is installed and `EDGEONE_API_KEY` is set, run its `scripts/detect.py --file <dir>/chunk_NN.txt` on every chunk; it calls the same Zhuque model through Tencent EdgeOne's API, with no captcha or daily web limit, and the text leaves the machine, so ask before sending confidential drafts. Otherwise the user pastes each chunk into matrix.tencent.com/ai-detect (3 free text checks a day as a guest, 20 after login, with an image captcha). Tencent Cloud's docs cap one AI-text detection at 2,000 characters and recommend 350–2,000; blocks under 350 characters are flagged in the preflight output. Target: block AIGC ≤ 0.40. Zhuque scores are a reference only: the author found no public evidence that WeChat uses Zhuque scores to decide penalties.

## Output format

Report as:

```
## 终检报告 — <文件名>
Z分: <n>（AI确认<x> − 人味确认<y>）
硬门: <p>/8（列出失败项）
人味弹药: <n>类命中
判定: ✅可发 / ⚠️改后复检 / ❌停下手术
下一步: <具体到哪一块哪一刀>
```

## Compliance

- This skill checks writing-quality signals; it is not a way to hide AI involvement. Under 《人工智能生成合成内容标识办法》 (in force since 2025-09-01) and WeChat's announcement, content generated or substantially rewritten by AI must be declared with the platform's 创作声明 at publish time, and platform-added AI labels must not be removed or hidden. Remind the user of this when a draft came from AI.
- WeChat's April 2026 "非真人自动化创作" rule prohibits using AI, scripts or APIs to replace the real creator: generating, rewriting or splicing content detached from the creator's own expression, batch or automated publishing, and spreading tutorials, methods or services for non-human automated creation. Penalties include traffic limits, deletion, capability limits and bans.
- Never simulate editing behavior, fake typos or "account warming" to look human. Knife 7 must use the writer's own experience and material; if the writer has none to give, say so instead of writing around it.

## Iron rules

1. Never alter the writer's own sentences (原话一字不改). `rules/R_豁免用户指纹.json` records the original skill author's personal voice (说白了, 逗号连写, 段尾判断直收, 设问定义体); it is reference material and not applied by the scripts. For another writer, preserve that writer's own recurring habits instead.
2. Target is the human baseline band, not 0% — human writing itself scores 54–72% on proxy detectors. Once gates pass, stop.
3. Performed imperfections (fake typos, inserted filler colloquialisms, half-width punctuation swaps, zero-width characters) are forbidden; the author measured fake imperfections as still 77% AI.
4. Never fabricate anchors. Facts, numbers, quotes and sources stay untouched.

## Limits

- 97% recall / 53% specificity were measured by the author with their own engine on the 52-fragment corpus; they cannot be reproduced here. It is a quality gate, not a human-vs-AI classifier. Z<0 does not prove "human-written". The 人味弹药 and 篇内骨架比 gates have no recall/specificity figures.
- The r=0.813 correlation in the references belongs to the author's earlier 196-rule Z (7 AI − 7 human rules), not to the shipped rule set; no correlation is published for the current Z.
- Corpus genre is Chinese self-media commentary. The 52-fragment corpus is not shipped (excluded by `.gitignore`). `scripts/abtest.py` re-scores every rule on a labeled corpus you provide at `validation/corpus/zhuque_corpus.json` (JSON array of `{"text": ..., "aigc": 0–1}`, fragments over 200 characters). By default it only prints old vs new status counts, including what happens to the rules the Z-score uses; `--write` overwrites `rules/*.json`. A rule that fires in fewer than 5 fragments becomes `insufficient`, so a small corpus silently empties the Z-score: collect about as many fragments as the author's 52, back up `rules/` first (`cp -a rules rules.bak`; the rule files also match the upstream GitHub repo), and compare the counts before writing.
- Traditional-script input is out of scope. The colon exemption and R6055 match simplified 说/告诉 only, so `說：「…」` counts against 冒号=0 and does not count as 直接引语; the word lists behind 专名人物 and 真实地名 are simplified too. The two traditional controls in the benchmark were converted with `opencc -c t2s` before scoring, so their stored text matches their Zhuque labels.
- `python scripts/benchmark.py` compares the gates and Z-score with real Zhuque results on `validation/benchmark/zhuque_benchmark.json`: 8 公众号-style articles generated by AI and 10 public-domain human texts (鲁迅, 胡适 1959 演讲, 朱自清, 郁达夫, 许地山; two simplified with opencc), scored 2026-11-10. Zhuque puts every AI article at 100% and every human text at 0%, and all 123 of its segments agree with the ground truth. Against that the skill blocks all 8 AI articles, passes 1 of 10 human texts, and the Z-score separates AI from human segments with AUC ≈ 0.78. Per-text gates over those segments: 冒号 93% vs 35%, 概念引用腔 89% vs 44%, 疑问句 42% vs 37%, 破折号 16% vs 21%; per article, 人味弹药 fails 7/8 AI and 1/10 human, 篇内骨架比 2/8 and 1/10 (one firing is 胡适's argumentative speech), so a 骨架比 warning is not by itself evidence of AI. Two contrasts are artifacts of how the set was built: 直引号 (73% vs 0%) because the essays are typeset with `“”` while the AI articles carry ASCII quotes, and 无小节标题 (73% vs 1%) because the generation prompt asked for sections. The human side is 1920s–1950s prose, not modern 公众号 commentary, so 疑问句 and 破折号 failing to separate the groups there is not evidence that the author's calibration is wrong; read these numbers as a false-alarm check, not a calibration. 概念引用腔 counts `“”` only, so `「」` text under-reports it. To extend the set, append entries with the same fields; `zhuque` is the raw `detect.py --json` output for `preflight.reader_text(article)`. It never changes the rules.

## References

Read on demand:

- `references/方法论与证据链.md` — full methodology: skeleton–fuel law, the 16 close-reading rules, exemption rationale, publish discipline (revised for compliance). Its tool list (`gate_check.py`, `dbs_check.py`, `score_all.py`, `rule_abtest2.py`, `zhuque_chunks.py`, the 李白 engine) refers to the author's private workspace and is not shipped; the runnable equivalents are `scripts/preflight.py` (gates, Z-score, `--chunks`) and `scripts/scanner.py` (full rule report).
- `references/评测报告.md` — validation report: classification power, cross-skill comparison, honest limits.
- `references/ROADMAP.md` — project roadmap.
- `rules/INDEX.json` — rule counts per library; each rule JSON carries `status` / `evidence` / `fix` / `exempt_when`.
- `validation/benchmark/zhuque_benchmark.json` — 18 articles (8 AI, 10 public-domain human) with their raw Zhuque results, and `scripts/benchmark.py`, the read-only runner that prints the per-article verdicts, the per-text gate rates and the per-article gate counts; see Limits for what the numbers do and do not show.
