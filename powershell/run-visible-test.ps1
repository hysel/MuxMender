param(
    [Parameter(Mandatory=$true)][string]$MediaPath,
    [string]$CodePath = "$env:LOCALAPPDATA\AMD\AI_Bundle\VSCode\Code.exe",
    [string]$UserDataDirectory,
    [string]$ExtensionsDirectory,
    [ValidateSet('auto','amd','nvidia','intel','cpu')][string]$Hardware = 'auto'
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $MediaPath -PathType Leaf)) { throw "Media file not accessible: $MediaPath" }
$encoded = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($MediaPath)).TrimEnd('=').Replace('+','-').Replace('/','_')
$uri = "vscode://hysel.muxmender-vscode/delivery?file64=$encoded&hardware=$Hardware"
$codeArguments = @('--reuse-window', '--open-url', $uri)
if ($UserDataDirectory) { $codeArguments += @('--user-data-dir', $UserDataDirectory) }
if ($ExtensionsDirectory) { $codeArguments += @('--extensions-dir', $ExtensionsDirectory) }
# Code.exe must run as Electron, not as the agent's inherited Node mode.
$priorElectronMode = $env:ELECTRON_RUN_AS_NODE
try {
    $env:ELECTRON_RUN_AS_NODE = $null
    & $CodePath @codeArguments
} finally { $env:ELECTRON_RUN_AS_NODE = $priorElectronMode }
