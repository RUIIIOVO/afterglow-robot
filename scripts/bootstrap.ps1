Write-Host "[Afterglow] 启动环境自检..."

$python = Get-Command python -ErrorAction SilentlyContinue
$py = Get-Command py -ErrorAction SilentlyContinue
$node = Get-Command node -ErrorAction SilentlyContinue
$npx = Get-Command npx -ErrorAction SilentlyContinue
$ollama = Get-Command ollama -ErrorAction SilentlyContinue

if ($null -ne $python) {
  Write-Host "[OK] Python: $($python.Source)"
} elseif ($null -ne $py) {
  Write-Host "[OK] Python(py): $($py.Source)"
} else {
  Write-Host "[MISSING] Python"
}

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

Write-Host "[INFO] 如需安装 Ollama：powershell -ExecutionPolicy Bypass -File scripts/install_ollama.ps1 -RunInstall"
Write-Host "[INFO] 如需安装 OpenClaw：powershell -ExecutionPolicy Bypass -File scripts/install_openclaw.ps1 -RunInstall"
Write-Host "[INFO] 如需安装 Python：powershell -ExecutionPolicy Bypass -File scripts/install_python.ps1 -RunInstall"
Write-Host "[INFO] 如需安装 Node.js：powershell -ExecutionPolicy Bypass -File scripts/install_node.ps1 -RunInstall"
Write-Host "[INFO] 一键自动安装并启动：powershell -ExecutionPolicy Bypass -File scripts/start.ps1"
Write-Host "[DONE] 自检完成。"
