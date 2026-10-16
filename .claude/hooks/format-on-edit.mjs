// PostToolUse 훅: 편집한 파일 하나만 가볍게 포맷한다 (tsc·lint는 돌리지 않음).
// - frontend/ 의 ts·tsx·js·jsx·css·json·html → prettier (frontend devDependency에 있을 때만, 내려받지 않음)
// - *.py → uv run ruff format
// 포맷 실패는 작업을 막지 않는다. 항상 exit 0.
import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'

let input
try {
  input = JSON.parse(readFileSync(0, 'utf8'))
} catch {
  process.exit(0)
}

const target = input.tool_input?.file_path
if (!target) process.exit(0)

const root = process.env.CLAUDE_PROJECT_DIR ?? input.cwd ?? process.cwd()
const abs = path.resolve(root, target)
if (!existsSync(abs)) process.exit(0)
const rel = path.relative(root, abs).split(path.sep).join('/')
const ext = path.extname(abs).toLowerCase()

const run = (cmd, args, cwd) => {
  const r = spawnSync(cmd, args, { cwd, stdio: ['ignore', 'ignore', 'pipe'], shell: process.platform === 'win32', timeout: 30000 })
  if (r.status !== 0 && r.stderr?.length) console.error(`포맷 건너뜀 (${cmd}): ${r.stderr.toString().trim().split('\n')[0]}`)
}

const FRONTEND_EXT = new Set(['.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.css', '.json', '.html'])

if (rel.startsWith('frontend/') && FRONTEND_EXT.has(ext)) {
  const frontend = path.join(root, 'frontend')
  if (existsSync(path.join(frontend, 'node_modules', 'prettier'))) {
    run('npx', ['--no-install', 'prettier', '--write', '--log-level', 'warn', path.relative(frontend, abs)], frontend)
  }
} else if (ext === '.py') {
  run('uv', ['run', '--quiet', 'ruff', 'format', rel], root)
}

process.exit(0)
