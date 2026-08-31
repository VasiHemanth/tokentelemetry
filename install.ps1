# tokentelemetry — one-line installer (Windows PowerShell).
#   irm https://raw.githubusercontent.com/VasiHemanth/tokentelemetry/main/install.ps1 | iex
$ErrorActionPreference = "Stop"

$RepoUrl   = "https://github.com/VasiHemanth/tokentelemetry.git"
$TargetDir = if ($env:TOKENTELEMETRY_DIR) { $env:TOKENTELEMETRY_DIR } else { "tokentelemetry" }

function Need($cmd) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) {
    Write-Error "ERROR: $cmd is required but not installed."
    exit 1
  }
}

Need git
Need node
Need npm
if (-not (Get-Command python -ErrorAction SilentlyContinue) -and
    -not (Get-Command python3 -ErrorAction SilentlyContinue)) {
  Write-Error "ERROR: python is required but not installed."
  exit 1
}

if (-not (Test-Path "./bin/cli.js")) {
  if (Test-Path $TargetDir) {
    Write-Host "-> using existing clone at $TargetDir"
  } else {
    Write-Host "-> cloning $RepoUrl -> $TargetDir"
    git clone --depth 1 $RepoUrl $TargetDir
  }
  Set-Location $TargetDir
}

# Absolute path to the checkout. The shims below point at this exact location,
# so they keep working after the installer exits and from any directory.
$CheckoutDir = (Resolve-Path .).Path

# Write a tokentelemetry.cmd (plus a .ps1 alongside) into a stable user-bin
# directory that is on the user PATH. The .cmd is what makes the bare name work
# from both PowerShell and cmd.exe even when the execution policy refuses
# unsigned .ps1 files.
$UserBin = Join-Path $env:USERPROFILE ".local\bin"
New-Item -ItemType Directory -Force -Path $UserBin | Out-Null

@"
@echo off
REM tokentelemetry shim -- forwards to the installed checkout.
node "$CheckoutDir\bin\cli.js" %*
"@ | Set-Content -Path (Join-Path $UserBin "tokentelemetry.cmd") -Encoding ASCII

@"
# tokentelemetry shim -- forwards to the installed checkout.
& node "$CheckoutDir\bin\cli.js" @args
exit `$LASTEXITCODE
"@ | Set-Content -Path (Join-Path $UserBin "tokentelemetry.ps1") -Encoding ASCII

$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($UserPath -notlike "*$UserBin*") {
  $NewPath = if ($UserPath) { "$UserBin;$UserPath" } else { $UserBin }
  [Environment]::SetEnvironmentVariable("Path", $NewPath, "User")
  Write-Host "-> added $UserBin to your user PATH (open a new terminal to pick it up)."
}

node bin/cli.js
