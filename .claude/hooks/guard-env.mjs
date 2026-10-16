// PreToolUse 훅: .env 편집 시도를 차단한다 (.env.example은 허용).
// 차단하면 exit 2 + stderr 사유 (Claude에게 전달됨). 입력을 못 읽으면 막지 않는다.
// contracts/ 보호는 훅이 아니라 PR 2인 승인 규칙으로 한다 (루트 CLAUDE.md ④).
import { readFileSync } from 'node:fs'
import path from 'node:path'

let input
try {
  input = JSON.parse(readFileSync(0, 'utf8'))
} catch {
  process.exit(0)
}

const ti = input.tool_input ?? {}
const target = ti.file_path ?? ti.notebook_path ?? ti.path
if (!target) process.exit(0)

const base = path.basename(target.split('\\').join('/'))

if (base === '.env' || (base.startsWith('.env.') && base !== '.env.example')) {
  console.error(`차단: ${base} 은 비밀값 파일이라 편집하지 않는다. 값은 사람이 직접 넣는다 (.env.example만 편집 가능).`)
  process.exit(2)
}

process.exit(0)
