param(
    [switch]$RunLiveDiscovery,
    [switch]$RunLiveHandoff,
    [switch]$AuditDeliverables
)

$ErrorActionPreference = "Stop"
$RepoRoot = (Get-Location).Path
$ArtifactPath = Join-Path $RepoRoot "artifacts\member_savings_balance.json"
$EvidenceRoot = Join-Path $RepoRoot "evidence"

$DiscoveryRun = "run_d37f9847c87c"
$ReplaySuccessRun = "run_05b560cca299"
$BusinessOutcomeRun = "run_a099316ecef6"
$HandoffRun = "run_3a9f88e34b09"
$HardFailureRun = "run_26d42264e4d2"

$script:PassCount = 0
$script:FailCount = 0
$script:SkipCount = 0

function Section($Name) {
    Write-Host ""
    Write-Host ("=" * 72) -ForegroundColor Cyan
    Write-Host $Name -ForegroundColor Cyan
    Write-Host ("=" * 72) -ForegroundColor Cyan
}
function Pass($Message) { $script:PassCount++; Write-Host "[PASS] $Message" -ForegroundColor Green }
function Fail($Message) { $script:FailCount++; Write-Host "[FAIL] $Message" -ForegroundColor Red }
function Skip($Message) { $script:SkipCount++; Write-Host "[SKIP] $Message" -ForegroundColor Yellow }
function Check($Condition, $Message) { if ($Condition) { Pass $Message } else { Fail $Message } }

function JsonFile($Path) {
    if (-not (Test-Path $Path)) { throw "Missing JSON file: $Path" }
    Get-Content $Path -Raw | ConvertFrom-Json
}

function Replay($MemberId) {
    $out = & python -m src.replay.cli --artifact $ArtifactPath --member-id $MemberId 2>&1
    $text = ($out | Out-String).Trim()
    if (-not $text.StartsWith("{")) { throw "Replay did not return JSON:`n$text" }
    $text | ConvertFrom-Json
}

function Ensure-MockBank {
    try {
        $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/" -UseBasicParsing -TimeoutSec 1
        if ($r.StatusCode -eq 200) { Pass "Mock bank is running"; return $null }
    } catch {}

    $python = (Get-Command python).Source
    $p = Start-Process -FilePath $python -ArgumentList "-m","src.mock_bank" -WorkingDirectory $RepoRoot -PassThru -WindowStyle Hidden

    for ($i=0; $i -lt 40; $i++) {
        try {
            $r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/" -UseBasicParsing -TimeoutSec 1
            if ($r.StatusCode -eq 200) { Pass "Acceptance test started mock bank"; return $p }
        } catch { Start-Sleep -Milliseconds 250 }
    }
    throw "Could not start mock bank"
}

