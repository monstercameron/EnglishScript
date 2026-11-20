[CmdletBinding()]
param(
    [ValidateSet('Demo', 'Live', 'Offline')][string]$Mode = 'Demo',
    [string]$Workspace,
    [string]$Model = 'jev+openai:gpt-6-luna',
    [string]$CredentialsFile
)

$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$python = Join-Path $root '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $python)) { $python = (Get-Command python).Source }
if (-not $Workspace) { $Workspace = Join-Path $PSScriptRoot ".local/$Mode" }
$null = [IO.Directory]::CreateDirectory($Workspace)
$folder = (Resolve-Path -LiteralPath $Workspace).Path
$inbox = Join-Path $folder 'inbox.txt'
if (-not (Test-Path -LiteralPath $inbox)) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'inbox.txt') -Destination $inbox
}
$options = @()
if ($Mode -eq 'Demo') { $options = @('--model', "replay:$(Join-Path $PSScriptRoot 'demo.jsonl')") }
if ($Mode -eq 'Live') { $options = @('--model', $Model) }
$previousPythonPath = $env:PYTHONPATH
$savedKeys = @{}
if ($CredentialsFile -and $Mode -eq 'Live') { $CredentialsFile = (Resolve-Path -LiteralPath $CredentialsFile).Path }
Push-Location -LiteralPath $folder
try {
    $env:PYTHONPATH = $root
    if ($Mode -eq 'Live') {
        if ($CredentialsFile) {
            $names = @{}
            $providers = $Model.Split('+') | ForEach-Object { $_.Split(':')[0] }
            if ('jev' -in $providers) {
                $names = @{ DF_JEV_API_KEY='JEV_API_KEY'; JEV_API_KEY='JEV_API_KEY'; TYPESAFE_API_KEY='TYPESAFE_API_KEY' }
            }
            if ('openai' -in $providers) { $names['OPENAI_API_KEY'] = 'OPENAI_API_KEY' }
            if ('anthropic' -in $providers) { $names['ANTHROPIC_API_KEY'] = 'ANTHROPIC_API_KEY' }
            foreach ($line in [IO.File]::ReadLines($CredentialsFile)) {
                if ($line -match '^\s*(?:export\s+)?([A-Za-z_][A-Za-z_0-9]*)\s*=\s*(.*?)\s*$' -and $names.ContainsKey($Matches[1])) {
                    $name = $names[$Matches[1]]
                    if (-not [Environment]::GetEnvironmentVariable($name)) {
                        $savedKeys[$name] = $null
                        [Environment]::SetEnvironmentVariable($name, $Matches[2].Trim('"', "'", [char]96))
                    }
                }
            }
        }
    }
    & $python -m englishscript (Join-Path $PSScriptRoot 'desk.english') @options
    $result = $LASTEXITCODE
    if ($result -eq 0) { Write-Host "Shift plan saved to $(Join-Path $folder 'shift-plan.txt')" }
} finally {
    $env:PYTHONPATH = $previousPythonPath
    foreach ($name in $savedKeys.Keys) { [Environment]::SetEnvironmentVariable($name, $null) }
    Pop-Location
}
exit $result
