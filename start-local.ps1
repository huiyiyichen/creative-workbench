param(
  [switch]$OpenBrowser,
  [switch]$Production,
  [switch]$Development,
  [ValidateRange(1, 65515)]
  [int]$BackendPort = 8102,
  [ValidateRange(1, 65515)]
  [int]$FrontendPort = 3000,
  [ValidateRange(5, 1800)]
  [int]$StartupTimeoutSeconds = 600
)

$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'backend'
$frontendRoot = Join-Path $projectRoot 'frontend'
$dataRoot = Join-Path $backendRoot 'data'
$python = Join-Path $backendRoot '.venv\Scripts\python.exe'
$next = Join-Path $frontendRoot 'node_modules\next\dist\bin\next'
$productionRoot = Join-Path $frontendRoot '.next-local'
$Production = $Production -or -not $Development

function Invoke-InDirectory([string]$Directory, [string]$Command, [string[]]$Arguments) {
  Push-Location -LiteralPath $Directory
  try {
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Setup command failed: $Command" }
  } finally { Pop-Location }
}

function New-LocalSecret {
  $bytes = New-Object byte[] 32
  $rng = [Security.Cryptography.RandomNumberGenerator]::Create()
  try { $rng.GetBytes($bytes) } finally { $rng.Dispose() }
  return [BitConverter]::ToString($bytes).Replace('-', '').ToLowerInvariant()
}

function Get-EnvValue([string]$Content, [string]$Name) {
  $match = [regex]::Match($Content, "(?m)^\s*$Name\s*=\s*(.*?)\s*$")
  return $match.Groups[1].Value.Trim().Trim('"').Trim("'")
}

function Prepare-Dependencies {
  $nodeVersion = & $node --version
  if ([int]($nodeVersion.TrimStart('v').Split('.')[0]) -lt 20) { throw 'Install Node.js 20 or newer.' }
  if (-not (Test-Path -LiteralPath $python)) {
    $uv = (Get-Command uv -ErrorAction SilentlyContinue).Source
    if (-not $uv) { throw 'Install uv, then run start.cmd again. See README.md.' }
    Write-Output 'Preparing Python and backend dependencies...'
    Invoke-InDirectory $backendRoot $uv @('sync', '--frozen', '--python', '3.12')
  }
  $npm = (Get-Command npm.cmd -ErrorAction Stop).Source
  if (-not (Test-Path -LiteralPath $next)) {
    Write-Output 'Installing frontend dependencies...'
    Invoke-InDirectory $frontendRoot $npm @('ci', '--no-audit', '--no-fund')
  }
  $mediaRoot = Join-Path $backendRoot 'media_runtime'
  if (-not (Test-Path -LiteralPath (Join-Path $mediaRoot 'node_modules\remotion\package.json'))) {
    Write-Output 'Installing animation dependencies...'
    Invoke-InDirectory $mediaRoot $npm @('ci', '--no-audit', '--no-fund')
  }
}

