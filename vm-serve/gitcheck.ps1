$p = 'C:\Program Files\Git\cmd\git.exe'
"installed_git=" + (Test-Path $p) | Set-Content C:\Users\User\gitcheck.txt -Encoding UTF8
$g = Get-Command git -ErrorAction SilentlyContinue
"git_cmd=" + $(if($g){$g.Source}else{'MISSING'}) | Add-Content C:\Users\User\gitcheck.txt -Encoding UTF8
if ($g) { "version=" + (& git --version) | Add-Content C:\Users\User\gitcheck.txt -Encoding UTF8 }
"winget_running=" + (@(Get-Process winget,msiexec -ErrorAction SilentlyContinue).Count) | Add-Content C:\Users\User\gitcheck.txt -Encoding UTF8
