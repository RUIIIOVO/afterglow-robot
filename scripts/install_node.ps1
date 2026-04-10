param(
  [switch]$RunInstall = $false
)

Write-Host "[Afterglow] 检查 Node.js / npx..."
$node = Get-Command node -ErrorAction SilentlyContinue
$npx = Get-Command npx -ErrorAction SilentlyContinue

if ($null -ne $node -and $null -ne $npx) {
  Write-Host "[OK] Node.js: $($node.Source)"
  & $node.Source --version
  Write-Host "[OK] npx: $($npx.Source)"
  exit 0
}

$installCmd = "winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements"
Write-Host "[MISSING] Node.js 或 npx 缺失。"
Write-Host "[INFO] 建议安装命令：$installCmd"

if (-not $RunInstall) {
  Write-Host "[NEXT] 如需执行安装，请运行："
  Write-Host "powershell -ExecutionPolicy Bypass -File scripts/install_node.ps1 -RunInstall"
  exit 1
}

$winget = Get-Command winget -ErrorAction SilentlyContinue
if ($null -eq $winget) {
  Write-Host "[ERROR] 当前环境未检测到 winget，无法自动安装 Node.js。"
  exit 1
}

Write-Host "[RUN] 开始自动安装 Node.js (LTS)..."
winget install -e --id OpenJS.NodeJS.LTS --accept-package-agreements --accept-source-agreements
if ($LASTEXITCODE -ne 0) {
  Write-Host "[ERROR] Node.js 安装失败。"
  exit $LASTEXITCODE
}

Write-Host "[OK] Node.js 安装命令执行完成。"
Write-Host "[NEXT] 请重新打开终端后执行：node --version && npx --version"
exit 0

