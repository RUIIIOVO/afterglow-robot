param(
  [switch]$RunInstall = $false
)

Write-Host "[Afterglow] 检查 Node.js / npx..."
$node = Get-Command node -ErrorAction SilentlyContinue
$npx = Get-Command npx -ErrorAction SilentlyContinue

if ($null -eq $node) {
  Write-Host "[MISSING] 未检测到 Node.js。请先安装 Node.js。"
  exit 1
}

if ($null -eq $npx) {
  Write-Host "[MISSING] 未检测到 npx。请先安装 npm。"
  exit 1
}

$installCmd = "npx -y @tencent-weixin/openclaw-weixin-cli@latest install"
Write-Host "[INFO] OpenClaw 安装命令：$installCmd"

if (-not $RunInstall) {
  Write-Host "[NEXT] 如需执行安装，请运行："
  Write-Host "powershell -ExecutionPolicy Bypass -File scripts/install_openclaw.ps1 -RunInstall"
  exit 0
}

Write-Host "[RUN] 开始执行 OpenClaw 安装命令..."
npx -y @tencent-weixin/openclaw-weixin-cli@latest install
if ($LASTEXITCODE -ne 0) {
  Write-Host "[ERROR] OpenClaw 安装失败。"
  exit $LASTEXITCODE
}

Write-Host "[OK] OpenClaw 安装命令执行完成。"
Write-Host "[NEXT] 请按 OpenClaw 指引完成扫码连接。"
exit 0

