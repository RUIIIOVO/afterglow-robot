param(
  [string]$Config = "config/config.yaml",
  [string]$BindHost = "127.0.0.1",
  [int]$Port = 8787,
  [switch]$CheckOnly = $false
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $scriptDir "..")
Set-Location $repoRoot

function Resolve-PythonCommand {
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($null -ne $python) {
    return @($python.Source)
  }
  $py = Get-Command py -ErrorAction SilentlyContinue
  if ($null -ne $py) {
    return @($py.Source, "-3")
  }
  return $null
}

function Invoke-InstallScript {
  param(
    [string]$ScriptPath
  )
  if (-not (Test-Path -LiteralPath $ScriptPath)) {
    throw "Missing install script: $ScriptPath"
  }
  & powershell -ExecutionPolicy Bypass -File $ScriptPath -RunInstall
  if ($LASTEXITCODE -ne 0) {
    throw "Install script failed: $ScriptPath"
  }
  Sync-PathEnvironment
}

function Sync-PathEnvironment {
  $allSegments = New-Object System.Collections.Generic.List[string]
  $seen = New-Object "System.Collections.Generic.HashSet[string]" ([System.StringComparer]::OrdinalIgnoreCase)
  foreach ($rawPath in @($env:Path, [Environment]::GetEnvironmentVariable("Path", "Machine"), [Environment]::GetEnvironmentVariable("Path", "User"))) {
    if ([string]::IsNullOrWhiteSpace($rawPath)) {
      continue
    }
    foreach ($segment in ($rawPath -split ";")) {
      $trimmed = $segment.Trim()
      if ([string]::IsNullOrWhiteSpace($trimmed)) {
        continue
      }
      if ($seen.Add($trimmed)) {
        $allSegments.Add($trimmed) | Out-Null
      }
    }
  }
  $env:Path = ($allSegments -join ";")
}

function Invoke-CheckedCommand {
  param(
    [object[]]$Command
  )
  $parts = @($Command)
  if ($parts.Length -eq 0) {
    throw "Empty command."
  }
  $exe = [string]$parts[0]
  $args = @()
  if ($parts.Length -gt 1) {
    $args = @($parts[1..($parts.Length - 1)])
  }
  & $exe @args
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed: $($parts -join ' ')"
  }
}

function Test-OllamaHealth {
  param(
    [string]$Endpoint,
    [int]$TimeoutSeconds = 5
  )
  $uri = "$($Endpoint.TrimEnd('/'))/api/tags"
  try {
    Invoke-RestMethod -Uri $uri -Method Get -TimeoutSec $TimeoutSeconds | Out-Null
    return $true
  } catch {
    return $false
  }
}

