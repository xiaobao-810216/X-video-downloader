 = Get-Date -Format yyyyMMdd_HHmmss
 = 'v3.0.1'
 =  ����������__Windows_.zip
if (-not (Test-Path release)) { New-Item -ItemType Directory -Path release | Out-Null }
 = 'dist/����������'
 = Join-Path release 
if (Test-Path ) { Remove-Item  -Force }
Compress-Archive -Path (Join-Path  '*') -DestinationPath  -Force
Write-Output Created: 
