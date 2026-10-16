// PreToolUse 훅: 에이전트의 `git push`를 한 가지 형태로만 허용한다 (docs/agent-collaboration.md 7장).
//   git push [-u] origin <브랜치>   — <브랜치>는 fix/·docs/·feat/·test/·chore/로 시작, ':'·'+'·추가 인자 없음
// 그 밖(-f·--force*·--mirror·--all·--delete·--tags 등 플래그, refspec ':', '+', origin 외 원격, main·dev 대상)은 전부 막는다.
// `git -c k=v push`, `bash -c "..."`·`sh -c`·`eval`, `$(...)`·백틱, heredoc으로 셸에 넘긴 명령, xargs·env·timeout 뒤의 git도 검사한다.
// 해석이 안 되면(따옴표 미종료, 변수·치환으로 만든 인자 등) 막는다(fail closed). 차단하면 exit 2 + stderr 사유.
import { readFileSync } from 'node:fs'

let input
try {
  input = JSON.parse(readFileSync(0, 'utf8'))
} catch {
  process.exit(0)
}

const command = input.tool_input?.command
if (typeof command !== 'string') process.exit(0)

const BRANCH = /^(fix|docs|feat|test|chore)\/[A-Za-z0-9._/-]+$/
const SHELLS = new Set(['bash', 'sh', 'zsh', 'dash', 'ksh', 'ash'])
const PS = new Set(['powershell', 'pwsh', 'cmd'])
const KEYWORDS = new Set(['{', '}', '!', 'if', 'then', 'else', 'elif', 'fi', 'do', 'done', 'while', 'until', 'time'])
// 값을 따로 받는 git 전역 옵션 / 값 없는 전역 옵션
const GIT_OPT_VALUE = new Set(['-C', '--git-dir', '--work-tree', '--namespace', '--exec-path', '--config-env', '--super-prefix'])
const GIT_OPT_FLAG = new Set([
  '--no-pager', '-p', '--paginate', '-P', '--bare', '--no-replace-objects', '--literal-pathspecs',
  '--glob-pathspecs', '--noglob-pathspecs', '--icase-pathspecs', '--no-optional-locks', '--no-lazy-fetch',
])

class Blocked extends Error {}
function block(reason) {
  throw new Blocked(reason)
}

const base = (w) => w.v.replace(/\\/g, '/').split('/').pop().toLowerCase().replace(/\.exe$/, '')

