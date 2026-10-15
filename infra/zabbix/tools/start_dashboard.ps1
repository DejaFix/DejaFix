# DejaFix 핵심 지표 대시보드 실행 (관리자 권한 불필요)
#   powershell -ExecutionPolicy Bypass -File C:\Users\403\Documents\DejaFix\infra\zabbix\tools\start_dashboard.ps1
# 1) Docker Zabbix 7.0.31 서버  2) 수집용 Agent 2(사용자 모드, 127.0.0.1:10060)  3) 대시보드(127.0.0.1:8090)  4) 브라우저
# 이미 떠 있는 것은 건너뛴다. 설치된 "Zabbix Agent" 서비스(팀 서버용)는 건드리지 않는다.
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$docker = 'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
$agent  = 'C:\Users\403\zabbix-agent2\portable\bin\zabbix_agent2.exe'
$agentConf = 'C:\Users\403\zabbix-agent2\local-dashboard\zabbix_agent2.conf'
$py = 'C:\Users\403\miniforge3\envs\dev\python.exe'
$server = Join-Path $PSScriptRoot 'dashboard\server.py'
$compose = Join-Path (Split-Path $PSScriptRoot) 'local-server'

function Listening($port) { [bool](Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) }

Write-Host '== 1. Zabbix 서버 (Docker)'
& $docker version --format '{{.Server.Version}}' *> $null
if ($LASTEXITCODE -ne 0) {
  Write-Host '   Docker 엔진이 꺼져 있어 Docker Desktop을 켭니다 (최대 2분 대기)'
  Start-Process 'C:\Program Files\Docker\Docker\Docker Desktop.exe'
  for ($i = 0; $i -lt 40; $i++) { Start-Sleep 3; $v = (& $docker version --format '{{.Server.Version}}' 2>$null); if ($v -match '^\d') { break } }
}
Push-Location $compose; & $docker compose up -d 2>&1 | Select-Object -Last 3 | ForEach-Object { "   $_" }; Pop-Location
for ($i = 0; $i -lt 40; $i++) {
  try { $r = Invoke-RestMethod -Uri http://127.0.0.1:8080/api_jsonrpc.php -Method Post -ContentType 'application/json-rpc' -Body '{"jsonrpc":"2.0","method":"apiinfo.version","params":{},"id":1}' -TimeoutSec 5; if ($r.result) { break } } catch {}
  Start-Sleep 3
}
Write-Host "   API: $($r.result)"

Write-Host '== 2. 수집용 Agent 2 (127.0.0.1:10060)'
if (Listening 10060) { Write-Host '   이미 실행 중' }
else { Start-Process -FilePath $agent -ArgumentList @('-c', "`"$agentConf`"", '-f') -WindowStyle Hidden; Start-Sleep 3; Write-Host "   시작: $(Listening 10060)" }

Write-Host '== 3. 대시보드 (127.0.0.1:8090)'
if (Listening 8090) { Write-Host '   이미 실행 중' }
else { Start-Process -FilePath $py -ArgumentList @('-I', "`"$server`"") -WindowStyle Hidden; Start-Sleep 2; Write-Host "   시작: $(Listening 8090)" }

Write-Host '== 4. 브라우저 열기: http://127.0.0.1:8090'
Start-Process 'http://127.0.0.1:8090/'
Write-Host '끄기: Get-Process zabbix_agent2 | Stop-Process; 8090 포트의 python 프로세스 종료; infra\zabbix\local-server 에서 docker compose stop'
