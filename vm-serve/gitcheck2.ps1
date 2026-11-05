$g = Get-Command git -ErrorAction SilentlyContinue
"git=" + $(if($g){$g.Source}else{'MISSING'}) | Set-Content C:\Users\User\gitcheck2.txt -Encoding UTF8
if ($g) { "ver=" + (& git --version) | Add-Content C:\Users\User\gitcheck2.txt -Encoding UTF8 }