function Prepare-Database {
  $null = New-Item -ItemType Directory -Path $dataRoot -Force
  $envPath = Join-Path $backendRoot '.env'
  if (-not (Test-Path -LiteralPath $envPath) -and -not $env:DATABASE_URL) {
    $databasePort = 15432
    while (@(Get-Listener $databasePort).Count -gt 0) { $databasePort++ }
    $secret = New-LocalSecret
    $content = "# Managed local database`nAPP_ENV=development`n" +
      "DATABASE_URL=postgresql+asyncpg://workbench:$secret@127.0.0.1:$databasePort/creative_workbench`n" +
      "APP_SECRET_KEY=$(New-LocalSecret)`nCORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000`n" +
      "AUTO_CREATE_TABLES_ON_STARTUP=true`nSTARTUP_SEED_ENABLED=true`n" +
      "DUCKDB_STARTUP_INIT_ENABLED=false`n"
    [IO.File]::WriteAllText($envPath, $content, (New-Object Text.UTF8Encoding($false)))
  }
  $envText = if (Test-Path -LiteralPath $envPath) { [IO.File]::ReadAllText($envPath) } else { '' }
  $databaseUrl = if ($env:DATABASE_URL) { $env:DATABASE_URL } else { Get-EnvValue $envText 'DATABASE_URL' }
  if (-not $databaseUrl) { throw 'Set DATABASE_URL in backend/.env. See README.md.' }
  $clusterRoot = Join-Path $dataRoot 'postgres'
  $managed = -not $env:DATABASE_URL -and (
    $envText.StartsWith('# Managed local database') -or (Test-Path -LiteralPath (Join-Path $clusterRoot 'PG_VERSION'))
  )
  if (-not $managed) {
    Write-Output 'Using the PostgreSQL connection configured in DATABASE_URL.'
    return
  }
  $dbUri = [Uri]($databaseUrl -replace '^postgresql\+[^:]+:', 'postgresql:')
  if ($dbUri.Host -notin @('127.0.0.1', 'localhost')) { return }
  $databasePort = $dbUri.Port
  $userInfo = $dbUri.UserInfo.Split(':', 2)
  $databaseUser = [Uri]::UnescapeDataString($userInfo[0])
  $databasePassword = if ($userInfo.Count -gt 1) { [Uri]::UnescapeDataString($userInfo[1]) } else { '' }
  $databaseName = [Uri]::UnescapeDataString($dbUri.AbsolutePath.TrimStart('/'))
  $pgRoot = Join-Path $dataRoot 'runtime\pgsql'
  if (-not (Test-Path -LiteralPath (Join-Path $pgRoot 'bin\pg_ctl.exe'))) {
    Write-Output 'Downloading PostgreSQL binaries (first start)...'
    $runtimeRoot = Join-Path $dataRoot 'runtime'
    $null = New-Item -ItemType Directory -Path $runtimeRoot -Force
    $download = Join-Path $runtimeRoot 'postgresql-binaries.zip'
    $oldProgress = $ProgressPreference
    try {
      $ProgressPreference = 'SilentlyContinue'
      [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
      Invoke-WebRequest -UseBasicParsing -Uri 'https://get.enterprisedb.com/postgresql/postgresql-16.15-1-windows-x64-binaries.zip' -OutFile $download
      Expand-Archive -LiteralPath $download -DestinationPath $runtimeRoot -Force
      Remove-Item -LiteralPath $download
    } finally { $ProgressPreference = $oldProgress }
  }
  # PostgreSQL's Windows binaries use an ASCII drive path for CJK workspaces.
  if (-not ('CreativeWorkbench.LocalDrive' -as [type])) {
    Add-Type -TypeDefinition @'
using System.Runtime.InteropServices;
using System.Text;
namespace CreativeWorkbench {
  public static class LocalDrive {
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)]
    private static extern uint QueryDosDevice(string name, StringBuilder target, int length);
    public static string Target(string name) {
      var target = new StringBuilder(32768);
      return QueryDosDevice(name, target, target.Capacity) == 0 ? null : target.ToString();
    }
  }
}
'@
  }
  $drive = $null
  $freeDrive = $null
  foreach ($letter in [char[]](90..80)) {
    $candidate = "$($letter):"
    $target = [CreativeWorkbench.LocalDrive]::Target($candidate)
    if ([string]::Equals($target, ('\??\' + $dataRoot), [StringComparison]::OrdinalIgnoreCase)) {
      $drive = $candidate
      break
    }
    if ($null -eq $target -and $null -eq $freeDrive) { $freeDrive = $candidate }
  }
  if (-not $drive) {
    if (-not $freeDrive) { throw 'A free drive letter between P: and Z: is required for PostgreSQL.' }
    & subst.exe $freeDrive $dataRoot
    if ($LASTEXITCODE -ne 0) { throw 'Could not map the local PostgreSQL data directory.' }
    $drive = $freeDrive
  }
  $bin = "$drive\runtime\pgsql\bin"
  $cluster = "$drive\postgres"
  if (-not (Test-Path -LiteralPath (Join-Path $clusterRoot 'PG_VERSION'))) {
    Write-Output 'Creating a new, independent local database...'
    $passwordFile = Join-Path $dataRoot 'postgres-init-password'
    [IO.File]::WriteAllText($passwordFile, $databasePassword, (New-Object Text.UTF8Encoding($false)))
    try {
      & "$bin\initdb.exe" -D $cluster -U $databaseUser --encoding=UTF8 --locale=C --auth=scram-sha-256 "--pwfile=$drive\postgres-init-password"
      if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL initialization failed.' }
    } finally { Remove-Item -LiteralPath $passwordFile -ErrorAction SilentlyContinue }
  }
  if (@(Get-Listener $databasePort).Count -eq 0) {
    & "$bin\pg_ctl.exe" -D $cluster -l "$drive\postgres-server.log" -o "-h 127.0.0.1 -p $databasePort" -w start
    if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL startup failed. See backend/data/postgres-server.log.' }
  }
  & "$bin\pg_isready.exe" --host=127.0.0.1 "--port=$databasePort" "--username=$databaseUser"
  if ($LASTEXITCODE -ne 0) { throw 'The configured PostgreSQL port is unavailable.' }
  $oldPassword = $env:PGPASSWORD
  try {
    $env:PGPASSWORD = $databasePassword
    $escapedName = $databaseName.Replace("'", "''")
    $exists = & "$bin\psql.exe" -h 127.0.0.1 -p $databasePort -U $databaseUser -d postgres -At -c "SELECT 1 FROM pg_database WHERE datname = '$escapedName'"
    if ($LASTEXITCODE -ne 0) { throw 'Could not connect to the local database.' }
    if ($exists -ne '1') {
      & "$bin\createdb.exe" -h 127.0.0.1 -p $databasePort -U $databaseUser -- $databaseName
      if ($LASTEXITCODE -ne 0) { throw 'Could not create the local workspace database.' }
    }
  } finally { $env:PGPASSWORD = $oldPassword }
}

function Get-Listener([int]$Port) {
  return @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
}

function Test-ServiceProcess([int]$ProcessId, [string]$Kind) {
  $seen = @{}
  for ($depth = 0; $depth -lt 4 -and $ProcessId -gt 0; $depth++) {
    if ($seen.ContainsKey($ProcessId)) { break }
    $seen[$ProcessId] = $true
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    if ($null -eq $process) { break }
    $command = $process.CommandLine
    if ($Kind -eq 'backend') {
      $samePython = [string]::Equals($process.ExecutablePath, $python, [StringComparison]::OrdinalIgnoreCase)
      if ($samePython -and $command -match '\buvicorn\s+app\.main:app\b') { return $true }
    } elseif ($command -and $command.IndexOf((Join-Path $frontendRoot 'node_modules\next\dist\'), [StringComparison]::OrdinalIgnoreCase) -ge 0) {
      return $true
    }
    $ProcessId = $process.ParentProcessId
  }
  return $false
}

function Find-ServicePort([int]$PreferredPort, [string]$Kind) {
  $firstAvailable = $null
  $activeListeners = @(Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue)
  for ($port = $PreferredPort; $port -le ($PreferredPort + 20); $port++) {
    $listeners = @($activeListeners | Where-Object { $_.LocalPort -eq $port })
    if ($listeners.Count -eq 0) {
      if ($null -eq $firstAvailable) { $firstAvailable = $port }
      continue
    }
    foreach ($listener in $listeners) {
      if (Test-ServiceProcess $listener.OwningProcess $Kind) { return $port }
    }
  }
  if ($null -eq $firstAvailable) { throw "No available $Kind port between $PreferredPort and $($PreferredPort + 20)." }
  return $firstAvailable
}

function Get-FrontendProcess([int]$ProcessId) {
  for ($depth = 0; $depth -lt 4 -and $ProcessId -gt 0; $depth++) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    if ($null -eq $process) { return $null }
    if ($process.CommandLine -and $process.CommandLine.IndexOf($next, [StringComparison]::OrdinalIgnoreCase) -ge 0) {
      return $process
    }
    $ProcessId = $process.ParentProcessId
  }
  return $null
}

function Stop-Frontend([int]$Port) {
  foreach ($listener in @(Get-Listener $Port)) {
    $process = Get-FrontendProcess $listener.OwningProcess
    if ($null -eq $process) { throw 'Refusing to stop a frontend process from another workspace.' }
    & taskkill.exe /PID $process.ProcessId /T /F | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not stop the old Creative Workbench frontend.' }
  }
}

function Get-BuildFingerprint {
  $roots = @('src', 'public') | ForEach-Object { Join-Path $frontendRoot $_ }
  $files = @($roots | Where-Object { Test-Path -LiteralPath $_ } | ForEach-Object {
    Get-ChildItem -LiteralPath $_ -Recurse -File
  })
  $files += @('next.config.js', 'package.json', 'package-lock.json', 'tsconfig.json', 'postcss.config.mjs') |
    ForEach-Object { Join-Path $frontendRoot $_ } |
    Where-Object { Test-Path -LiteralPath $_ } |
    ForEach-Object { Get-Item -LiteralPath $_ }
  $fileHasher = [Security.Cryptography.SHA256]::Create()
  try {
    $parts = foreach ($file in $files | Sort-Object FullName) {
      $stream = [IO.File]::OpenRead($file.FullName)
      try {
        $digest = [BitConverter]::ToString($fileHasher.ComputeHash($stream)).Replace('-', '')
        "$($file.FullName):$digest"
      } finally { $stream.Dispose() }
    }
  } finally {
    $fileHasher.Dispose()
  }
  $parts += $env:BACKEND_API_URL
  $sha = [Security.Cryptography.SHA256]::Create()
  try {
    return [BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes(($parts -join "`n"))))
  } finally { $sha.Dispose() }
}

function Wait-Http([string]$Url, [string]$LogPath) {
  $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    $response = $null
    try {
      $response = $http.GetAsync($Url).GetAwaiter().GetResult()
      if ([int]$response.StatusCode -eq 200) { return }
    } catch {
      # Services can briefly refuse connections while starting or compiling.
    } finally {
      if ($null -ne $response) { $response.Dispose() }
    }
    Start-Sleep -Milliseconds 750
  }
  throw "Service did not become ready: $Url. See $LogPath"
}