function Get-LlmRuntimeConfig {
  param(
    [object[]]$PythonCommand,
    [string]$ConfigPath
  )
  $script = @'
from src.common.config import load_config
import json

config = load_config(r"__CONFIG_PATH__")
print(json.dumps({
    "endpoint": config.llm.endpoint,
    "model": config.llm.model,
}, ensure_ascii=False))
'@
  $script = $script.Replace("__CONFIG_PATH__", $ConfigPath.Replace("\", "\\"))
  $parts = @($PythonCommand)
  $exe = [string]$parts[0]
  $args = @()
  if ($parts.Length -gt 1) {
    $args += @($parts[1..($parts.Length - 1)])
  }
  $args += "-"
  $output = @"
$script
"@ | & $exe @args
  if ($LASTEXITCODE -ne 0) {
    throw "Read LLM config failed."
  }
  return (($output | Out-String).Trim() | ConvertFrom-Json)
}

function Test-LocalOllamaEndpoint {
  param(
    [string]$Endpoint
  )
  try {
    $uri = [Uri]$Endpoint
  } catch {
    return $false
  }
  return $uri.Host -in @("127.0.0.1", "localhost", "::1")
}

function Ensure-OllamaReady {
  param(
    [string]$OllamaExe,
    [string]$Endpoint,
    [string]$ModelName
  )
  if (-not (Test-LocalOllamaEndpoint -Endpoint $Endpoint)) {
    Write-Host "[INFO] LLM endpoint is not local Ollama, skip local bootstrap: $Endpoint"
    return
  }

  if (-not (Test-OllamaHealth -Endpoint $Endpoint)) {
    Write-Host "[AUTO] Ollama service not ready, starting local server..."
    Start-Process -FilePath $OllamaExe -ArgumentList "serve" -WindowStyle Hidden | Out-Null
    $ready = $false
    foreach ($i in 1..30) {
      Start-Sleep -Seconds 1
      if (Test-OllamaHealth -Endpoint $Endpoint) {
        $ready = $true
        break
      }
    }
    if (-not $ready) {
      throw "Ollama service failed to start: $Endpoint"
    }
  }

  if ([string]::IsNullOrWhiteSpace($ModelName)) {
    return
  }

  Write-Host "[AUTO] checking Ollama model: $ModelName"
  $listOutput = & $OllamaExe list 2>&1
  if ($LASTEXITCODE -ne 0) {
    throw "ollama list failed: $($listOutput | Out-String)"
  }
  $modelPattern = "^{0}(\s|$)" -f [regex]::Escape($ModelName)
  $modelFound = $false
  foreach ($line in $listOutput) {
    if ([string]$line -match $modelPattern) {
      $modelFound = $true
      break
    }
  }
  if ($modelFound) {
    return
  }

  Write-Host "[AUTO] pulling Ollama model: $ModelName"
  & $OllamaExe pull $ModelName
  if ($LASTEXITCODE -ne 0) {
    throw "ollama pull failed: $ModelName"
  }
}

function Invoke-PythonStdinScript {
  param(
    [object[]]$PythonCommand,
    [string]$ScriptContent
  )
  $pythonParts = @($PythonCommand)
  $pythonExe = [string]$pythonParts[0]
  $pythonArgs = @()
  if ($pythonParts.Length -gt 1) {
    $pythonArgs += @($pythonParts[1..($pythonParts.Length - 1)])
  }
  $pythonArgs += "-"
  @"
$ScriptContent
"@ | & $pythonExe @pythonArgs
  if ($LASTEXITCODE -ne 0) {
    throw "Python inline script failed."
  }
}

function Invoke-AfterglowWeixinPatch {
  param(
    [object[]]$PythonCommand,
    [string]$BridgeUrl
  )
  $patchScript = Join-Path $repoRoot "scripts/patch_openclaw_weixin_for_afterglow.py"
  if (-not (Test-Path -LiteralPath $patchScript)) {
    throw "Patch script not found: $patchScript"
  }
  Write-Host "[AUTO] patch openclaw-weixin to route messages into afterglow-robot..."
  $parts = @($PythonCommand)
  $exe = [string]$parts[0]
  $args = @()
  if ($parts.Length -gt 1) {
    $args += @($parts[1..($parts.Length - 1)])
  }
  $args += @($patchScript, "--bridge-url", $BridgeUrl)
  & $exe @args
  if ($LASTEXITCODE -ne 0) {
    throw "Patch openclaw-weixin failed."
  }
}

function Test-PythonPackages {
  param(
    [object[]]$PythonCommand
  )
  $script = @'
import importlib
import sys
required = ["yaml", "chromadb"]
optional = ["sentence_transformers"]
missing = []
for name in required:
    try:
        importlib.import_module(name)
    except Exception:
        missing.append(name)
for name in optional:
    try:
        importlib.import_module(name)
    except Exception:
        missing.append(name)
if missing:
    print(",".join(missing))
    sys.exit(1)
sys.exit(0)
'@
  $parts = @($PythonCommand)
  $exe = [string]$parts[0]
  $args = @()
  if ($parts.Length -gt 1) {
    $args += @($parts[1..($parts.Length - 1)])
  }
  $args += "-"
  $output = @"
$script
"@ | & $exe @args
  return @{
    ExitCode = $LASTEXITCODE
    Output = ($output | Out-String).Trim()
  }
}

function Ensure-PythonPackages {
  param(
    [object[]]$PythonCommand
  )
  $check = Test-PythonPackages -PythonCommand $PythonCommand
  if ($check.ExitCode -eq 0) {
    return
  }
  if ($check.Output -ne "") {
    Write-Host "[AUTO] missing python packages: $($check.Output)"
  } else {
    Write-Host "[AUTO] python package check failed, try install dependencies..."
  }
  $parts = @($PythonCommand)
  $exe = [string]$parts[0]
  $args = @()
  if ($parts.Length -gt 1) {
    $args += @($parts[1..($parts.Length - 1)])
  }
  $pipInstallOk = $false
  $installArgs = @()
  $installArgs += $args
  $installArgs += @("-m", "pip", "install", "--disable-pip-version-check", "-e", ".[embeddings]")
  & $exe @installArgs
  if ($LASTEXITCODE -eq 0) {
    $pipInstallOk = $true
  }
  if (-not $pipInstallOk) {
    throw "Install python dependencies failed."
  }
  $recheck = Test-PythonPackages -PythonCommand $PythonCommand
  if ($recheck.ExitCode -ne 0) {
    throw "Python dependencies still missing: $($recheck.Output)"
  }
}

function Resolve-OrCreateVenvPython {
  param(
    [object[]]$BasePythonCommand
  )
  $venvPython = Join-Path $repoRoot ".venv/Scripts/python.exe"
  if (-not (Test-Path -LiteralPath $venvPython)) {
    Write-Host "[AUTO] create local virtualenv (.venv)..."
    $parts = @($BasePythonCommand)
    $exe = [string]$parts[0]
    $args = @()
    if ($parts.Length -gt 1) {
      $args += @($parts[1..($parts.Length - 1)])
    }
    $venvArgs = @()
    $venvArgs += $args
    $venvArgs += @("-m", "venv", ".venv")
    & $exe @venvArgs
    if ($LASTEXITCODE -ne 0) {
      throw "Create .venv failed."
    }
  }
  if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "Venv python not found: $venvPython"
  }
  return @($venvPython)
}

function Test-IngestArtifacts {
  param(
    [object[]]$PythonCommand,
    [string]$ConfigPath
  )
  $checkScript = @'
from src.common.config import load_config
from src.runtime.errors import IngestArtifactsMissingError, VectorStoreNotBuiltError, AfterglowError
from src.vectorstore.chroma_store import ChromaVectorStore
import sys

try:
    config = load_config(r"__CONFIG_PATH__")
    output_base = config.resolve_path(config.output.base_dir)
    required = [
        output_base / "persona_prompt.txt",
        output_base / "fewshot.json",
    ]
    for path in required:
        if not path.exists():
            raise IngestArtifactsMissingError(str(path))

    chroma_dir = config.resolve_path(config.embedding.chroma_dir)
    store = ChromaVectorStore(
        chroma_dir=chroma_dir,
        model_name=config.embedding.model_name,
        provider=config.embedding.provider,
        allow_fallback=config.embedding.allow_fallback,
        fallback_provider=config.embedding.fallback_provider,
    )
    try:
        store.query("ping", top_k=1)
    except VectorStoreNotBuiltError:
        raise
    except Exception:
        pass
except IngestArtifactsMissingError as error:
    print(error.user_message)
    sys.exit(21)
except VectorStoreNotBuiltError as error:
    print(error.user_message)
    sys.exit(22)
except AfterglowError as error:
    print(error.user_message)
    sys.exit(1)
'@
  $checkScript = $checkScript.Replace("__CONFIG_PATH__", $ConfigPath.Replace("\", "\\"))
  $pythonParts = @($PythonCommand)
  $pythonExe = [string]$pythonParts[0]
  $pythonArgs = @()
  if ($pythonParts.Length -gt 1) {
    $pythonArgs += @($pythonParts[1..($pythonParts.Length - 1)])
  }
  $pythonArgs += "-"
  @"
$checkScript
"@ | & $pythonExe @pythonArgs
  return $LASTEXITCODE
}

try {
  Write-Host "[Afterglow] Startup checks begin..."
  Sync-PathEnvironment
  $pythonCmd = Resolve-PythonCommand
  if ($null -eq $pythonCmd) {
    Write-Host "[AUTO] Python not found, trying auto-install..."
    Invoke-InstallScript -ScriptPath (Join-Path $repoRoot "scripts/install_python.ps1")
    $pythonCmd = Resolve-PythonCommand
    if ($null -eq $pythonCmd) {
      Write-Host "[ERROR] Python not found (python/py). Please install Python 3.10+."
      exit 1
    }
  }

  $pythonCmd = Resolve-OrCreateVenvPython -BasePythonCommand $pythonCmd
  Ensure-PythonPackages -PythonCommand $pythonCmd

  $node = Get-Command node -ErrorAction SilentlyContinue
  $npx = Get-Command npx -ErrorAction SilentlyContinue
  if ($null -eq $node -or $null -eq $npx) {
    Write-Host "[AUTO] Node.js or npx missing, trying auto-install..."
    Invoke-InstallScript -ScriptPath (Join-Path $repoRoot "scripts/install_node.ps1")
    $node = Get-Command node -ErrorAction SilentlyContinue
    $npx = Get-Command npx -ErrorAction SilentlyContinue
    if ($null -eq $node -or $null -eq $npx) {
      throw "Node.js/npx still unavailable after installation."
    }
  }

  $ollama = Get-Command ollama -ErrorAction SilentlyContinue
  if ($null -eq $ollama) {
    Write-Host "[AUTO] Ollama missing, trying auto-install..."
    Invoke-InstallScript -ScriptPath (Join-Path $repoRoot "scripts/install_ollama.ps1")
    $ollama = Get-Command ollama -ErrorAction SilentlyContinue
    if ($null -eq $ollama) {
      throw "Ollama still unavailable after installation."
    }
  }

  $configPath = Resolve-Path -LiteralPath (Join-Path $repoRoot $Config) -ErrorAction SilentlyContinue
  if ($null -eq $configPath) {
    $exampleConfig = Join-Path $repoRoot "config/config.example.yaml"
    if (-not (Test-Path -LiteralPath $exampleConfig)) {
      Write-Host "[ERROR] Config template not found: $exampleConfig"
      exit 1
    }
    $targetConfig = Join-Path $repoRoot $Config
    $targetDir = Split-Path -Parent $targetConfig
    if (-not (Test-Path -LiteralPath $targetDir)) {
      New-Item -ItemType Directory -Path $targetDir | Out-Null
    }
    Copy-Item -LiteralPath $exampleConfig -Destination $targetConfig -Force
    $configPath = Resolve-Path -LiteralPath $targetConfig
    Write-Host "[INFO] Config file created: $configPath"
  }

  $llmRuntime = Get-LlmRuntimeConfig -PythonCommand $pythonCmd -ConfigPath $configPath.Path
  Ensure-OllamaReady -OllamaExe $ollama.Source -Endpoint $llmRuntime.endpoint -ModelName $llmRuntime.model

  Write-Host "[1/4] Run init (env + config checks)..."
  $initCommand = @()
  $initCommand += @($pythonCmd)
  $initCommand += @("-m", "src.cli.main", "init", "--config", $configPath.Path)
  Invoke-CheckedCommand -Command $initCommand

  $bridgeUrl = "http://$($BindHost):$Port/openclaw/event"

  Write-Host "[2/4] Run wechat-connect (install/check OpenClaw + bridge patch)..."
  $wechatCommand = @()
  $wechatCommand += @($pythonCmd)
  $wechatCommand += @("-m", "src.cli.main", "wechat-connect", "--config", $configPath.Path, "--bridge-url", $bridgeUrl)
  Invoke-CheckedCommand -Command $wechatCommand

  Write-Host "[3/4] Validate ingest artifacts..."
  $artifactCheckCode = Test-IngestArtifacts -PythonCommand $pythonCmd -ConfigPath $configPath.Path
  if ($artifactCheckCode -ne 0) {
    if ($artifactCheckCode -eq 21 -or $artifactCheckCode -eq 22) {
      Write-Host "[AUTO] ingest artifacts missing, run ingest now..."
      $ingestSucceeded = $false
      try {
        $ingestCommand = @()
        $ingestCommand += @($pythonCmd)
        $ingestCommand += @("-m", "src.cli.main", "ingest", "--config", $configPath.Path)
        Invoke-CheckedCommand -Command $ingestCommand
        $ingestSucceeded = $true
      } catch {
        $ingestSucceeded = $false
      }
      if (-not $ingestSucceeded) {
        $demoExportDir = Join-Path $repoRoot "tests/fixtures/single_account"
        if (Test-Path -LiteralPath $demoExportDir) {
          Write-Host "[AUTO] configured export_dir unavailable. fallback to demo data..."
          try {
            $demoIngestCommand = @()
            $demoIngestCommand += @($pythonCmd)
            $demoIngestCommand += @("-m", "src.cli.main", "ingest", "--config", $configPath.Path, "--export-dir", $demoExportDir, "--target-wxid", "wxid_target")
            Invoke-CheckedCommand -Command $demoIngestCommand
            $ingestSucceeded = $true
          } catch {
            $ingestSucceeded = $false
          }
        }
      }
      if (-not $ingestSucceeded) {
        Write-Host "[ERROR] ingest failed. please check wechat.export_dir in config/config.yaml."
        exit 1
      }

      Write-Host "[AUTO] re-check ingest artifacts..."
      $artifactCheckCode = Test-IngestArtifacts -PythonCommand $pythonCmd -ConfigPath $configPath.Path
      if ($artifactCheckCode -ne 0) {
        Write-Host "[ERROR] ingest artifacts check still failed after auto-ingest."
        exit 1
      }
    } else {
      Write-Host "[ERROR] ingest artifacts check failed. Run: python -m src.cli.main ingest --config $($configPath.Path)"
      exit 1
    }
  }

  if ($CheckOnly) {
    Write-Host "[DONE] All checks passed (CheckOnly)."
    exit 0
  }

  Write-Host "[4/4] Start bridge service..."
  Write-Host "[INFO] URL: http://$($BindHost):$Port"
  $serveCommand = @()
  $serveCommand += @($pythonCmd)
  $serveCommand += @("-m", "src.cli.main", "serve", "--config", $configPath.Path, "--host", $BindHost, "--port", "$Port")
  Invoke-CheckedCommand -Command $serveCommand
  exit 0
} catch {
  Write-Host "[ERROR] $($_.Exception.Message)"
  exit 1
}
