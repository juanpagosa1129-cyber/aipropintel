$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
python -m py_compile backend\app.py backend\propintel\config.py backend\propintel\database.py backend\propintel\geocoder.py backend\propintel\scoring.py backend\propintel\sources\csv_source.py backend\propintel\sources\rama_judicial.py
python -m unittest discover -s tests
node --check frontend\app.js
Write-Host "Propintel IA verificado correctamente."