# Serialize double-clicks so two launchers cannot create competing services.
$hash = [System.Security.Cryptography.SHA256]::Create()
$workspaceId = [BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($projectRoot))).Replace('-', '')
$hash.Dispose()
$mutex = New-Object System.Threading.Mutex($false, "Local\CreativeWorkbench.Start.$workspaceId")
$lockAcquired = $false
$http = $null
$handler = $null

try {
  try { $lockAcquired = $mutex.WaitOne(0) } catch [System.Threading.AbandonedMutexException] { $lockAcquired = $true }
  if (-not $lockAcquired) {
    Write-Output 'Creative Workbench startup is already in progress.'
    exit 0
  }

  $node = (Get-Command node -ErrorAction Stop).Source
  $env:PYTHONUTF8 = '1'
  Prepare-Dependencies
  if ($Development -and $Production) { throw 'Choose either -Development or -Production.' }

  Add-Type -AssemblyName System.Net.Http
  $handler = New-Object System.Net.Http.HttpClientHandler
  $handler.UseProxy = $false
  $http = New-Object System.Net.Http.HttpClient($handler)
  $http.Timeout = [TimeSpan]::FromSeconds(15)

  Write-Output '[1/3] PostgreSQL'
  Prepare-Database

  $BackendPort = Find-ServicePort $BackendPort 'backend'
  $FrontendPort = Find-ServicePort $FrontendPort 'frontend'
  $env:PYTHONUTF8 = '1'
  $env:BACKEND_API_URL = "http://127.0.0.1:$BackendPort"
  $env:WORKBENCH_LOCAL_BUILD = if ($Production) { '1' } else { '0' }
  Write-Output "[2/3] Backend :$BackendPort"
  if (@(Get-Listener $BackendPort).Count -eq 0) {
    $backendArguments = @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$BackendPort")
    if (-not $Production) { $backendArguments += @('--reload', '--reload-dir', 'app') }
    Start-Process -FilePath $python `
      -ArgumentList $backendArguments `
      -WorkingDirectory $backendRoot `
      -RedirectStandardOutput (Join-Path $dataRoot 'backend-server.log') `
      -RedirectStandardError (Join-Path $dataRoot 'backend-server-error.log') `
      -WindowStyle Hidden
  }
  Wait-Http "http://127.0.0.1:$BackendPort/health/ready" (Join-Path $dataRoot 'backend-server-error.log')

  Write-Output "[3/3] Frontend :$FrontendPort"
  $fingerprintFile = Join-Path $productionRoot 'launcher-build.json'
  $needsBuild = $false
  if ($Production) {
    $fingerprint = Get-BuildFingerprint
    $previousBuild = $null
    if (Test-Path -LiteralPath $fingerprintFile) {
      try { $previousBuild = Get-Content -LiteralPath $fingerprintFile -Raw | ConvertFrom-Json } catch {}
    }
    $needsBuild = -not (Test-Path -LiteralPath (Join-Path $productionRoot 'BUILD_ID')) -or $previousBuild.fingerprint -ne $fingerprint
  }
  foreach ($listener in @(Get-Listener $FrontendPort)) {
    $process = Get-FrontendProcess $listener.OwningProcess
    $requestedMode = if ($Production) { 'start' } else { 'dev' }
    if ($null -ne $process -and ($needsBuild -or $process.CommandLine -notmatch ("\s" + $requestedMode + "\s"))) {
      Write-Output 'Replacing the previous Creative Workbench frontend runtime.'
      Stop-Frontend $FrontendPort
      break
    }
  }
  if ($needsBuild) {
    Write-Output 'Building the local frontend (first start or source update)...'
    $build = Start-Process -FilePath $node `
      -ArgumentList @("`"$next`"", 'build') `
      -WorkingDirectory $frontendRoot `
      -RedirectStandardOutput (Join-Path $frontendRoot '.runtime-build.log') `
      -RedirectStandardError (Join-Path $frontendRoot '.runtime-build-error.log') `
      -WindowStyle Hidden -PassThru
    $null = $build.Handle
    if (-not $build.WaitForExit($StartupTimeoutSeconds * 1000)) {
      & taskkill.exe /PID $build.Id /T /F | Out-Null
      throw 'Frontend build timed out. See frontend/.runtime-build.log.'
    }
    $build.WaitForExit()
    $build.Refresh()
    if ($build.ExitCode -ne 0) { throw 'Frontend build failed. See frontend/.runtime-build-error.log.' }
    @{ fingerprint = (Get-BuildFingerprint) } | ConvertTo-Json | Set-Content -LiteralPath $fingerprintFile -Encoding UTF8
  }
  if (@(Get-Listener $FrontendPort).Count -eq 0) {
    $frontendArguments = @("`"$next`"")
    if ($Production) { $frontendArguments += 'start' } else { $frontendArguments += @('dev', '--webpack') }
    $frontendArguments += @('--hostname', '127.0.0.1', '--port', "$FrontendPort")
    Start-Process -FilePath $node `
      -ArgumentList $frontendArguments `
      -WorkingDirectory $frontendRoot `
      -RedirectStandardOutput (Join-Path $frontendRoot '.runtime-start.log') `
      -RedirectStandardError (Join-Path $frontendRoot '.runtime-start-error.log') `
      -WindowStyle Hidden
  }
  $studioUrl = "http://127.0.0.1:$FrontendPort/studio"
  Wait-Http $studioUrl (Join-Path $frontendRoot '.runtime-start-error.log')
  Wait-Http "http://127.0.0.1:$FrontendPort/api/v1/studio/catalog" (Join-Path $frontendRoot '.runtime-start-error.log')
  $buildRoot = if ($Production) { $productionRoot } else { Join-Path $frontendRoot '.next\dev' }
  $manifest = Get-Content -LiteralPath (Join-Path $buildRoot 'build-manifest.json') -Raw | ConvertFrom-Json
  foreach ($asset in $manifest.rootMainFiles) {
    if ($asset -notlike 'static/*' -or $asset.Contains('..')) { throw 'Invalid frontend bootstrap asset path.' }
    Wait-Http "http://127.0.0.1:$FrontendPort/_next/$asset" (Join-Path $frontendRoot '.runtime-start-error.log')
  }
  Write-Output "Creative Workbench is ready: $studioUrl"
  if ($OpenBrowser) { Start-Process $studioUrl }
} catch {
  [Console]::Error.WriteLine("Startup failed: $($_.Exception.Message)")
  exit 1
} finally {
  if ($null -ne $http) { $http.Dispose() }
  if ($null -ne $handler) { $handler.Dispose() }
  if ($lockAcquired) { $mutex.ReleaseMutex() }
  $mutex.Dispose()
}
