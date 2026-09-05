param(
    [string]$VisualStudioPath = 'C:\Program Files\Microsoft Visual Studio\18\Community',
    [string]$Python = 'C:\Python314\python.exe',
    [switch]$Test
)
$ErrorActionPreference = 'Stop'
function Invoke-Checked([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE" }
}
# Dependencies must already be installed. No downloads, Git, or media operations.
$originalPath = $env:PATH
$originalPkgConfigPath = $env:PKG_CONFIG_PATH
Push-Location $PSScriptRoot
try {
    Import-Module "$VisualStudioPath\Common7\Tools\Microsoft.VisualStudio.DevShell.dll"
    Enter-VsDevShell -VsInstallPath $VisualStudioPath -SkipAutomaticLocation -DevCmdArguments '-arch=x64 -host_arch=x64'
    $cmakeRoot = "$VisualStudioPath\Common7\IDE\CommonExtensions\Microsoft\CMake"
    $env:PATH = "$VisualStudioPath\VC\Tools\Llvm\x64\bin;$PSScriptRoot\vcpkg_installed\x64-windows\tools\pkgconf;$cmakeRoot\Ninja;$cmakeRoot\CMake\bin;" + $env:PATH
    $env:PKG_CONFIG_PATH = "$PSScriptRoot\pkgconfig;$PSScriptRoot\vcpkg_installed\x64-windows-release\lib\pkgconfig"
    $placeboBuild = 'build/_deps/libplacebo-build-clang'
    $setup = @('-m', 'mesonbuild.mesonmain', 'setup', $placeboBuild,
        'build/_deps/libplacebo-src', '--native-file', 'meson-clang.ini',
        '--buildtype=release', '--default-library=shared',
        '-Dvulkan=disabled', '-Dopengl=disabled', '-Dd3d11=enabled',
        '-Dshaderc=enabled', '-Dglslang=disabled', '-Ddovi=enabled',
        '-Dlibdovi=disabled', '-Dlcms=disabled', '-Dxxhash=disabled',
        '-Ddemos=false', '-Dtests=false')
    if (Test-Path "$placeboBuild/meson-private/coredata.dat") { $setup += '--reconfigure' }
    Invoke-Checked $Python $setup
    Invoke-Checked $Python @('-m', 'mesonbuild.mesonmain', 'compile', '-C', $placeboBuild, '-j', '4')
    Invoke-Checked 'cmake' @('-S', '.', '-B', 'build/preview', '-G', 'Ninja',
        '-DCMAKE_BUILD_TYPE=Release', '-DMUXMENDER_COLOR_TEST=ON', '-DMUXMENDER_DV_PREVIEW=ON',
        "-DCMAKE_C_COMPILER=$VisualStudioPath/VC/Tools/Llvm/x64/bin/clang.exe",
        "-DCMAKE_CXX_COMPILER=$VisualStudioPath/VC/Tools/Llvm/x64/bin/clang++.exe")
    Invoke-Checked 'cmake' @('--build', 'build/preview', '--parallel', '4')
    if ($Test) {
        Invoke-Checked 'ctest' @('--test-dir', 'build/preview', '--output-on-failure', '--verbose')
        Invoke-Checked $Python @('tests/test_preview_safety.py')
    }
} finally {
    Pop-Location
    $env:PATH = $originalPath
    $env:PKG_CONFIG_PATH = $originalPkgConfigPath
}
