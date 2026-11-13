param([Parameter(Mandatory)][string]$DwgPath)
$ErrorActionPreference = 'Stop'
New-Item -ItemType Directory -Force cad-data | Out-Null
$stem = 'smoke-' + [guid]::NewGuid().ToString('N')
Copy-Item -LiteralPath $DwgPath -Destination "cad-data/$stem.dwg"
docker compose -f compose.cad.yaml run --build --rm cad-converter -o "$stem.dxf" "$stem.dwg"
if ($LASTEXITCODE -ne 0) { throw 'DWG conversion failed' }
$result = Get-Content "cad-data/$stem.dxf" -Raw
if ($result -notmatch 'SECTION' -or $result -notmatch 'ENTITIES' -or $result -notmatch 'EOF') {
    throw 'Converter output is not a complete ASCII DXF'
}
Write-Output "Smoke test passed: cad-data/$stem.dxf"
