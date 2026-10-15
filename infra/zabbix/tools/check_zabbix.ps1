# DejaFix Zabbix 점검 - 더블클릭이 아니라 PowerShell에서 실행:
#   powershell -ExecutionPolicy Bypass -File C:\Users\403\Documents\DejaFix\infra\zabbix\tools\check_zabbix.ps1
# 확인 순서: Docker 컨테이너 -> 에이전트 서비스 -> 서버 API -> 에이전트 연결 + CPU/MEM/DISK/NET 최신 값 -> 열린 장애
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$env:PYTHONIOENCODING = 'utf-8'
$hostName = 'DESKTOP-4V9JO99'
$secrets = 'C:\Users\403\host-setup\zabbix-secrets.json'
$py = 'C:\Users\403\miniforge3\envs\dev\python.exe'
$docker = 'C:\Program Files\Docker\Docker\resources\bin\docker.exe'
function Show($ok, $msg) { if ($ok) { Write-Host "[OK]   $msg" -ForegroundColor Green } else { Write-Host "[FAIL] $msg" -ForegroundColor Red } }

Write-Host "== 1. Zabbix 서버 컨테이너 (Docker)"
$ps = & $docker ps --filter "name=dejafix-zabbix" --format "{{.Names}} {{.Status}}" 2>&1
$up = @($ps | Where-Object { $_ -match ' Up ' }).Count
Show ($up -eq 3) "실행 중 컨테이너 $up/3"; $ps | ForEach-Object { "       $_" }

Write-Host "== 2. 에이전트"
$svc = Get-Service 'Zabbix Agent*' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($svc) {
  $path = (Get-CimInstance Win32_Service -Filter "Name='$($svc.Name)'").PathName
  $conf = [regex]::Match($path, '--config "([^"]+)"').Groups[1].Value
  $ver = (Get-Item ([regex]::Match($path, '^"([^"]+)"').Groups[1].Value)).VersionInfo.ProductVersion
  $sa = (Get-Content $conf -ErrorAction SilentlyContinue | Where-Object { $_ -match '^\s*ServerActive=' }) -replace '^\s*ServerActive=', ''
  $saOk = $sa -match '^[A-Za-z0-9\-]+(\.[A-Za-z0-9\-]+)+(:\d+)?$|^\[.*\]|:\d+$' 
  Show ($svc.Status -eq 'Running' -and $saOk) ("설치된 서비스 '$($svc.Name)' $ver = $($svc.Status), ServerActive=$sa" + $(if (-not $saOk) { "  <- 서버 주소 형식이 아님(값이 잘림?) → 액티브 수집 실패" } else { "" }))
  # 버전: 에이전트 <= 서버 (공식 호환 규칙). 서버 주소는 conf의 ServerActive에서 읽는다.
  $srv = ($sa -split ',')[0] -replace ':\d+$', ''
  $sv = $null
  foreach ($u in @("http://$srv/zabbix/api_jsonrpc.php", "http://$srv/api_jsonrpc.php")) {
    try { $sv = (Invoke-RestMethod -Uri $u -Method Post -ContentType 'application/json-rpc' -Body '{"jsonrpc":"2.0","method":"apiinfo.version","params":{},"id":1}' -TimeoutSec 5).result; if ($sv) { break } } catch {}
  }
  if ($sv) {
    $agentMm = [version](($ver -split '\.')[0..1] -join '.'); $serverMm = [version](($sv -split '\.')[0..1] -join '.')
    Show ($agentMm -le $serverMm) ("버전: 에이전트 $ver / 대상 서버 $sv" + $(if ($agentMm -gt $serverMm) { "  <- 에이전트가 서버보다 새 버전(미지원)" } else { "" }))
  } else { Write-Host "[?]    대상 서버 API 버전 확인 불가 (웹 경로가 다르거나 접속 불가)" }
  # 마지막 액티브 상태: 에이전트 로그 끝에서 판단
  $logf = (Get-Content $conf -ErrorAction SilentlyContinue | Where-Object { $_ -match '^\s*LogFile=' }) -replace '^\s*LogFile=', ''
  # 마지막 재시작 이후 줄만 보고, 마지막 오류가 마지막 복구보다 뒤면 FAIL
  $lines = @(Get-Content $logf -Tail 300 -ErrorAction SilentlyContinue)
  $from = 0; for ($i = 0; $i -lt $lines.Count; $i++) { if ($lines[$i] -match 'started \[main process\]') { $from = $i } }
  $err = $null; $ok = $null
  for ($i = $from; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match 'not found|Unable to connect|Unable to send|rejected|cannot connect') { $err = $i }
    elseif ($lines[$i] -match 'working again|are active again') { $ok = $i }
  }
  if ($null -eq $err -or ($null -ne $ok -and $ok -gt $err)) { Show $true "액티브 연결 오류 없음 (마지막 재시작 이후, 로그 $logf)" }
  elseif ($lines[$err] -match 'not found') { Show $false "대상 서버가 호스트를 모름: $($lines[$err].Trim())  <- 서버에 호스트 '$hostName' 등록 필요(대소문자 일치)" }
  else { Show $false "액티브 연결 문제: $($lines[$err].Trim())" }
} else { Show $false "설치된 Zabbix 에이전트 서비스 없음" }
$dash = [bool](Get-NetTCPConnection -State Listen -LocalPort 10060 -ErrorAction SilentlyContinue)
Show $dash "대시보드 수집용 Agent 2 (127.0.0.1:10060) 실행 = $dash  (꺼져 있으면 start_dashboard.ps1)"
Write-Host "== 3. 서버 API"
try {
  $v = (Invoke-RestMethod -Uri http://127.0.0.1:8080/api_jsonrpc.php -Method Post -ContentType 'application/json-rpc' -Body '{"jsonrpc":"2.0","method":"apiinfo.version","params":{},"id":1}' -TimeoutSec 10).result
  Show ([bool]$v) "apiinfo.version = $v"
} catch { Show $false "API 응답 없음: $($_.Exception.Message)" }

Write-Host "== 4. 에이전트 연결 + 핵심 지표 (Zabbix API, 읽기 전용 토큰)"
$tmp = Join-Path $env:TEMP "dejafix-core-metrics.txt"; cmd /c "`"$py`" -I `"$(Join-Path $PSScriptRoot "core_metrics.py")`" --host $hostName --secrets `"$secrets`" > `"$tmp`" 2>&1"; Get-Content $tmp -Encoding UTF8 | ForEach-Object { Write-Host $_ }
Write-Host ""
Write-Host "웹에서 보기: http://127.0.0.1:8080 -> Monitoring > Latest data -> Hosts: $hostName (Admin 비밀번호는 $secrets)"