// ---- 셸 명령 해석: 단순 명령 목록 [{ words: [{v, opaque}], heredocs: [본문] }] 과 치환 본문 목록 ----
function lex(src) {
  const cmds = []
  const subs = []
  let cur = { words: [], heredocs: [] }
  let word = null
  let skipNext = false // 리다이렉션 대상 단어는 인자가 아니다
  let hereString = false
  const pending = [] // { cmd, delim, strip }
  let i = 0
  const n = src.length

  const startWord = () => {
    if (word === null) word = { v: '', opaque: false }
  }
  const endWord = () => {
    if (word === null) return
    if (hereString) cur.heredocs.push(word.v), (hereString = false)
    else if (!skipNext) cur.words.push(word)
    skipNext = false
    word = null
  }
  const endCmd = () => {
    endWord()
    if (cur.words.length || cur.heredocs.length) cmds.push(cur)
    cur = { words: [], heredocs: [] }
  }
  // '(' 위치에서 짝 맞는 ')'까지 (따옴표 고려)
  const balanced = (start) => {
    let depth = 0
    for (let j = start; j < n; j++) {
      const c = src[j]
      if (c === '\\') j++
      else if (c === "'") {
        j = src.indexOf("'", j + 1)
        if (j < 0) break
      } else if (c === '"') {
        j++
        while (j < n && src[j] !== '"') j += src[j] === '\\' ? 2 : 1
      } else if (c === '(') depth++
      else if (c === ')' && --depth === 0) return j
    }
    throw new Error('괄호가 닫히지 않음')
  }
  const backtick = (start) => {
    let j = start + 1
    while (j < n && src[j] !== '`') j += src[j] === '\\' ? 2 : 1
    if (j >= n) throw new Error('백틱이 닫히지 않음')
    return j
  }
  // $ 처리: 치환·변수는 값을 알 수 없으므로 opaque
  const dollar = () => {
    const nx = src[i + 1]
    if (nx === '(') {
      const end = balanced(i + 1)
      if (src[i + 2] !== '(') subs.push(src.slice(i + 2, end)) // $(( )) 산술은 명령이 아님
      word.opaque = true
      i = end + 1
    } else if (nx === '{' || /[A-Za-z0-9_@*#?$!-]/.test(nx ?? '')) {
      word.opaque = true
      if (nx === '{') {
        const end = src.indexOf('}', i)
        if (end < 0) throw new Error('${ 가 닫히지 않음')
        i = end + 1
      } else if (/[A-Za-z_]/.test(nx)) {
        i++
        while (i < n && /[A-Za-z0-9_]/.test(src[i])) i++
      } else i += 2 // $1 $@ $? 같은 특수 변수 한 글자
    } else {
      word.v += '$'
      i++
    }
  }
  const readHeredocs = () => {
    // 줄바꿈 직후 i에서 heredoc 본문들을 읽는다
    for (const h of pending) {
      const lines = []
      for (;;) {
        if (i >= n) throw new Error(`heredoc ${h.delim} 이 닫히지 않음`)
        let e = src.indexOf('\n', i)
        if (e < 0) e = n
        let line = src.slice(i, e).replace(/\r$/, '')
        i = e + 1
        if (h.strip) line = line.replace(/^\t+/, '')
        if (line === h.delim) break
        lines.push(line)
      }
      h.cmd.heredocs.push(lines.join('\n'))
    }
    pending.length = 0
  }

  while (i < n) {
    const c = src[i]
    if (c === ' ' || c === '\t' || c === '\r') {
      endWord()
      i++
    } else if (c === '\n') {
      endCmd()
      i++
      if (pending.length) readHeredocs()
    } else if (c === '#' && word === null) {
      while (i < n && src[i] !== '\n') i++
    } else if (c === '&' && src[i + 1] === '>') {
      endWord()
      i += src[i + 2] === '>' ? 3 : 2
      skipNext = true
    } else if (c === ';' || c === '&' || c === '|' || c === '(' || c === ')') {
      endCmd()
      i++
    } else if (c === '<' && src[i + 1] === '<') {
      endWord()
      if (src[i + 2] === '<') {
        i += 3
        hereString = true
        continue
      }
      i += 2
      let strip = false
      if (src[i] === '-') strip = true, i++
      while (src[i] === ' ' || src[i] === '\t') i++
      let delim = ''
      while (i < n && !/[\s;&|<>()]/.test(src[i])) {
        if (src[i] === "'" || src[i] === '"') {
          const q = src[i]
          const e = src.indexOf(q, i + 1)
          if (e < 0) throw new Error('heredoc 구분자 따옴표가 닫히지 않음')
          delim += src.slice(i + 1, e)
          i = e + 1
        } else if (src[i] === '\\') {
          delim += src[i + 1] ?? ''
          i += 2
        } else delim += src[i++]
      }
      if (!delim) throw new Error('heredoc 구분자가 없음')
      pending.push({ cmd: cur, delim, strip })
    } else if (c === '<' || c === '>') {
      if (word && /^\d+$/.test(word.v) && !word.opaque) word = null // 2>&1 의 2
      else endWord()
      i++
      while (src[i] === '>' || src[i] === '&' || src[i] === '|') i++
      if (/\d|-/.test(src[i] ?? '') && src[i - 1] === '&') {
        while (/[\d-]/.test(src[i] ?? '')) i++ // >&2, >&-
      } else skipNext = true
    } else if (c === "'") {
      startWord()
      const e = src.indexOf("'", i + 1)
      if (e < 0) throw new Error('작은따옴표가 닫히지 않음')
      word.v += src.slice(i + 1, e)
      i = e + 1
    } else if (c === '$' && src[i + 1] === "'") {
      // $'...' — 이스케이프가 있으면 값을 단정하지 않는다
      startWord()
      let j = i + 2
      let raw = ''
      while (j < n && src[j] !== "'") {
        if (src[j] === '\\') word.opaque = true, (raw += src[j++])
        raw += src[j++]
      }
      if (j >= n) throw new Error("$'가 닫히지 않음")
      word.v += raw
      i = j + 1
    } else if (c === '"') {
      startWord()
      i++
      while (i < n && src[i] !== '"') {
        const d = src[i]
        if (d === '\\') {
          const e = src[i + 1]
          if (e === '\n') i += 2
          else if ('"\\$`'.includes(e)) (word.v += e), (i += 2)
          else (word.v += d), i++
        } else if (d === '$') dollar()
        else if (d === '`') {
          const e = backtick(i)
          subs.push(src.slice(i + 1, e))
          word.opaque = true
          i = e + 1
        } else (word.v += d), i++
      }
      if (i >= n) throw new Error('큰따옴표가 닫히지 않음')
      i++
    } else if (c === '\\') {
      if (src[i + 1] === '\n') i += 2
      else startWord(), (word.v += src[i + 1] ?? ''), (i += 2)
    } else if (c === '$') {
      startWord()
      dollar()
    } else if (c === '`') {
      startWord()
      const e = backtick(i)
      subs.push(src.slice(i + 1, e))
      word.opaque = true
      i = e + 1
    } else {
      startWord()
      word.v += c
      i++
    }
  }
  endCmd()
  if (pending.length) throw new Error(`heredoc ${pending[0].delim} 본문이 없음`)
  return { cmds, subs }
}

// ---- git push 형태 검사 ----
function checkPush(args, shown) {
  if (args.some((a) => a.opaque)) block(`변수·치환으로 만든 인자는 해석할 수 없다: ${shown}`)
  const v = args.map((a) => a.v)
  const rest = v[0] === '-u' ? v.slice(1) : v
  const flag = rest.find((a) => a.startsWith('-'))
  if (flag) block(`플래그 ${flag}는 허용하지 않는다 (-u만 origin 앞에 허용): ${shown}`)
  if (rest.length !== 2) block(`허용 형태는 'git push [-u] origin <브랜치>' 하나뿐이다: ${shown}`)
  const [remote, branch] = rest
  if (remote !== 'origin') block(`원격은 origin만 허용한다 (${remote}): ${shown}`)
  if (!BRANCH.test(branch)) {
    block(`브랜치는 fix/·docs/·feat/·test/·chore/로 시작해야 하고 ':'·'+'·플래그를 쓸 수 없다 (${branch}): ${shown}`)
  }
}

function checkGit(args, shown) {
  let j = 0
  while (j < args.length) {
    const a = args[j]
    if (a.opaque) {
      if (args.slice(j).some((w) => w.v === 'push' || w.opaque)) block(`git 인자를 해석할 수 없다: ${shown}`)
      return
    }
    if (a.v === '-c') {
      const val = args[j + 1]
      if (!val || val.opaque) block(`git -c 값을 해석할 수 없다: ${shown}`)
      if (/^alias\./i.test(val.v)) block(`git -c alias.* 는 쓸 수 없다: ${shown}`)
      j += 2
    } else if (GIT_OPT_VALUE.has(a.v)) j += 2
    else if (GIT_OPT_FLAG.has(a.v) || /^--(git-dir|work-tree|namespace|exec-path|config-env|super-prefix)=/.test(a.v)) j++
    else if (a.v.startsWith('-')) {
      if (args.slice(j).some((w) => w.v === 'push')) block(`알 수 없는 git 옵션 ${a.v} 뒤의 push: ${shown}`)
      return
    } else {
      if (a.v === 'push') checkPush(args.slice(j + 1), shown)
      return
    }
  }
}

function analyze(src, depth = 0) {
  if (depth > 8) block('중첩이 너무 깊다')
  let parsed
  try {
    parsed = lex(src)
  } catch (e) {
    if (/git|push/i.test(src)) block(`명령을 해석하지 못했다 (${e.message})`)
    return
  }
  for (const s of parsed.subs) analyze(s, depth + 1)
  for (const cmd of parsed.cmds) {
    let words = cmd.words
    const assigns = []
    while (words.length && (KEYWORDS.has(words[0].v) || /^[A-Za-z_][A-Za-z0-9_]*=/.test(words[0].v))) {
      if (!KEYWORDS.has(words[0].v)) assigns.push(words[0].v)
      words = words.slice(1)
    }
    if (!words.length) continue
    const shown = words.map((w) => (w.opaque ? '<?>' : w.v)).join(' ')

    // 명령 이름 자체가 변수·치환이면 무엇을 실행하는지 알 수 없다
    if (words[0].opaque && words.slice(1).some((w) => w.opaque || w.v === 'push' || w.v === 'git')) {
      block(`명령 이름을 해석할 수 없다: ${shown}`)
    }

    words.forEach((w, k) => {
      if (w.opaque) return
      const name = base(w)
      const after = words.slice(k + 1)
      // xargs·env·timeout·nohup 등 뒤에 와도 git은 git이다
      if (name === 'git') {
        if (after.some((x) => x.v === 'push') && assigns.some((a) => /^GIT_/.test(a))) {
          block(`GIT_* 환경 변수를 붙인 git push는 허용하지 않는다: ${shown}`)
        }
        checkGit(after, shown)
      } else if (SHELLS.has(name)) {
        const ci = after.findIndex((x) => !x.opaque && /^-[A-Za-z]*c[A-Za-z]*$/.test(x.v))
        if (ci >= 0) {
          const script = after[ci + 1]
          if (!script) block(`${name} -c 뒤에 명령이 없다: ${shown}`)
          if (script.opaque) block(`${name} -c 명령을 해석할 수 없다: ${shown}`)
          analyze(script.v, depth + 1)
        }
        for (const h of cmd.heredocs) analyze(h, depth + 1)
      } else if (name === 'eval') {
        if (after.some((x) => x.opaque)) block(`eval 인자를 해석할 수 없다: ${shown}`)
        analyze(after.map((x) => x.v).join(' '), depth + 1)
      } else if (PS.has(name)) {
        const ci = after.findIndex((x) => /^([-/](c|command)|-encodedcommand|-enc|-e)$/i.test(x.v))
        if (ci >= 0) {
          if (/enc/i.test(after[ci].v) || /^-e$/i.test(after[ci].v)) block(`인코딩된 명령은 해석할 수 없다: ${shown}`)
          analyze(after.slice(ci + 1).map((x) => x.v).join(' '), depth + 1)
        }
      }
    })
  }
}

try {
  analyze(command)
} catch (e) {
  if (e instanceof Blocked) {
    console.error(`차단: ${e.message} (docs/agent-collaboration.md 7장, .claude/hooks/guard-push.mjs)`)
    process.exit(2)
  }
  console.error(`차단: push 검사 중 오류 (${e.message})`)
  process.exit(2)
}
process.exit(0)
