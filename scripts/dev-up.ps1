# DejaFix 로컬 기동 (compose 없이, 탈출 규칙 3 "로컬 프로세스 데모"용)
# MCP(:8200) -> Agent(:8100) -> Scheduler -> Backend(:8000) -> Frontend(:5173) 순서로 띄우고 각 /healthz 를 확인한다.
# - .env 는 scripts/run_with_env.py 가 python-dotenv 로 읽는다(값은 출력하지 않음). python-dotenv 는 서비스 패키지 의존성이 아니라 `uv run --with python-dotenv` 로 붙인다(빈 .venv 대비). 이 스크립트가 넘기는 환경 변수가 .env 보다 우선.
# - 이미 쓰는 포트가 있으면 그 서비스는 띄우지 않고 실패로 보고한다(떠 있는 프로세스를 끄지 않음).
# - 띄운 프로세스 PID 는 <LogDir>\dev-up.pids.json 에 남긴다 -> scripts/dev-down.ps1 이 그 PID 만 종료.
#
# 사용 (저장소 루트에서):
#   powershell -ExecutionPolicy Bypass -File scripts\dev-up.ps1                 # 목 모드(ZABBIX_MOCK=true), 기본 포트
#   powershell -ExecutionPolicy Bypass -File scripts\dev-up.ps1 -Live           # 실서버 모드(.env 의 ZABBIX_MOCK 그대로)
#   powershell -ExecutionPolicy Bypass -File scripts\dev-up.ps1 -Seed           # data\*.db 가 없으면 시드부터
#   powershell -ExecutionPolicy Bypass -File scripts\dev-up.ps1 -Live -Kb      # RAG(mcp-kb :8300)도 같이. knowledge.db 가 없으면 색인 1회 (결정 017). 안 주면 MCP_KB_URL 을 건드리지 않아 RAG 꺼짐
#   powershell -ExecutionPolicy Bypass -File scripts\dev-up.ps1 -McpPort 18200 -AgentPort 18100 -BackendPort 18000 -FrontendPort 15173 -DataDir C:\tmp\dejafix-data
[CmdletBinding()]
param(
    [int]$McpPort = 8200,
    [int]$AgentPort = 8100,
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [int]$KbPort = 8300,
    [string]$DataDir = "",          # 비우면 .env 의 SHARED_DB_PATH·BACKEND_DB_PATH 를 그대로 쓴다
    [string]$LogDir = "",           # 기본: <저장소>\data\logs
    [int]$PollSec = 10,             # Scheduler INCIDENT_POLL_SEC (최소 5)
    [switch]$Live,                  # 주면 ZABBIX_MOCK 을 덮어쓰지 않는다
    [switch]$Seed,                  # shared.db·backend.db 가 없을 때만 시드 (있으면 건드리지 않음)
    [switch]$NoFrontend,
    [switch]$Kb,                    # 주면 mcp-kb(RAG)를 agent 보다 먼저 띄우고 Agent 에 MCP_KB_URL 을 넘긴다
    [int]$TimeoutSec = 90
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
if (-not $LogDir) { $LogDir = Join-Path $Root "data\logs" }
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$PidFile = Join-Path $LogDir "dev-up.pids.json"

function Test-PortBusy([int]$Port) {
    return [bool](Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
}

function Wait-Http([string]$Url, [int]$Timeout) {
    $deadline = (Get-Date).AddSeconds($Timeout)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
            if ($r.StatusCode -eq 200) { return $r.Content }
        } catch { }
        Start-Sleep -Milliseconds 700
    }
    return $null
}

# ---- 공통 환경 변수 (자식 프로세스가 물려받음, .env 보다 우선) ----
if (-not $Live) { $env:ZABBIX_MOCK = "true" }
$env:MCP_ZABBIX_HOST = "127.0.0.1"
$env:MCP_ZABBIX_PORT = "$McpPort"
$env:MCP_ZABBIX_URL = "http://127.0.0.1:$McpPort/mcp"
$env:AGENT_URL = "http://127.0.0.1:$AgentPort"
$env:INCIDENT_POLL_SEC = "$PollSec"
$env:PYTHONIOENCODING = "utf-8"
if ($DataDir) {
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
    $env:SHARED_DB_PATH = (Join-Path $DataDir "shared.db")
    $env:BACKEND_DB_PATH = (Join-Path $DataDir "backend.db")
}