$server = $null
try {
    Section "AGENTFORGE FINAL ACCEPTANCE TEST"
    Check (Test-Path "pyproject.toml") "Running from repository root"
    Check (Test-Path $ArtifactPath) "Capability artifact exists"
    Check (Test-Path "src\agent\cli.py") "Discovery CLI exists"
    Check (Test-Path "src\replay\cli.py") "Replay CLI exists"
    Check (Test-Path "src\handoff\manager.py") "Handoff manager exists"

    $server = Ensure-MockBank

    Section "3.1 GOAL-DRIVEN AGENT LOOP"
    $dResult = Join-Path $EvidenceRoot "$DiscoveryRun\result.json"
    $dEvents = Join-Path $EvidenceRoot "$DiscoveryRun\events.jsonl"
    Check (Test-Path $dResult) "Official discovery result exists"
    Check (Test-Path $dEvents) "Official discovery log exists"

    $d = JsonFile $dResult
    Check ($d.status -eq "success") "Genuine discovery succeeded"
    Check ($d.outputs.savings_balance -eq '$4,821.37') "Discovery extracted expected savings balance"
    $actions = @($d.steps | ForEach-Object { $_.decision.action })
    Check ($actions -contains "type") "Discovery performed TYPE"
    Check ($actions -contains "click") "Discovery performed CLICK"
    Check ($actions -contains "finish") "Discovery verified goal completion"
    Check ($d.steps[0].target.candidates.Count -ge 2) "Discovery stored fallback target candidates"

    if ($RunLiveDiscovery) {
        if (-not $env:OPENAI_API_KEY) {
            Fail "RunLiveDiscovery requested but OPENAI_API_KEY is missing"
        } else {
            $live = & python -m src.agent.cli --goal "Look up member 12345 and return their current savings balance" --target "http://127.0.0.1:8000" 2>&1
            $lt = ($live | Out-String)
            Check ($lt -match '"status":\s*"success"') "Fresh live LLM discovery succeeded"
            Check ($lt -match '\$4,821\.37') "Fresh live discovery returned expected value"
        }
    } else {
        Skip "Fresh paid LLM discovery not rerun; curated genuine discovery evidence verified"
    }

    Section "3.2 STRUCTURED ARTIFACT"
    $a = JsonFile $ArtifactPath
    Check ($a.schema_version -eq "1.0") "Artifact schema is versioned"
    Check ($a.capability.version -eq "1.0.0") "Capability is versioned"
    Check ($a.capability.id -eq "member_savings_balance") "Capability has stable ID"
    Check ($a.inputs.member_id.type -eq "string") "Typed member_id input exists"
    Check ($a.outputs.savings_balance.type -eq "string") "Typed savings_balance output exists"
    Check ($a.outputs.savings_balance.extractor.strategy -eq "table_cell") "Deterministic output extractor exists"
    Check ($a.steps.Count -eq 2) "Ordered reusable step list exists"
    Check ($a.steps[0].action -eq "type") "First step is TYPE"
    Check ($a.steps[1].action -eq "click") "Second step is CLICK"
    Check ($a.steps[0].value.kind -eq "parameter") "Discovery literal was parameterized"
    Check ($a.steps[0].value.name -eq "member_id") "TYPE step binds member_id"
    $artifactText = Get-Content $ArtifactPath -Raw
    Check (-not $artifactText.Contains('"12345"')) "Artifact does not hardcode discovery member ID"
    Check ($a.steps[0].target.candidates.Count -ge 2) "TYPE step has locator fallbacks"
    Check ($a.steps[1].target.candidates.Count -ge 2) "CLICK step has locator fallbacks"
    Check ($null -ne $a.success_checkpoint) "Success checkpoint exists"

    Section "FULL PYTEST SUITE"
    & pytest
    Check ($LASTEXITCODE -eq 0) "Full pytest suite passes"

    Section "3.3 DETERMINISTIC REPLAY"
    $savedKey = $env:OPENAI_API_KEY
    $savedModel = $env:OPENAI_MODEL
    Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue
    Remove-Item Env:OPENAI_MODEL -ErrorAction SilentlyContinue
    try {
        $s = Replay "67890"
        Check ($s.status -eq "success") "Replay succeeds for different member 67890"
        Check ($s.outputs.savings_balance -eq '$2,614.09') "Replay returns declared output"
        Check ($s.steps[0].checkpoint_passed) "TYPE checkpoint passes"
        Check ($s.steps[1].checkpoint_passed) "CLICK checkpoint passes"

        $b = Replay "99999"
        Check ($b.status -eq "business_outcome") "Not-found is a business outcome"
        Check ($b.code -eq "member_not_found") "Business outcome code is explicit"

        $recoverableCode = @'
import asyncio
from src.replay.engine import ReplayEngine, default_replay_policy, load_artifact
async def main():
    a = load_artifact("artifacts/member_savings_balance.json")
    r = await ReplayEngine(
        artifact=a,
        policy=default_replay_policy(a),
        headless=True,
        enable_handoff=False,
        checkpoint_timeout_ms=0,
    ).run({"member_id":"55555"})
    print(r.model_dump_json())
asyncio.run(main())
'@
        $rt = $recoverableCode | python -
        $r = (($rt | Out-String).Trim() | ConvertFrom-Json)
        Check ($r.status -eq "recoverable") "Known interstitial is recoverable"
        Check ($r.code -eq "known_interstitial") "Recoverable condition code is explicit"

        $f = Replay "77777"
        Check ($f.status -eq "failure") "Permission denial becomes hard failure"
        Check ($f.code -eq "checkpoint_failed") "Hard failure code is explicit"
        Check ($f.failed_step_id -eq "step_2_click") "Hard failure identifies failed step"
        Check ($f.expected_state.page_title -eq "Member Details") "Hard failure reports expected state"
        Check ($f.observed_state.page_title -eq "Permission Denied") "Hard failure reports observed state"
        Check (Test-Path (Join-Path $RepoRoot $f.evidence_path)) "Hard failure produced screenshot evidence"

        Pass "Replay path works with OPENAI_API_KEY removed"
    } finally {
        if ($null -ne $savedKey) { $env:OPENAI_API_KEY = $savedKey }
        if ($null -ne $savedModel) { $env:OPENAI_MODEL = $savedModel }
    }

    Section "3.4 SAFETY & POLICY"
    & pytest tests/test_policy_engine.py tests/test_redaction.py -q
    Check ($LASTEXITCODE -eq 0) "Allowlist, risk and redaction tests pass"
    $trackedEnv = (git ls-files -- ".env" | Out-String).Trim()
    Check ([string]::IsNullOrWhiteSpace($trackedEnv)) "Real .env is not tracked"
    $secretPattern = "s" + "k-"
    $secretMatches = (git grep -n $secretPattern -- . 2>$null | Out-String).Trim()
    Check ([string]::IsNullOrWhiteSpace($secretMatches)) "No obvious API secret pattern in tracked files"

    Section "3.5 EVIDENCE / OBSERVABILITY"
    foreach ($run in @($DiscoveryRun,$ReplaySuccessRun,$BusinessOutcomeRun,$HandoffRun,$HardFailureRun)) {
        Check (Test-Path (Join-Path $EvidenceRoot "$run\events.jsonl")) "$run has events.jsonl"
        Check (Test-Path (Join-Path $EvidenceRoot "$run\result.json")) "$run has result.json"
    }
    Check (Test-Path (Join-Path $EvidenceRoot "$HardFailureRun\failure_step_2_click_checkpoint.png")) "Curated failure screenshot exists"

    Section "3.6 HUMAN-IN-THE-LOOP HANDOFF"
    $he = Get-Content (Join-Path $EvidenceRoot "$HandoffRun\events.jsonl") -Raw
    foreach ($e in @("intervention_requested","control_transferred","human_action","control_returned","resume_validated","replay_completed")) {
        Check ($he.Contains('"' + $e + '"')) "Handoff evidence contains $e"
    }
    Check ($he.Contains('"human_action_count": 1')) "Handoff records one human action"
    Check ($he.Contains('"text": "Continue Session"')) "Handoff records Continue Session click"
    Check (Test-Path (Join-Path $EvidenceRoot "$HandoffRun\failure_step_2_click_intervention.png")) "Intervention screenshot exists"

    if ($RunLiveHandoff) {
        Write-Host "LIVE HANDOFF: when prompted, click Continue Session in the SAME Chromium session, then press Enter." -ForegroundColor Yellow
        & python -m src.replay.cli --artifact $ArtifactPath --member-id 55555 --headed --handoff
        Check ($LASTEXITCODE -eq 0) "Live handoff completed"
    } else {
        Skip "Live manual handoff not rerun; curated real handoff evidence verified"
    }

    Section "3.7 HETEROGENEITY & SCALE SEAMS"
    Check (Test-Path "src\surface\base.py") "Surface abstraction exists"
    Check (Test-Path "src\surface\browser.py") "Browser is a concrete surface adapter"
    Check (-not [string]::IsNullOrWhiteSpace($a.target.application_family)) "Artifact records application family"
    Check (-not [string]::IsNullOrWhiteSpace($a.target.surface_type)) "Artifact records surface type"


    # -------------------------------------------------------------------------
    # 8. Optional stretch: agent-facing capability API
    # -------------------------------------------------------------------------
    Section "8. OPTIONAL STRETCH: AGENT-FACING CAPABILITY API"

    Check (Test-Path "src\capability_api\app.py") "Capability API implementation exists"
    Check (Test-Path "tests\test_capability_api.py") "Capability API tests exist"

    & pytest tests/test_capability_api.py -q
    Check ($LASTEXITCODE -eq 0) "Capability catalog/invocation API tests pass"

    # Start a temporary local API process for a real HTTP catalog + invocation check.
    $apiPython = (Get-Command python).Source
    $apiProcess = Start-Process `
        -FilePath $apiPython `
        -ArgumentList "-m", "src.capability_api" `
        -WorkingDirectory $RepoRoot `
        -PassThru `
        -WindowStyle Hidden

    try {
        $apiReady = $false
        for ($i = 0; $i -lt 40; $i++) {
            try {
                $health = Invoke-RestMethod `
                    -Method Get `
                    -Uri "http://127.0.0.1:8010/health" `
                    -TimeoutSec 1
                if ($health.status -eq "ok") {
                    $apiReady = $true
                    break
                }
            }
            catch {
                Start-Sleep -Milliseconds 250
            }
        }

        Check $apiReady "Capability API starts on port 8010"

        if ($apiReady) {
            $catalogResponse = Invoke-RestMethod `
                -Method Get `
                -Uri "http://127.0.0.1:8010/v1/capabilities"

            $capability = @($catalogResponse.capabilities) |
                Where-Object { $_.id -eq "member_savings_balance" } |
                Select-Object -First 1

            Check ($null -ne $capability) "Agent can discover member_savings_balance by name"
            if ($null -ne $capability) {
                Check ($capability.input_schema.properties.member_id.type -eq "string") "Catalog exposes typed member_id input"
                Check ($capability.output_schema.properties.savings_balance.type -eq "string") "Catalog exposes typed savings_balance output"
                Check ($capability.tool_schema.type -eq "function") "Catalog exposes provider-neutral function/tool schema"
            }

            $invokeBody = @{
                arguments = @{
                    member_id = "67890"
                }
            } | ConvertTo-Json -Depth 5

            $invokeResult = Invoke-RestMethod `
                -Method Post `
                -Uri "http://127.0.0.1:8010/v1/capabilities/member_savings_balance/invoke" `
                -ContentType "application/json" `
                -Body $invokeBody

            Check ($invokeResult.status -eq "success") "Agent-facing API invokes capability successfully"
            Check ($invokeResult.capability_id -eq "member_savings_balance") "Invocation returns capability identity"
            Check ($invokeResult.outputs.savings_balance -eq '$2,614.09') "Invocation returns deterministic declared output"
        }
    }
    finally {
        Stop-Process -Id $apiProcess.Id -Force -ErrorAction SilentlyContinue
    }

    Section "6. DELIVERABLES"
    Check (Test-Path "README.md") "README.md exists"
    Check (Test-Path "REPORT.md") "REPORT.md exists"

    if ($AuditDeliverables) {
        $report = Get-Content "REPORT.md" -Raw
        foreach ($h in @(
            "Architecture",
            "Artifact schema",
            "Determinism & error handling",
            "Heterogeneity & multi-tenant",
            "Escalation & handoff",
            "Safety",
            "Cuts"
        )) {
            Check ($report.Contains($h)) "REPORT contains required heading: $h"
        }
        $readme = Get-Content "README.md" -Raw
        Check ($readme -match "OPENAI_API_KEY|API key") "README documents API key setup"
        Check ($readme -match "src\.agent\.cli") "README documents discovery command"
        Check ($readme -match "src\.replay\.cli") "README documents replay command"
    } else {
        Skip "Detailed README/REPORT wording audit deferred to Stage 12"
    }

    Section "FINAL RESULT"
    Write-Host "Passed : $script:PassCount" -ForegroundColor Green
    Write-Host "Failed : $script:FailCount" -ForegroundColor $(if ($script:FailCount -eq 0) {"Green"} else {"Red"})
    Write-Host "Skipped: $script:SkipCount" -ForegroundColor Yellow

    if ($script:FailCount -eq 0) {
        Write-Host "AGENTFORGE CORE ACCEPTANCE: PASS" -ForegroundColor Green
        exit 0
    } else {
        Write-Host "AGENTFORGE CORE ACCEPTANCE: FAIL" -ForegroundColor Red
        exit 1
    }
}
finally {
    if ($null -ne $server) {
        Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
    }
}
