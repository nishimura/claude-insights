---
name: claude-insights
description: 明示的に指定された cwd/path glob に対応する Claude Code セッション履歴を分析し、Markdown の insights report を書く。
argument-hint: "[path/glob] [brief|normal|deep]"
disable-model-invocation: true
---

# Claude Insights

このファイルは `SKILL.md` の日本語訳。実行用の skill 定義は英語の `SKILL.md` を正とし、この訳文も今後あわせて更新する。

指定された cwd/path glob に対応する Claude Code セッション履歴を分析し、検査可能な Markdown report を書く。workflow は packet files を収集し、選択した evidence を読み、必要なら `deep` mode reviewers を使い、`deep` run では `findings.md` を書いてから `report.md` を作成・検証する。

## Arguments

`$ARGUMENTS` を次のように解釈する:

- target path/glob: Claude Code セッション開始時の cwd、project directory、worktree、または glob
- mode: `brief`, `normal`, `deep`
- optional latest count: `latest:N`、または "latest 3 sessions" のような自然言語
- optional session ID: 完全な Claude Code session UUID、または一意な UUID prefix

内部では次の canonical mode を使う:

- `brief`: `brief`, `short`, `simple`
- `normal`: `normal`, `default`, `standard`, `regular`, `usual`
- `deep`: `detailed`, `detail`, `deep`, `thorough`, `extensive`

target path/glob が指定されていない場合は、Claude Code session startup directory または cwd glob をユーザーに尋ねて待つ。shell の `pwd` から推測しない。`!cd` などにより shell cwd は session startup directory と異なる場合があるため。

default mode は `normal`。

完全な UUID または UUID prefix が指定された場合は、`--session-id` で single-session collection を実行する。disambiguation のために target path/glob が併記されていてもよいが、session-id mode では必須ではない。

ユーザーが latest N sessions を求めた場合は、`--limit N` を渡すか `latest:N` を含める。

## Collector

collector 実行前に、この run 用の小さな temporary correction keyword file を作る。英語の base idea に加えて、ユーザーの現在の言語、または対象セッションに見える言語での類義語を入れる。これは user-correction candidate detection の軽量 hint list であり、確定判定リストではない。短く汎用的な語より、具体的な correction phrase を優先する。通常の設計質問を主に示す語は避ける。

run ごとに一意な temporary file path を使う:

```bash
mkdir -p /tmp/claude-insights-keywords
KEYWORDS_FILE="/tmp/claude-insights-keywords/correction-keywords-$(date +%Y%m%d_%H%M%S).txt"
```

この skill directory から実行する:

```bash
python3 bin/collect-project-packets.py --correction-keyword-file "$KEYWORDS_FILE" --limit 20 "<path-or-glob>"
```

default は次の通り:

- `brief`: `--limit 10`
- `normal`: `--limit 30`
- `deep`: `--limit 40 --exclude-noop --max-main-lines 320 --max-agent-lines 180`

便利な optional flags:

```bash
--session-id 45685c9d-0a30-4101-9924-e1eda0abc0c4
--correction-keyword-file "$KEYWORDS_FILE"
--exclude-noop
--max-main-lines 180
--max-agent-lines 80
--max-agents 12
```

## Report Workflow

1. Python collector を実行する。
2. まず `aggregate.json` と `index.md` を読む。
3. `recommended_packets` と `report_flags` を使って packet file を選ぶ。
4. 選んだ `packets/*.md` だけを開く。すべての packet を盲目的に読まない。
5. main-session behavior と subagent behavior の区別を保つ。
6. 生成された output directory に `report.md` を書く。
7. `report.md` を書いた後、期待する section heading が存在することを確認し、file の冒頭と末尾を読んで完成していることを確認する。

`aggregate.json` や `index.md` を見るだけのために、Bash から ad hoc な `python -c`、`python3 -c`、Python heredoc を使わない。これらの file は直接読むことを優先する。