# ---- 시드 (선택, 없을 때만) ----
if ($Seed) {
    $shared = if ($env:SHARED_DB_PATH) { $env:SHARED_DB_PATH } else { Join-Path $Root "data\shared.db" }
    if (Test-Path $shared) {
        Write-Host "[seed] $shared 가 이미 있어 시드를 건너뜀 (다시 하려면 백업 후 지우고 실행)"
    } else {
        Write-Host "[seed] 시드 넣는 중 -> $(Split-Path $shared)"
        & uv run --no-project --python 3.12 python -I (Join-Path $PSScriptRoot "seed_dev.py") (Split-Path $shared)
        if ($LASTEXITCODE -ne 0) { throw "시드 실패" }
    }
}

$results = @()

# ---- RAG (-Kb): 색인이 없으면 1회 만들고, 성공해야 Agent 에 MCP_KB_URL 을 넘긴다 ----
$kbReady = $false
if ($Kb) {
    $env:KB_ROOT = $Root
    if ($DataDir) { $env:KB_DB_PATH = (Join-Path $DataDir "knowledge.db") }
    $kbDb = if ($env:KB_DB_PATH) { $env:KB_DB_PATH } else { Join-Path $Root "data\knowledge.db" }
    if (Test-Path $kbDb) {
        Write-Host "[kb] $kbDb 가 이미 있어 색인을 건너뜀 (다시 만들려면 python -m dejafix_kb index 를 직접 실행)"
        $kbReady = $true
    } else {
        Write-Host "[kb] 색인 만드는 중 -> $kbDb"
        & uv run --with python-dotenv --package kb python scripts/run_with_env.py module dejafix_kb index | Out-Null
        if ($LASTEXITCODE -eq 0 -and (Test-Path $kbDb)) { $kbReady = $true }
        else { $results += [pscustomobject]@{ service = "mcp-kb"; status = "FAIL"; detail = "색인 실패 - RAG 없이 계속 (uv run ... python -m dejafix_kb index 를 직접 실행해 오류 확인)" } }
    }
    if ($kbReady) {
        $env:MCP_KB_HOST = "127.0.0.1"
        $env:MCP_KB_PORT = "$KbPort"
        $env:MCP_KB_URL = "http://127.0.0.1:$KbPort/mcp"
    }
}

$services = @(
    @{ name = "mcp-zabbix"; port = $McpPort; health = "http://127.0.0.1:$McpPort/healthz";
       args = @("run", "--with", "python-dotenv", "--package", "mcp-zabbix", "python", "scripts/run_with_env.py", "module", "mcp_zabbix") }
)
if ($kbReady) {
    # agent 가 기동 시 MCP_KB_URL 을 보므로 agent 보다 먼저
    $services += @{ name = "mcp-kb"; port = $KbPort; health = "http://127.0.0.1:$KbPort/healthz";
       args = @("run", "--with", "python-dotenv", "--package", "mcp-kb", "python", "scripts/run_with_env.py", "module", "mcp_kb") }
}
$services += @(
    @{ name = "agent"; port = $AgentPort; health = "http://127.0.0.1:$AgentPort/healthz";
       args = @("run", "--with", "python-dotenv", "--package", "agent", "python", "scripts/run_with_env.py", "asgi", "dejafix_agent.main:app", "$AgentPort") },
    @{ name = "scheduler"; port = 0; health = "";
       args = @("run", "--with", "python-dotenv", "--package", "scheduler", "python", "scripts/run_with_env.py", "module", "dejafix_scheduler") },
    @{ name = "backend"; port = $BackendPort; health = "http://127.0.0.1:$BackendPort/healthz";
       args = @("run", "--with", "python-dotenv", "--package", "backend", "python", "scripts/run_with_env.py", "asgi", "dejafix_backend.main:app", "$BackendPort") }
)

