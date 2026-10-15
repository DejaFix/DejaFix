// PreToolUse 훅: 에이전트의 `gh pr merge`를 dev 대상·승인 충족 PR로만 제한한다 (docs/agent-collaboration.md 7장).
// - base가 dev가 아니면 차단 (main 머지는 사람만)
// - 작성자가 아닌 승인이 없거나, 변경 요청이 남아 있거나, needs-human 라벨이면 차단
// - contracts/를 바꾸는 PR은 승인 2명 이상 (루트 CLAUDE.md ④)
// dev에 브랜치 규칙이 없으면 GitHub이 --auto 예약을 승인 전에 바로 머지하므로, 이 검사가 그 공백을 막는다.
// 차단하면 exit 2 + stderr 사유. PR 정보를 못 읽으면 머지 쪽은 막는다(fail closed).
import { readFileSync } from 'node:fs'
import { execFileSync } from 'node:child_process'

let input
try {
  input = JSON.parse(readFileSync(0, 'utf8'))
} catch {
  process.exit(0)
}

const command = input.tool_input?.command
if (typeof command !== 'string') process.exit(0)

// 명령 위치(줄 처음, ; & | ( $( 뒤)의 머지만 본다. 커밋 메시지·PR 본문 속 문구는 건너뛴다.
const merges = [...command.matchAll(/(?:^|[;&|(\n])\s*(?:\$\()?\s*gh\s+pr\s+merge\b([^;&|\n)]*)/g)]
if (merges.length === 0) process.exit(0)

function block(reason) {
  console.error(`차단: ${reason} (docs/agent-collaboration.md 7장)`)
  process.exit(2)
}

for (const m of merges) {
  const args = m[1].trim().split(/\s+/).filter(Boolean)
  if (args.includes('--admin')) block('--admin 머지는 쓰지 않는다')
  const target = args.find((a) => !a.startsWith('-'))

  let pr
  try {
    const out = execFileSync(
      'gh',
      ['pr', 'view', ...(target ? [target] : []), '--json', 'number,baseRefName,author,reviews,labels,files'],
      { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], timeout: 20000 },
    )
    pr = JSON.parse(out)
  } catch {
    block(`PR 정보를 읽지 못해 머지를 막았다 (${target ?? '현재 브랜치'})`)
  }

  if (pr.baseRefName !== 'dev') block(`PR #${pr.number}의 대상은 ${pr.baseRefName}이다. 에이전트는 dev만 머지한다. main은 사람이 머지한다`)
  if (pr.labels.some((l) => l.name === 'needs-human')) block(`PR #${pr.number}에 needs-human 라벨이 있다`)

  // 리뷰어별 마지막 의견만 센다 (COMMENTED는 의견 변경으로 보지 않음)
  const latest = new Map()
  for (const r of pr.reviews) {
    const who = r.author?.login
    if (!who || who === pr.author.login) continue
    if (r.state === 'APPROVED' || r.state === 'CHANGES_REQUESTED' || r.state === 'DISMISSED') latest.set(who, r.state)
  }
  const blockers = [...latest].filter(([, s]) => s === 'CHANGES_REQUESTED').map(([who]) => who)
  if (blockers.length) block(`PR #${pr.number}에 변경 요청이 남아 있다: ${blockers.join(', ')}`)

  const approvals = [...latest].filter(([, s]) => s === 'APPROVED').length
  const needed = pr.files.some((f) => f.path.startsWith('contracts/')) ? 2 : 1
  if (approvals < needed) block(`PR #${pr.number}의 승인 ${approvals}명, 필요 ${needed}명 (작성자 본인 제외)`)
}

process.exit(0)
