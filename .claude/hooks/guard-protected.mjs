// PreToolUse 훅: contracts/ 와 .env 편집 시도를 차단한다.
// 차단하면 exit 2 + stderr 사유 (Claude에게 전달됨). 입력을 못 읽으면 막지 않는다.
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

const root = process.env.CLAUDE_PROJECT_DIR ?? input.cwd ?? process.cwd()
const rel = path.relative(root, path.resolve(root, target)).split(path.sep).join('/')
const base = path.posix.basename(rel)

if (rel === 'contracts' || rel.startsWith('contracts/')) {
  console.error(`차단: contracts/ 는 Claude Code로 편집하지 않는다 (${rel}). 계약 변경은 계약 소유자의 2인 승인 PR로 진행하고, 필요하면 PR 본문·LOG에 "계약 변경 제안"으로 남긴다.`)
  process.exit(2)
}

if (base === '.env' || (base.startsWith('.env.') && base !== '.env.example')) {
  console.error(`차단: ${rel} 은 비밀값 파일이라 편집하지 않는다. 값은 사람이 직접 넣는다 (.env.example만 편집 가능).`)
  process.exit(2)
}

process.exit(0)