`aggregate.json` 自体が 1 回の Read token limit を超える場合（10+ sessions の run では 100KB+ になりうる）、ad hoc `python3 -c` に戻らず、bounded `offset`/`limit` range で読む。例: まず `totals` と `subagent_role_stats` の header、その後 `sessions` array の targeted slice を読む。1回の Read limit は session context window とは独立しているため、数回の bounded read は context をほとんど消費しない。

繰り返し必要な JSON transformation がある場合は、挙動を reviewable / reusable にするため、`bin/` 配下に named helper script を追加する。

mode は evidence budget と sampling strategy を変えるものであり、結論の種類を強制するものではない。`brief` でも重大な発見を報告してよいし、evidence が単純なら `deep` でも短い report になってよい。

- `brief`: 最も強い recommended packets を 2-4 件開く。
- `normal`: 重複を開かず、主要な recommended packets を cover する。opened packet content はおおよそ 50-80K token を目安にする。
- `deep`: non-overlapping packet と Large Packet の bounded range を追加する。per-call Read limit を守りつつ、75-120K token 程度を目安にする。

`deep` mode では、subagent が利用可能で、複数の substantive packets または Large Packets がある場合、3 名の second-opinion reviewers を使う。その条件で reviewers を skip する場合は、理由を Evidence Used または Limits に書く。main session が primary analysis と final report に責任を持つ。reviewers は section writers ではない。

- bad points: friction、missed opportunities、user corrections、repeated failures、weak delegation、楽観的な読みを覆す evidence
- good points: うまく機能した workflow、有用な delegation、強い verification、再利用可能な習慣、過度に否定的な読みを覆す evidence
- tool-use quality: tool usage 全体を見る。task を実質的に前進させたか、信頼できる evidence を作ったか、不要な detour を避けたか、noisy tool errors と real blockers を正しく切り分けたかで判断する

reviewers には answer-shaped scope ではなく shared context を渡す: run directory、`aggregate.json`、`index.md`、packet list、Large Packet entries、ユーザー指定 focus。starting points は渡してよいが non-exclusive とする。reviewer 自身が grep target と bounded range を選ぶよう促し、Large Packets を絶対に full-read しないよう remind する。

reviewers には top findings、evidence、importance、contradictions を求める。reviewer prose を `report.md` に貼り付けない。final report を変える、または強める supported findings だけを取り込む。

`deep` mode では、`report.md` の前に run directory に `findings.md` を書く。これは polished report ではなく discovery ledger。含めるもの:

- 実施した discovery checks。user corrections、verification outcomes、blockers、delegation failures、knowledge persistence または repeated learned facts、user interruptions または unnecessary stops、Large Packet handling、focus-specific checks を含む
- stable ID、claim、evidence、impact、source（`main`、reviewer name、または両方）、intended report placement を持つ candidate findings
- `report.md` 作成後の final status: `included`, `diagnostics`, `evidence_only`, `limits`, `omitted_low_materiality`, `omitted_unverified`, `contradicted`

material findings については、短さより網羅性を優先する。`report.md` を短く、またはバランスよく保つためだけに supported finding を落とさない。main narrative が長くなりすぎる場合は、Evidence Used、Diagnostics Notes、Limits に残し、その placement を `findings.md` に記録する。

ユーザーが natural-language focus を指定した場合は、それを packet selection と local-file interpretation の guide にする。focus は skill、command、feature、file area、failure mode、workflow pattern、その他の topic でありうる。`aggregate.json`、`index.md` Focus Hints、first intents、top files、flags、targeted grep を使って likely evidence を特定する。関連する local files は focus 解釈に役立つ場合のみ読む。この挙動を skill definitions に限定しない。

focus は問いを狭めるが、evidence search を狭めるものではない。`deep` mode では、focused packets に加えて、adjacent、representative、error-heavy、verification-heavy な sessions の小さな contrast set を見る。focus は report を整理するために使い、先に答えを決めるために使わない。

focused reports では、focus が特定できない、または誤った仮定が report を misleading にする場合を除き、clarification question で中断しない。明示的な assumptions と limits を書き、follow-up でユーザーに補正してもらうことを優先する。

chronological caution を適用する。現在の files、docs、skills、tests は、古い session 当時のものと異なる場合がある。historical session behavior を current files と比較する場合、packet が同じ rule または file content が当時存在したことを示さない限り、possible evolution、drift、observed mismatch、follow-up checks として表現する。