$started = @()
foreach ($s in $services) {
    if ($s.port -and (Test-PortBusy $s.port)) {
        $results += [pscustomobject]@{ service = $s.name; status = "SKIP"; detail = "포트 $($s.port) 이미 사용 중 (떠 있는 프로세스는 건드리지 않음)" }
        continue
    }
    $out = Join-Path $LogDir "$($s.name).log"
    $err = Join-Path $LogDir "$($s.name).err.log"
    $p = Start-Process -FilePath "uv" -ArgumentList $s.args -WorkingDirectory $Root -WindowStyle Hidden `
        -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
    $started += [pscustomobject]@{ service = $s.name; pid = $p.Id; port = $s.port }

    if ($s.health) {
        $body = Wait-Http $s.health $TimeoutSec
        if ($body) { $results += [pscustomobject]@{ service = $s.name; status = "OK"; detail = $body.Trim() } }
        else { $results += [pscustomobject]@{ service = $s.name; status = "FAIL"; detail = "$($s.health) 응답 없음 - $err 확인" } }
    } else {
        # Scheduler 는 포트가 없다: 첫 폴링 로그(poll_problems ok/실패)를 기다린다
        $deadline = (Get-Date).AddSeconds($TimeoutSec)
        $line = $null
        while ((Get-Date) -lt $deadline -and -not $line) {
            Start-Sleep -Milliseconds 700
            if ($p.HasExited) { break }
            $line = Select-String -Path $err, $out -Pattern "poll_problems" -ErrorAction SilentlyContinue | Select-Object -Last 1
        }
        if ($line -and $line.Line -match "poll_problems ok") { $results += [pscustomobject]@{ service = $s.name; status = "OK"; detail = $line.Line.Trim() } }
        elseif ($line) { $results += [pscustomobject]@{ service = $s.name; status = "FAIL"; detail = $line.Line.Trim() } }
        else { $results += [pscustomobject]@{ service = $s.name; status = "FAIL"; detail = "폴링 로그 없음(종료됨=$($p.HasExited)) - $err 확인" } }
    }
}

if (-not $NoFrontend) {
    if (Test-PortBusy $FrontendPort) {
        $results += [pscustomobject]@{ service = "frontend"; status = "SKIP"; detail = "포트 $FrontendPort 이미 사용 중" }
    } else {
        $env:VITE_MSW = "off"
        $env:DEV_API_TARGET = "http://127.0.0.1:$BackendPort"   # vite.config.ts 프록시 대상 (-BackendPort 와 맞춤)
        $out = Join-Path $LogDir "frontend.log"
        $err = Join-Path $LogDir "frontend.err.log"
        $p = Start-Process -FilePath "npm.cmd" -ArgumentList @("run", "dev", "--", "--port", "$FrontendPort", "--strictPort") `
            -WorkingDirectory (Join-Path $Root "frontend") -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err -PassThru
        $started += [pscustomobject]@{ service = "frontend"; pid = $p.Id; port = $FrontendPort }
        # Vite 는 localhost(IPv6 ::1)에만 바인딩하므로 127.0.0.1 이 아니라 localhost 로 확인
        if (Wait-Http "http://localhost:$FrontendPort/" $TimeoutSec) { $results += [pscustomobject]@{ service = "frontend"; status = "OK"; detail = "http://localhost:$FrontendPort (VITE_MSW=off, /api -> vite.config.ts 프록시)" } }
        else { $results += [pscustomobject]@{ service = "frontend"; status = "FAIL"; detail = "응답 없음 - $err 확인" } }
    }
}

# PID 기록 (이번에 띄운 것만 덧붙임)
$prev = @()
if (Test-Path $PidFile) { $prev = @(Get-Content $PidFile -Raw | ConvertFrom-Json | ForEach-Object { $_ }) }
ConvertTo-Json -InputObject @($prev + $started) | Set-Content -Path $PidFile -Encoding UTF8

$results | Format-Table -AutoSize | Out-String -Width 200 | Write-Host
Write-Host "로그: $LogDir   PID: $PidFile   종료: scripts\dev-down.ps1"
if ($results | Where-Object { $_.status -eq "FAIL" }) { exit 1 } else { exit 0 }
