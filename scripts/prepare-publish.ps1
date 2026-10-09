param(
  [string]$SourceRoot,
  [string]$Destination
)

$ErrorActionPreference = 'Stop'
$SourceRoot = (Resolve-Path -LiteralPath $SourceRoot).Path
if (Test-Path -LiteralPath $Destination) { throw 'Publish folder already exists.' }
$Destination = [IO.Path]::GetFullPath($Destination)
$null = New-Item -ItemType Directory -Path $Destination
$folders = @(
  'backend/app', 'backend/alembic', 'backend/scripts', 'backend/tests',
  'backend/media_runtime/template', 'frontend/src', 'frontend/public', 'frontend/scripts', 'docs/assets'
)
$paths = @(
  '.gitignore', '.gitattributes', 'LICENSE', 'README.md', 'README.zh-CN.md',
  'start.cmd', 'start-local.ps1', 'docker-compose.yml',
  'backend/.dockerignore', 'backend/.env.example', 'backend/alembic.ini',
  'backend/Dockerfile', 'backend/pyproject.toml', 'backend/pytest.ini', 'backend/uv.lock',
  'backend/media_runtime/package.json', 'backend/media_runtime/package-lock.json',
  'frontend/.dockerignore', 'frontend/.env.example', 'frontend/.gitignore', 'frontend/Dockerfile',
  'frontend/eslint.config.mjs', 'frontend/next.config.js', 'frontend/package.json',
  'frontend/package-lock.json', 'frontend/postcss.config.mjs', 'frontend/tailwind.config.ts',
  'frontend/tsconfig.json', 'frontend/vitest.config.ts'
)
Push-Location -LiteralPath $SourceRoot
try {
  $paths += @(& rg --files --hidden @folders -g '!**/__pycache__/**' -g '!**/*.pyc' -g '!**/node_modules/**')
  if ($LASTEXITCODE -ne 0) { throw 'Could not enumerate publication sources.' }
} finally { Pop-Location }
foreach ($relative in @($paths | Sort-Object -Unique)) {
  $input = Join-Path $SourceRoot $relative
  $target = Join-Path $Destination $relative
  $file = Get-Item -LiteralPath $input
  if ($file.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Linked file: $relative" }
  $null = New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force
  Copy-Item -LiteralPath $input -Destination $target
}
Write-Output "Prepared $(@($paths | Sort-Object -Unique).Count) source and documentation files."
