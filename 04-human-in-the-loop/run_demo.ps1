# ============================================================
# run_demo.ps1 - Project 11 complete oversight lifecycle, in Docker.
# Lia Surguladze, COMPE 475 Fall 2026
#
# Run from C:\k11 (with .env beside docker-compose.yml):
#     powershell -ExecutionPolicy Bypass -File run_demo.ps1
#
# Each scenario's output is shown on screen AND saved to evidence\NN_*.log
# Start from an empty database with:  docker compose down -v
# ============================================================

$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot
New-Item -ItemType Directory -Force -Path evidence | Out-Null
$global:Log = $null

function Section($file, $title) {
    $global:Log = "evidence\$file"
    $head = @("", ("=" * 70), "  $title", "  $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')", ("=" * 70))
    $head | Out-File -Encoding utf8 $global:Log
    $head | ForEach-Object { Write-Host $_ -ForegroundColor Cyan }
}

function Say($text) {
    "# $text" | Out-File -Encoding utf8 -Append $global:Log
    Write-Host "# $text" -ForegroundColor Yellow
}

# Run one supervised-Korra command in a fresh container and log it
function K {
    param([Parameter(ValueFromRemainingArguments = $true)] $Rest)
    $line = "PS> korra " + ($Rest -join " ")
    $line | Out-File -Encoding utf8 -Append $global:Log
    Write-Host $line -ForegroundColor Green
    $out = & docker compose run --rm -T korra @Rest 2>$null
    $code = $LASTEXITCODE
    $out | Out-File -Encoding utf8 -Append $global:Log
    $out | ForEach-Object { Write-Host $_ }
    "(exit $code)" | Out-File -Encoding utf8 -Append $global:Log
    Write-Host "(exit $code)" -ForegroundColor DarkGray
}

function Run($cmd) {
    "PS> $cmd" | Out-File -Encoding utf8 -Append $global:Log
    Write-Host "PS> $cmd" -ForegroundColor Green
    $out = Invoke-Expression "$cmd 2>&1" | ForEach-Object { "$_" }
    $out | Out-File -Encoding utf8 -Append $global:Log
    $out | ForEach-Object { Write-Host $_ }
}

function LatestId {
    $id = & docker compose run --rm -T korra pending --latest-id 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $id) { Say "WARNING: Korra did not pause (no pending decision)."; return "" }
    return ($id | Select-Object -Last 1).Trim()
}

# ------------------------------------------------------------
Section "00_build.log" "BUILD AND START (db healthy before korra runs)"
Run "docker compose up -d --build --wait db"
Run "docker compose build korra"
Run "docker compose ps"

# ------------------------------------------------------------
Section "01_interrupt_paused_state.log" "S2: INTERRUPT BEFORE THE PROTECTED ACTION + CHECKPOINTED STATE"
Say "Student asks Korra to add a student. Korra proposes save_student_record; approval_gate interrupts."
K ask --thread demo-approve --user student "Please add a student: Ana Lopez, ana@sdsu.edu, Computer Engineering, 3.6, 2026-10-26"
$A = LatestId
Say "The pending decision is listed with its stable ID ($A)."
K pending
Say "Nothing was written while approval is pending (no Ana Lopez in the table)."
K students
Say "The thread's checkpoint: next node is approval_gate (paused)."
K history --thread demo-approve
Say "Sending another message on the paused thread does NOT continue it."
K ask --thread demo-approve --user student "hello, are you done?"

# ------------------------------------------------------------
Section "02_invalid_decisions.log" "S3: DECISION VALIDATION AND AUTHORIZATION"
Say "Unauthorized reviewer"
K decide $A approve --by random.user
Say "Invalid decision value"
K decide $A maybe --by lia.surguladze
Say "Unknown decision ID"
K decide D-000000000000 approve --by lia.surguladze
Say "Still pending after all three refusals"
K pending

# ------------------------------------------------------------
Section "03_approve_resume_once.log" "S3: APPROVE -> RESUME FROM CHECKPOINT -> ACTION RUNS EXACTLY ONCE"
K decide $A approve --by lia.surguladze --reason "details verified"
Say "A second approval of the same decision is refused (duplicate / stale)."
K decide $A approve --by prof.nunez
Say "Ana Lopez appears exactly once."
K students
K history --thread demo-approve

# ------------------------------------------------------------
Section "04_reject.log" "S3: REJECT -> NOTHING SAVED, KORRA EXPLAINS"
K ask --thread demo-reject --user student "Please add a student: Ben Ruiz, ben@sdsu.edu, Physics, 3.1, 2026-10-26"
$B = LatestId
K decide $B reject --by prof.nunez --reason "not a registered applicant"
K students

# ------------------------------------------------------------
Section "05_revise.log" "S3: REVISE -> REVIEWER CORRECTS VALUES, THEN SAVE RUNS ONCE"
K ask --thread demo-revise --user student "Please add a student: Cara Kim, cara@sdsu.edu, Mathematics, 3.2, 2026-10-26"
$C = LatestId
Say "Invalid revisions are refused and the decision stays pending."
K decide $C revise --by lia.surguladze --set gpa=9
K decide $C revise --by lia.surguladze --set color=red
Say "Valid revision: GPA 3.2 -> 3.7 and major corrected."
K decide $C revise --by lia.surguladze --set gpa=3.7 --set "major=Applied Mathematics" --reason "transcript shows 3.7"
K students

# ------------------------------------------------------------
Section "06_cancel.log" "S3: CANCEL BY THE REQUESTER -> WORKFLOW TERMINATES"
K ask --thread demo-cancel --user dana "Please add a student: Dana Park, dana@sdsu.edu, Biology, 3.3, 2026-10-26"
$D = LatestId
K decide $D cancel --by dana --reason "entered by mistake"
K history --thread demo-cancel

# ------------------------------------------------------------
Section "07_restart_pending_preserved.log" "S4: RESTART WITH THE PENDING DECISION PRESERVED"
K ask --thread demo-restart --user student "Please add a student: Finn Oak, finn@sdsu.edu, History, 3.4, 2026-10-26"
$F = LatestId
Say "Destroy every container (the named volume is kept) ..."
Run "docker compose down"
Run "docker compose ps -a"
Say "... and start a brand-new database container on the same volume."
Run "docker compose up -d --wait db"
Run "docker compose logs db --tail 20"
Say "The decision $F is still pending after the restart."
K pending
K decide $F approve --by lia.surguladze --reason "approved after restart"
K students

# ------------------------------------------------------------
Section "08_timeout.log" "S4: TIMEOUT -> TREATED AS REJECT, LATE APPROVAL REFUSED"
K ask --thread demo-timeout --user student "Please add a student: Eli Moss, eli@sdsu.edu, Chemistry, 3.0, 2026-10-26"
$E = LatestId
Say "Waiting 10 seconds with a 5-second timeout for this run ..."
Start-Sleep -Seconds 10
$env:HITL_TIMEOUT_SECONDS = "5"
K sweep
Remove-Item Env:HITL_TIMEOUT_SECONDS
Say "A late approval is refused: the decision already timed out."
K decide $E approve --by lia.surguladze
K students

# ------------------------------------------------------------
Section "09_audit_no_secrets.log" "S4: AUDIT LOG + SECRET CHECK"
K audit --check-secrets
Say "The image's environment holds no key or password:"
Run "docker image inspect korra11-hitl --format '{{json .Config.Env}}'"

Write-Host ""
Write-Host "Demo complete. Logs are in $PSScriptRoot\evidence" -ForegroundColor Cyan
