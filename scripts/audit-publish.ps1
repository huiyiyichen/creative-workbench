param([string]$Root)

$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path -LiteralPath $Root).Path
$files = @(Get-ChildItem -LiteralPath $Root -Recurse -Force -File | Where-Object { $_.FullName -notlike "$Root\.git\*" })
$problems = foreach ($file in $files) {
  $relative = $file.FullName.Substring($Root.Length + 1)
  if ($relative -match '(?i)(^|[\\/])(\.venv|node_modules|\.next[^\\/]*|__pycache__|\.dsh|\.codex|\.playwright-cli|\.pytest_cache|\.ruff_cache)([\\/]|$)' -or
      $relative -match '(?i)^backend[\\/]data[\\/]' -or
      $relative -match '(?i)\.(db|sqlite[0-9]*|duckdb|log|pyc|pem|key|zip|mp4|mkv|wav|mp3|tsbuildinfo)$' -or
      ($file.Name -like '.env*' -and $file.Name -ne '.env.example') -or
      $file.Length -gt 10MB) {
    [pscustomobject]@{File=$relative; Problem='Private/runtime/large file'}
    continue
  }
  if ($file.Extension -in @('.png', '.jpg', '.ico')) { continue }
  $content = [IO.File]::ReadAllText($file.FullName)
  if ($content -match '\bsk-[A-Za-z0-9._-]{16,}|\b(?:ghp_|github_pat_|hf_|xox[baprs]-)[A-Za-z0-9_-]{20,}|\bAKIA[A-Z0-9]{16}\b' -or
      $content -match '-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----' -or
      $content -match '(?i)[CD]:[\\/](Users|作业|下载)[\\/]|\b26361\b' -or
      $content -match '\beyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\b') {
    [pscustomobject]@{File=$relative; Problem='Credential or personal-path candidate'}
  }
}
if (@($problems).Count) {
  $problems | Format-Table -AutoSize
  throw 'Publication scan needs attention.'
}
$readme = [IO.File]::ReadAllText((Join-Path $Root 'README.md'))
foreach ($match in [regex]::Matches($readme, '!\[[^\]]*\]\(([^)]+)\)')) {
  if (-not (Test-Path -LiteralPath (Join-Path $Root $match.Groups[1].Value))) {
    throw 'README image is missing.'
  }
}
[pscustomobject]@{
  Files=$files.Count
  TotalMB=[math]::Round(($files | Measure-Object Length -Sum).Sum / 1MB, 2)
  PrivacyFindings=0
  RuntimeFiles=0
} | Format-List
