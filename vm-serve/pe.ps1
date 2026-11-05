$out = 'C:\Users\User\pathenv.txt'
Remove-Item $out -ErrorAction SilentlyContinue
"ENV PATH git entries:" | Add-Content $out
($env:PATH -split ';' | Where-Object { $_ -match 'Git' }) | ForEach-Object { "  " + $_ } | Add-Content $out
"machine:" | Add-Content $out
([Environment]::GetEnvironmentVariable('Path','Machine') -split ';' | Where-Object { $_ -match 'Git' }) | ForEach-Object { "  " + $_ } | Add-Content $out
"cmd where:" | Add-Content $out
$w = & cmd /c "where git 2>nul"
$w | Add-Content $out
"direct run:" | Add-Content $out
$d = & 'C:\Program Files\Git\cmd\git.exe' --version 2>&1
$d | Add-Content $out
