# One-command setup for a fresh Windows PC with an NVIDIA GPU.
#   Double-click setup.bat  (or: powershell -ExecutionPolicy Bypass -File setup.ps1)
#
# Installs, per-user (no admin rights needed for any step):
#   uv      - Python package/version manager; it downloads Python 3.12 itself (no Python install needed)
#   Python packages from pyproject.toml, incl. PyTorch 2.7 for CUDA 12.8 (works on RTX 20/30/40/50 series)
#   Chromium for the automated game test (Edge is used if this fails)
#   Ollama  - runs the local language models
#   all AI models for this machine's hardware profile (16 GB GPU -> larger models)
# Then runs the pre-flight check. Safe to run again: finished steps are skipped.
#
# Options:  -SkipModels   do not download the AI models now (they download on first use instead)
param([switch]$SkipModels)

$ErrorActionPreference = "Continue"     # native tools write progress to stderr; errors are checked explicitly
$ProgressPreference = "SilentlyContinue"          # Invoke-WebRequest is very slow with the progress bar on
Set-Location -LiteralPath $PSScriptRoot
try { Start-Transcript -Path (Join-Path $PSScriptRoot "setup.log") -Append | Out-Null } catch { }

$env:HF_HUB_DISABLE_SYMLINKS_WARNING = "1"
$env:UV_HTTP_TIMEOUT = "600"
$Total = 7

function Step($n, $text) { Write-Host ""; Write-Host "[$n/$Total] $text" -ForegroundColor Cyan }
function Ok($text)   { Write-Host "  OK   $text" -ForegroundColor Green }
function Note($text) { Write-Host "  !    $text" -ForegroundColor Yellow }
function Fail($text) {
    Write-Host "  FAIL $text" -ForegroundColor Red
    Write-Host ""
    Write-Host "Setup stopped. Fix the problem above and run setup.bat again (finished steps are skipped)." -ForegroundColor Red
    Write-Host "Full log: $(Join-Path $PSScriptRoot 'setup.log')"
    try { Stop-Transcript | Out-Null } catch { }
    exit 1
}
function Add-ToPath($dir) {
    if ($dir -and (Test-Path -LiteralPath $dir) -and (($env:Path -split ";") -notcontains $dir)) { $env:Path = "$dir;$env:Path" }
}
function Test-Ollama {
    try { Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3 -ErrorAction Stop | Out-Null; return $true } catch { return $false }
}

Write-Host "Game Harness setup" -ForegroundColor White
Write-Host "Folder: $PSScriptRoot"

# ---------------------------------------------------------------------------------------------
Step 1 "NVIDIA GPU and driver"
$smi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if (-not $smi) {
    Note "nvidia-smi not found: no NVIDIA driver. Games can still be made with placeholder art (run.bat ... --skip-art)."
    Note "To use the GPU, install the latest driver from https://www.nvidia.com/Download/index.aspx and run setup.bat again."
} else {
    $line = (& nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits | Select-Object -First 1)
    $parts = $line -split ","
    $gpu = $parts[0].Trim(); $vram = [int]([double]$parts[1].Trim()); $driver = $parts[2].Trim()
    Ok ("{0}, {1:N0} GB VRAM, driver {2}" -f $gpu, ($vram / 1024), $driver)
    $major = [int](($driver -split "\.")[0])
    if ($major -lt 570) {
        Note "Driver $driver is too old for CUDA 12.8 (needs 570 or newer; RTX 50-series always needs it)."
        Note "Update it from https://www.nvidia.com/Download/index.aspx (needs admin), then run setup.bat again."
    }
    if ($vram -ge 14000) { Ok "16 GB-class GPU: the larger models will be used (high profile)" }
    else { Ok "8-12 GB GPU: the smaller models will be used (low profile)" }
}

