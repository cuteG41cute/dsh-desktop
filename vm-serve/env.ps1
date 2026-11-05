$git = Get-Command git -ErrorAction SilentlyContinue
$wg = Get-Command winget -ErrorAction SilentlyContinue
"git=" + $(if($git){$git.Source}else{'MISSING'}) | Set-Content C:\Users\User\env.txt -Encoding UTF8
"winget=" + $(if($wg){$wg.Source}else{'MISSING'}) | Add-Content C:\Users\User\env.txt -Encoding UTF8
"path_git=" + (@($env:PATH -split ';' | Where-Object { $_ -match 'Git' }) -join '|') | Add-Content C:\Users\User\env.txt -Encoding UTF8
