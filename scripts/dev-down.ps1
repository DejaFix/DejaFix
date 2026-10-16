# scripts/dev-up.ps1 이 띄운 프로세스만 종료한다 (<LogDir>\dev-up.pids.json 의 PID, 자식 프로세스 포함).
# 다른 방법으로 띄운 서비스·다른 창은 건드리지 않는다. DB 파일은 지우지 않는다.
#   powershell -ExecutionPolicy Bypass -File scripts\dev-down.ps1 [-LogDir <dev-up 에 준 경로>]
[CmdletBinding()]
param([string]$LogDir = "")

$Root = Split-Path -Parent $PSScriptRoot
if (-not $LogDir) { $LogDir = Join-Path $Root "data\logs" }
$PidFile = Join-Path $LogDir "dev-up.pids.json"
if (-not (Test-Path $PidFile)) { Write-Host "PID 파일 없음: $PidFile (dev-up 으로 띄운 프로세스가 없음)"; exit 0 }

# PS 5.1 의 ConvertFrom-Json 은 배열을 원소 하나로 돌려주므로 파이프로 풀어서 받는다
$items = @(Get-Content $PidFile -Raw | ConvertFrom-Json | ForEach-Object { $_ })
$failed = @()
foreach ($it in $items) {
    $p = Get-Process -Id $it.pid -ErrorAction SilentlyContinue
    if (-not $p) { Write-Host "[$($it.service)] PID $($it.pid) 이미 종료"; continue }
    # uv·npm 은 자식(python·node)을 띄우므로 트리째 종료
    & taskkill.exe /T /F /PID $it.pid | Out-Null
    if ($LASTEXITCODE -ne 0) { $failed += $it; Write-Host "[$($it.service)] PID $($it.pid) 종료 실패" }
    else { Write-Host "[$($it.service)] PID $($it.pid) 종료" }
}
# 실패한 것이 있으면 PID 파일을 남겨 다시 실행할 수 있게 한다
if ($failed.Count) { ConvertTo-Json -InputObject @($failed) | Set-Content -Path $PidFile -Encoding UTF8 }
else { Remove-Item $PidFile -Force }
$left = @($items | Where-Object { $_.port -gt 0 } | Where-Object { Get-NetTCPConnection -LocalPort $_.port -State Listen -ErrorAction SilentlyContinue })
if ($left.Count) { Write-Host "아직 열려 있는 포트: $(($left | ForEach-Object { $_.port }) -join ', ')"; exit 1 }
Write-Host "dev-up 으로 띄운 서비스를 모두 종료했습니다."
exit 0
