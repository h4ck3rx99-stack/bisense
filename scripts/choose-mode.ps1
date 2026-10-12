# Decides, at start-up, whether BISense runs ONLINE (Groq) or LOCAL (Ollama + Whisper on this computer),
# and writes the matching settings as `set NAME=VALUE` lines to a .cmd file that start-bisense.bat runs.
# Environment variables override .env for this run only; .env itself is never changed.
#
#   online : Groq answers (and its Whisper for speech). If Ollama is installed, it is set as the backup, so
#            BISense switches to it by itself when Groq fails or its free daily allowance runs out.
#   local  : no internet / Groq unreachable / no key -> Ollama answers, local Whisper transcribes.
#            Without Ollama: answers show the official passages verbatim (no AI summary).
#
# Usage: powershell -File scripts\choose-mode.ps1 -Out <file.cmd> [-Mode auto|online|local]
param(
  [Parameter(Mandatory = $true)][string]$Out,
  [ValidateSet("auto", "online", "local")][string]$Mode = "auto"
)
$ErrorActionPreference = "SilentlyContinue"
$root = Split-Path -Parent $PSScriptRoot
$lines = New-Object System.Collections.Generic.List[string]
function Say($text) { Write-Host "  $text" }
function SetVar($name, $value) { $lines.Add("set `"$name=$value`"") }

# --- read .env (only what we need; values are never printed) ------------------------------------------
$envFile = @{}
if (Test-Path "$root\.env") {
  foreach ($line in Get-Content "$root\.env") {
    if ($line -match '^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$') { $envFile[$Matches[1]] = $Matches[2].Trim('"') }
  }
}
$baseUrl = $envFile["LLM_BASE_URL"]
$key = $envFile["LLM_API_KEY"]

# --- is the online AI (Groq) reachable with this key? ------------------------------------------------
$online = $false
if ($Mode -ne "local" -and $baseUrl -and $key -and $baseUrl -notmatch "localhost|127\.0\.0\.1") {
  try {
    $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 6 -Headers @{ Authorization = "Bearer $key" } "$($baseUrl.TrimEnd('/'))/models"
    $online = ($r.StatusCode -eq 200)
  } catch {
    $code = $_.Exception.Response.StatusCode.value__
    if ($code -eq 401 -or $code -eq 403) { Say "[!] The AI key in .env was rejected (HTTP $code). Check LLM_API_KEY." }
  }
}
if ($Mode -eq "online" -and -not $online) { Say "[!] Online mode was requested but the AI service is not reachable; using local mode." }

# --- local AI (Ollama): find it, start it, pick a model ---------------------------------------------------
$ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source
if (-not $ollama -and (Test-Path "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe")) { $ollama = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe" }
$localModel = $null
if ($ollama) {
  $up = $false
  try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "http://127.0.0.1:11434/api/tags" | Out-Null; $up = $true } catch {}
  if (-not $up) {
    $env:OLLAMA_CONTEXT_LENGTH = "8192"  # BISense prompts are ~3k tokens; the default 4096 can cut them
    Start-Process -FilePath $ollama -ArgumentList "serve" -WindowStyle Hidden
    for ($i = 0; $i -lt 20 -and -not $up; $i++) {
      Start-Sleep -Milliseconds 750
      try { Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 "http://127.0.0.1:11434/api/tags" | Out-Null; $up = $true } catch {}
    }
  }
  if ($up) {
    try {
      $names = (Invoke-RestMethod -TimeoutSec 4 "http://127.0.0.1:11434/api/tags").models | ForEach-Object { $_.name }
      # LLM_FALLBACK_MODEL in .env wins; otherwise the fast small model first (measured on a 2026 laptop:
      # llama3.2 ~6 s for a short answer, qwen3:8b ~70 s because it does not fit in the GPU's memory).
      $wanted = @($envFile["LLM_FALLBACK_MODEL"], "llama3.2", "llama3.2:latest", "qwen3:8b") | Where-Object { $_ }
      $localModel = $wanted | Where-Object { $names -contains $_ } | Select-Object -First 1
      if (-not $localModel -and $names) { $localModel = $names | Select-Object -First 1 }
    } catch {}
  }
}

# --- decide ---------------------------------------------------------------------------------------------
if ($online -and $Mode -ne "local") {
  Say "Mode: ONLINE - answers by $($envFile['LLM_MODEL']) (Groq), speech by Groq Whisper."
  if ($localModel) {
    SetVar "LLM_FALLBACK_BASE_URL" "http://localhost:11434/v1"
    SetVar "LLM_FALLBACK_MODEL" $localModel
    Say "Backup: $localModel on this computer (Ollama) takes over if Groq fails or its daily limit is reached."
  } else {
    Say "Backup: none for AI answers (install Ollama and run: ollama pull qwen3:8b). If Groq fails, answers show the sources verbatim."
  }
  Say "Speech switches to Whisper on this computer if Groq speech fails (English, Hindi)."
} else {
  SetVar "STT_PROVIDER" "local"
  if ($localModel) {
    SetVar "LLM_PROVIDER" "openai_compatible"
    SetVar "LLM_BASE_URL" "http://localhost:11434/v1"
    SetVar "LLM_MODEL" $localModel
    SetVar "LLM_ALT_MODEL" $localModel
    SetVar "TRANSLATION_MODEL" $localModel
    SetVar "LLM_FALLBACK_BASE_URL" "http://localhost:11434/v1"
    SetVar "LLM_FALLBACK_MODEL" $localModel
    SetVar "LLM_TIMEOUT_S" "60"
    Say "Mode: LOCAL - answers by $localModel on this computer (Ollama), speech by Whisper on this computer."
  } else {
    SetVar "LLM_PROVIDER" "none"
    Say "Mode: LOCAL without an AI model - answers show the official sources verbatim (no AI summary)."
    if ($ollama) { Say "Tip: download a local model once with internet:  ollama pull qwen3:8b" }
    else { Say "Tip: for AI answers offline, install Ollama (https://ollama.com) and run: ollama pull qwen3:8b" }
  }
  Say "Read-aloud uses the voices installed on this computer."
}
Set-Content -Path $Out -Value ($lines -join "`r`n") -Encoding ASCII
