$paths = @(
  'C:\Program Files\Git\cmd\git.exe',
  'C:\Program Files\Git\bin\git.exe',
  "$env:LOCALAPPDATA\Programs\Git\cmd\git.exe",
  "$env:ProgramFiles\Git\mingw64\bin\git.exe"
)
$out = 'C:\Users\User\gitpaths.txt'; Remove-Item $out -ErrorAction SilentlyContinue
foreach ($p in $paths) { "$p => " + (Test-Path $p) | Add-Content $out -Encoding UTF8 }
"machine_path_has_git=" + (([Environment]::GetEnvironmentVariable('Path','Machine') -match 'Git')) | Add-Content $out -Encoding UTF8
"user_path_has_git=" + (([Environment]::GetEnvironmentVariable('Path','User') -match 'Git')) | Add-Content $out -Encoding UTF8

