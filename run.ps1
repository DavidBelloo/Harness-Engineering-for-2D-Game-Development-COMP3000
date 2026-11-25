# Make a game. Used by run.bat:
#   run.bat "a ghost dodging falling pumpkins"        (opens the game in the browser when done)
#   run.bat                                           (asks for the idea)
#   run.bat --batch prompts\benchmark.txt             (benchmark: writes output\benchmark_*.md)
#   run.bat "idea" --skip-art --no-music              (any harness.py option works)
# Starts Ollama if it is not running, then runs harness.py inside the project's Python environment.
$ErrorActionPreference = "Continue"     # native tools write progress to stderr; errors are checked explicitly
Set-Location -LiteralPath $PSScriptRoot
$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"

foreach ($dir in @((Join-Path $env:USERPROFILE ".local\bin"), (Join-Path $env:LOCALAPPDATA "Programs\Ollama"))) {
    if ((Test-Path -LiteralPath $dir) -and (($env:Path -split ";") -notcontains $dir)) { $env:Path = "$dir;$env:Path" }
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "uv not found - run setup.bat first." -ForegroundColor Red; exit 1
}

function Test-Ollama {
    try { Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3 -ErrorAction Stop | Out-Null; return $true } catch { return $false }
}
if (-not (Test-Ollama)) {
    $ollama = Get-Command ollama -ErrorAction SilentlyContinue
    if (-not $ollama) { Write-Host "Ollama not found - run setup.bat first." -ForegroundColor Red; exit 1 }
    Write-Host "Starting Ollama..."
    Start-Process -FilePath $ollama.Source -ArgumentList "serve" -WindowStyle Hidden
    for ($i = 0; $i -lt 30 -and -not (Test-Ollama); $i++) { Start-Sleep -Seconds 1 }
}

$harnessArgs = @($args)
if ($harnessArgs.Count -eq 0) {
    $idea = Read-Host "Describe your game in one sentence"
    if (-not $idea) { exit 0 }
    $harnessArgs = @($idea)
}
if (($harnessArgs -notcontains "--batch") -and ($harnessArgs -notcontains "--open")) { $harnessArgs += "--open" }

& uv run python harness.py @harnessArgs
exit $LASTEXITCODE
