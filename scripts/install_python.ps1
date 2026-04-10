param(
  [switch]$RunInstall = $false
)

Write-Host "[Afterglow] 检查 Python..."
$python = Get-Command python -ErrorAction SilentlyContinue
$py = Get-Command py -ErrorAction SilentlyContinue

if ($null -ne $python) {
  Write-Host "[OK] Python: $($python.Source)"
  & $python.Source --version
  exit 0
}

if ($null -ne $py) {
  Write-Host "[OK] Python(py): $($py.Source)"
  & $py.Source -3 --version
  exit 0
}

$installCmd = "winget install -e --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements"
Write-Host "[MISSING] 未检测到 Python。"
Write-Host "[INFO] 建议安装命令：$installCmd"

if (-not $RunInstall) {
  Write-Host "[NEXT] 如需执行安装，请运行："
  Write-Host "powershell -ExecutionPolicy Bypass -File scripts/install_python.ps1 -RunInstall"
  exit 1
}

$winget = Get-Command winget -ErrorAction SilentlyContinue
if ($null -eq $winget) {
  Write-Host "[ERROR] 当前环境未检测到 winget，无法自动安装 Python。"
  exit 1
}

Write-Host "[RUN] 开始自动安装 Python..."
winget install -e --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements
if ($LASTEXITCODE -ne 0) {
  Write-Host "[ERROR] Python 安装失败。"
  exit $LASTEXITCODE
}

Write-Host "[OK] Python 安装命令执行完成。"
Write-Host "[NEXT] 请重新打开终端后执行：python --version"
exit 0

