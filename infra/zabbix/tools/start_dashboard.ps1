# DejaFix 핵심 지표 대시보드 실행 (관리자 권한 불필요) - 저장소 루트에서:
#   powershell -ExecutionPolicy Bypass -File infra\zabbix\tools\start_dashboard.ps1 [-Remote <Zabbix API URL>] [-HostName <이름>] [-NoBrowser]
#
# 두 가지 방식 (자세한 설명: infra\zabbix\README.md "대시보드 보기")
#   로컬 방식(기본): 1) Docker 로컬 Zabbix 7.0.31 서버(127.0.0.1:18080)  2) 수집용 Agent 2(사용자 모드, 127.0.0.1:10060)
#                    3) 대시보드(127.0.0.1:18090)  4) 브라우저
#   원격 방식(-Remote): Docker·에이전트 없이 팀 Zabbix 서버를 바로 조회하는 대시보드만 띄운다.
# 토큰: 환경 변수 ZABBIX_API_TOKEN, 없으면 -Secrets 파일("api_token"). 토큰은 대시보드 서버에만 있고 브라우저로 가지 않는다.
# 이미 떠 있는 것은 건너뛴다. 설치된 "Zabbix Agent" 서비스(팀 서버용)는 건드리지 않는다.
param(
  [string]$Remote = '',
  [string]$HostName = $env:COMPUTERNAME,
  [string]$Secrets = (Join-Path $HOME 'host-setup\zabbix-secrets.json'),
  [string]$Python = 'python',
  [string]$AgentExe = (Join-Path $HOME 'zabbix-agent2\portable\bin\zabbix_agent2.exe'),
  [string]$AgentConf = (Join-Path $HOME 'zabbix-agent2\local-dashboard\zabbix_agent2.conf'),
  [int]$WebPort = 18080,
  [int]$DashboardPort = 18090,
  [switch]$NoBrowser
)
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$server = Join-Path $PSScriptRoot 'dashboard\server.py'
$compose = Join-Path (Split-Path $PSScriptRoot) 'local-server'
$docker = (Get-Command docker -ErrorAction SilentlyContinue).Source
if (-not $docker) { $docker = Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe' }

function Listening($port) { [bool](Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) }

if ($Remote) {
  $url = $Remote
  Write-Host "== 원격 방식: $url 조회 (Docker·수집용 에이전트는 건너뜀)"
} else {
  $url = "http://127.0.0.1:$WebPort/api_jsonrpc.php"
  Write-Host '== 1. 로컬 Zabbix 서버 (Docker)'
  & $docker version --format '{{.Server.Version}}' *> $null
  if ($LASTEXITCODE -ne 0) {
    Write-Host '   Docker 엔진이 꺼져 있어 Docker Desktop을 켭니다 (최대 2분 대기)'
    Start-Process (Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe')
    for ($i = 0; $i -lt 40; $i++) { Start-Sleep 3; $v = (& $docker version --format '{{.Server.Version}}' 2>$null); if ($v -match '^\d') { break } }
  }
  Push-Location $compose; & $docker compose up -d 2>&1 | Select-Object -Last 3 | ForEach-Object { "   $_" }; Pop-Location
  for ($i = 0; $i -lt 40; $i++) {
    try { $r = Invoke-RestMethod -Uri $url -Method Post -ContentType 'application/json-rpc' -Body '{"jsonrpc":"2.0","method":"apiinfo.version","params":{},"id":1}' -TimeoutSec 5; if ($r.result) { break } } catch {}
    Start-Sleep 3
  }
  Write-Host "   API: $($r.result)"

  Write-Host '== 2. 수집용 Agent 2 (127.0.0.1:10060)'
  if (Listening 10060) { Write-Host '   이미 실행 중' }
  elseif ((Test-Path $AgentExe) -and (Test-Path $AgentConf)) { Start-Process -FilePath $AgentExe -ArgumentList @('-c', "`"$AgentConf`"", '-f') -WindowStyle Hidden; Start-Sleep 3; Write-Host "   시작: $(Listening 10060)" }
  else { Write-Host "   건너뜀: 에이전트 파일 없음 ($AgentExe / $AgentConf) - README의 로컬 방식 준비 참고" }
}

Write-Host "== 대시보드 (127.0.0.1:$DashboardPort, 호스트 $HostName)"
if (Listening $DashboardPort) { Write-Host '   이미 실행 중' }
else {
  $dashArgs = @('-I', "`"$server`"", '--url', $url, '--host', $HostName, '--port', $DashboardPort)
  if (-not $env:ZABBIX_API_TOKEN) {
    if (Test-Path $Secrets) { $dashArgs += @('--secrets', "`"$Secrets`"") }
    else { Write-Host '   토큰 없음: $env:ZABBIX_API_TOKEN 을 설정하거나 -Secrets 로 파일을 지정하세요'; exit 1 }
  }
  Start-Process -FilePath $Python -ArgumentList $dashArgs -WindowStyle Hidden; Start-Sleep 2; Write-Host "   시작: $(Listening $DashboardPort)"
}

Write-Host "== 브라우저: http://127.0.0.1:$DashboardPort"
if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$DashboardPort/" }
Write-Host "끄기: $DashboardPort 포트의 python 프로세스 종료, Get-Process zabbix_agent2 | Stop-Process, infra\zabbix\local-server 에서 docker compose stop"
