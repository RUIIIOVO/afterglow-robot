Write-Host "[Afterglow] 启动环境自检..."

$node = Get-Command node -ErrorAction SilentlyContinue
$npx = Get-Command npx -ErrorAction SilentlyContinue
$ollama = Get-Command ollama -ErrorAction SilentlyContinue

if ($null -eq $node) {
  Write-Host "[MISSING] Node.js"
} else {
  Write-Host "[OK] Node.js: $($node.Source)"
}

if ($null -eq $npx) {
  Write-Host "[MISSING] npx"
} else {
  Write-Host "[OK] npx: $($npx.Source)"
}

if ($null -eq $ollama) {
  Write-Host "[MISSING] Ollama"
} else {
  Write-Host "[OK] Ollama: $($ollama.Source)"
}

Write-Host "[INFO] 如需安装 Ollama：powershell -ExecutionPolicy Bypass -File scripts/install_ollama.ps1"
Write-Host "[INFO] 如需安装 OpenClaw：powershell -ExecutionPolicy Bypass -File scripts/install_openclaw.ps1 -RunInstall"
Write-Host "[DONE] 自检完成。"