# ---------------------------------------------------------------------------------------------
Step 2 "uv (installs Python and the packages)"
Add-ToPath (Join-Path $env:USERPROFILE ".local\bin")
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    Write-Host "  installing uv..."
    try { Invoke-RestMethod -Uri "https://astral.sh/uv/install.ps1" -ErrorAction Stop | Invoke-Expression }
    catch { Fail "Could not install uv: $($_.Exception.Message). Check the internet connection." }
    Add-ToPath (Join-Path $env:USERPROFILE ".local\bin")
}
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { Fail "uv was installed but cannot be found. Close this window and run setup.bat again." }
Ok (& uv --version)

# ---------------------------------------------------------------------------------------------
Step 3 "Python 3.12 + packages (first time: ~4 GB download, PyTorch is most of it)"
& uv sync
if ($LASTEXITCODE -ne 0) { Fail "Installing the Python packages failed (see the messages above)." }
$torchInfo = (& uv run python -c "import torch; print(torch.__version__, torch.cuda.is_available())")
Ok "packages installed (PyTorch $torchInfo)"

# ---------------------------------------------------------------------------------------------
Step 4 "Browser for the automated game test"
& uv run playwright install chromium
if ($LASTEXITCODE -eq 0) { Ok "Chromium installed" } else { Note "Chromium download failed - Microsoft Edge will be used instead" }

# ---------------------------------------------------------------------------------------------
Step 5 "Ollama (runs the language models)"
$ollamaDir = Join-Path $env:LOCALAPPDATA "Programs\Ollama"
Add-ToPath $ollamaDir
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    $installed = $false
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        Write-Host "  installing Ollama with winget..."
        & winget install --id Ollama.Ollama -e --silent --accept-package-agreements --accept-source-agreements
        Add-ToPath $ollamaDir
        $installed = [bool](Get-Command ollama -ErrorAction SilentlyContinue)
    }
    if (-not $installed) {
        Write-Host "  downloading the Ollama installer..."
        $exe = Join-Path $env:TEMP "OllamaSetup.exe"
        try { Invoke-WebRequest -Uri "https://ollama.com/download/OllamaSetup.exe" -OutFile $exe -UseBasicParsing -ErrorAction Stop }
        catch { Fail "Could not download Ollama: $($_.Exception.Message)" }
        Start-Process -FilePath $exe -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART" -Wait
        Add-ToPath $ollamaDir
    }
}
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) { Fail "Ollama is not installed. Install it from https://ollama.com/download and run setup.bat again." }
if (-not (Test-Ollama)) {
    Write-Host "  starting the Ollama server..."
    Start-Process -FilePath (Get-Command ollama).Source -ArgumentList "serve" -WindowStyle Hidden
    for ($i = 0; $i -lt 30 -and -not (Test-Ollama); $i++) { Start-Sleep -Seconds 1 }
}
if (Test-Ollama) { Ok ("Ollama " + ((& ollama --version) -join " ") + " is running") } else { Fail "Ollama is installed but its server did not start. Open the Ollama app from the Start menu, then run setup.bat again." }

# ---------------------------------------------------------------------------------------------
Step 6 "AI models (first time: 15-25 GB, can take a while)"
if ($SkipModels) {
    Note "skipped (-SkipModels): models download on first use"
} else {
    & uv run python setup_check.py --prefetch
    if ($LASTEXITCODE -ne 0) { Note "Some models did not download. Run setup.bat again to retry (finished downloads are kept)." }
    else { Ok "all models downloaded" }
}

# ---------------------------------------------------------------------------------------------
Step 7 "Pre-flight check"
& uv run python setup_check.py
$checkOk = ($LASTEXITCODE -eq 0)

Write-Host ""
if ($checkOk) {
    Write-Host "Setup complete." -ForegroundColor Green
    Write-Host "Make a game:   run.bat `"a cat flying a rocket and shooting asteroids`""
    Write-Host "Benchmark:     run.bat --batch prompts\benchmark.txt"
} else {
    Write-Host "Setup finished, but the check above found a problem - see the FAIL lines." -ForegroundColor Yellow
}
try { Stop-Transcript | Out-Null } catch { }
