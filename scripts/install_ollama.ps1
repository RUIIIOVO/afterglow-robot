param(
  [switch]$RunInstall = $false
)

Write-Host "[Afterglow] 检查 Ollama 环境..."

$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if ($null -ne $ollama) {
  Write-Host "[OK] Ollama 已安装: $($ollama.Source)"
  exit 0
}

Write-Host "[MISSING] 未检测到 Ollama。"
Write-Host "建议安装方式："
Write-Host "1) 访问官方页面: https://ollama.com/download"
Write-Host "2) 或使用 winget: winget install Ollama.Ollama"
Write-Host "安装完成后执行: ollama --version"

if (-not $RunInstall) {
  Write-Host "[NEXT] 如需执行自动安装，请运行："
  Write-Host "powershell -ExecutionPolicy Bypass -File scripts/install_ollama.ps1 -RunInstall"
  exit 1
}

$winget = Get-Command winget -ErrorAction SilentlyContinue
if ($null -eq $winget) {
  Write-Host "[ERROR] 当前环境未检测到 winget，无法自动安装 Ollama。"
  exit 1
}

Write-Host "[RUN] 开始自动安装 Ollama..."
winget install -e --id Ollama.Ollama --accept-package-agreements --accept-source-agreements
if ($LASTEXITCODE -ne 0) {
  Write-Host "[ERROR] Ollama 安装失败。"
  exit $LASTEXITCODE
}

Write-Host "[OK] Ollama 安装命令执行完成。"
Write-Host "[NEXT] 请重新打开终端后执行：ollama --version"
exit 0
