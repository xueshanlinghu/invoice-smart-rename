$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
$TargetTriple = (rustc --print host-tuple).Trim()
if (-not $TargetTriple) {
    throw "无法读取 Rust target triple"
}

$BinaryDir = Join-Path $Root "src-tauri\binaries"
$WorkDir = Join-Path $Root "backend\.pyinstaller\build"
$SpecDir = Join-Path $Root "backend\.pyinstaller"
New-Item -ItemType Directory -Force -Path $BinaryDir, $WorkDir, $SpecDir | Out-Null

$BinaryName = "invoice-backend-$TargetTriple"
uv run --project (Join-Path $Root "backend") --extra build pyinstaller `
    --noconfirm `
    --clean `
    --onefile `
    --name $BinaryName `
    --distpath $BinaryDir `
    --workpath $WorkDir `
    --specpath $SpecDir `
    --collect-all pypdfium2 `
    (Join-Path $Root "backend\run_production.py")

if ($LASTEXITCODE -ne 0) {
    throw "后端 sidecar 构建失败，PyInstaller 退出码：$LASTEXITCODE"
}

Write-Host "后端 sidecar 已生成：$BinaryDir\$BinaryName.exe"
