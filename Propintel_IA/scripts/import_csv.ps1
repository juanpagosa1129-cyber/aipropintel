param(
  [Parameter(Mandatory=$true)]
  [string]$Path,
  [string]$BaseUrl = "http://127.0.0.1:8088"
)

$ErrorActionPreference = "Stop"
$CsvText = Get-Content -LiteralPath $Path -Raw
$Body = @{ csv_text = $CsvText } | ConvertTo-Json -Depth 3
Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/import/csv" -ContentType "application/json" -Body $Body
