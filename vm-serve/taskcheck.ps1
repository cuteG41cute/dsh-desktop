"files:" | Set-Content C:\Users\User\taskcheck.txt -Encoding UTF8
(Get-ChildItem C:\Users\User\actrun_act20.* -ErrorAction SilentlyContinue | ForEach-Object { $_.Name + " " + $_.Length }) | Add-Content C:\Users\User\taskcheck.txt
"task:" | Add-Content C:\Users\User\taskcheck.txt
$t = schtasks /query /tn act20 /fo list /v 2>&1
($t | Select-String "Status|Last Run|Last Result|Task To Run|状态|上次") | ForEach-Object { $_.Line.Trim() } | Add-Content C:\Users\User\taskcheck.txt
"proc:" | Add-Content C:\Users\User\taskcheck.txt
(Get-Process DshManager -ErrorAction SilentlyContinue | ForEach-Object { "pid=$($_.Id) sess=$($_.SessionId)" }) | Add-Content C:\Users\User\taskcheck.txt