`Read` tool には 25000-token limit がある。非 ASCII（multibyte）text は token あたりおおよそ 2 bytes を消費するため、significant non-ASCII content を持つ packet は約 40KB または約 700 lines 以上で full read が truncate されうる。pure-ASCII packets は token あたりより多く読めるため、これらの limit は conservative。packet を開く前に:

1. `aggregate.json` と `Large Packets` index section で、その session の `packet_size_bytes`, `packet_line_count`, `large_packet`, `very_large_packet`, `suggested_read_strategy` を確認する。
2. `large_packet` が true なら full-read しない。Metadata、Main Signals、Notable Tool Results、Agent Activity など relevant headings 周辺を `offset`/`limit` の bounded ranges で読むか、targeted lookup に `grep` を使う。
3. `Large Packets` index list を full read の authoritative blocklist として扱う。per-session `suggested_read_strategy` string は同じ signal を繰り返している。

## Packet Selection

次の順序で packets を優先する:

1. `recommended_packets.agent_heavy`
2. `recommended_packets.error_heavy`
3. `recommended_packets.verification_heavy`
4. `recommended_packets.interrupted`
5. `recommended_packets.representative`
6. `recommended_packets.noop_examples`。ただし no-op rate が report-worthy な場合のみ

selection refinement には `index.md` flags を使う:

- `agent-heavy`
- `error-heavy`
- `verification-heavy`
- `edit-heavy`
- `interrupted`
- `user-correction`
- `docs`
- `implementation`

subagent analysis では、`raw_subagent_transcript_count` と `logical_subagent_role_count` を比較する。raw transcripts は file 間で split されることがあり、logical roles は parent delegation labels から来る。

`aggregate.json` の `subagent_role_stats`、`subagent_*`、`combined_*` fields も確認する。legacy `verification_count` と `error_count` fields は main-session counts。subagent verification と errors は別に report される。report/document completeness checks は `report_verification_*` fields に別計上され、build/test の `verification_count` には含まれない。

Subagent tool counts は tool_use ID で de-duplicate される。elapsed role activity には `active_minutes_union` を優先する。`active_minutes_cumulative` は resumed agents の repeated context を含みうる。

## Report Shape

ユーザーが別の指定をしない限り、この section set から始める:

```markdown
# Session Insights Report

## Scope

## Executive Summary

## Main Workflow Patterns

## Subagent / Delegation Patterns

## Friction and Failure Modes

## What Worked Well

## Improvements to Try

## Evidence Used

## Diagnostics Notes

## Limits of This Report
```

これらの sections は defaults であり quotas ではない。埋めるために弱い positives、negatives、improvements を作らない。material evidence がない section は merge、shorten、omit してよい。subsection headings は high-signal findings を読みやすくする場合のみ使う。

ordinary project reports は、`aggregate.json`、`index.md`、packet metadata、collector counts を見なくても `report.md` 単体で理解できるように書く。Executive Summary から collector field names と collector-derived totals を外す: edit/write totals、verification totals、error totals、subagent error totals、raw/logical transcript counts、active-minute totals、`role_stats` counts。これは "main 32 / subagent 14 / total 46 errors" のように自然語で書かれている場合にも適用する。Executive Summary に置ける count は、sessions reviewed、domain object counts、`PHPUnit 8/8 passed` のような test results など、direct reader-facing project facts のみ。

raw fields と parser caveats は、verification に重要な場合、Evidence Used、Diagnostics Notes、Limits of This Report に置く。通常の読者が report を理解するためにそれらの section を読む必要がないようにする。

focused または chronology-sensitive reports では、hard verdicts より evidence-backed observations と hypotheses を優先する。後続の improvement session や current file で解釈を検証すべき場合は、assumptions と follow-up checks を含める。

## Self-Test Mode

ユーザーが `/claude-insights self-test ...` を起動した場合は、full self-test workflow、required checks、verdict format のために [self-test.md](self-test.md) を読む。ordinary project reports ではこの file を load しない。
