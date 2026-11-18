# Build audio.cpp on Windows with static eSpeak-ng (required by English Kokoro voices).
# Prerequisites: VS Build Tools with the C++ workload, CMake, Ninja.
param(
    [string]$Source = 'C:\Users\twinblade\Documents\audio.cpp',
    [string]$BuildDir = 'build-espeak-win',
    [int]$Jobs = 10
)

$ErrorActionPreference = 'Stop'

if (-not (Test-Path (Join-Path $Source 'CMakeLists.txt'))) {
    throw "audio.cpp source not found: $Source"
}

$vswhere = Join-Path ([Environment]::GetFolderPath('ProgramFilesX86')) 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path $vswhere)) { throw 'vswhere not found; install VS Build Tools with C++ workload' }
$vs = & $vswhere -products '*' -latest -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
if (-not $vs) { throw 'No Visual Studio with C++ toolchain found' }

$vcvars = Join-Path $vs 'VC\Auxiliary\Build\vcvars64.bat'
if (-not (Test-Path $vcvars)) { throw "vcvars64.bat not found: $vcvars" }

Write-Host "VS: $vs"

$argsList = @(
    "call `"$vcvars`"",
    "cmake -S `"$Source`" -B `"$BuildDir`" -G Ninja -DCMAKE_BUILD_TYPE=Release",
    "-DENGINE_ENABLE_CUDA=OFF -DENGINE_ENABLE_VULKAN=OFF -DENGINE_ENABLE_HIP=OFF -DENGINE_ENABLE_WEBGPU=OFF",
    "-DENGINE_ENABLE_NATIVE_CPU=ON -DENGINE_ENABLE_LLAMAFILE=ON",
    "-DENGINE_BUILD_EXAMPLES=OFF -DENGINE_BUILD_TESTS=OFF -DENGINE_BUILD_WARMBENCH=OFF",
    "-DAUDIOCPP_DEPLOYMENT_BUILD=OFF -DAUDIOCPP_BUILD_NATIVE_MODEL_MANAGER=OFF",
    "-DAUDIOCPP_USE_SYSTEM_OPENSSL=OFF -DAUDIOCPP_MODEL_SET=full",
    "-DAUDIOCPP_MODELS=qwen3_tts,kokoro_tts",
    "-DAUDIOCPP_STATIC_ESPEAK=ON",
    "cmake --build `"$BuildDir`" --target audiocpp_server audiocpp_cli -j $Jobs"
)
$cmd = $argsList -join ' && '

Write-Host 'Building (first run: 15-30 minutes)...'
cmd /c $cmd
if ($LASTEXITCODE -ne 0) { throw "Build failed (exit $LASTEXITCODE)" }

$bin = Join-Path $BuildDir 'bin'
Get-ChildItem $bin -ErrorAction SilentlyContinue | ForEach-Object { Write-Host $_.Name }
