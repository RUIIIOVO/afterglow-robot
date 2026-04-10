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
exit 1

