# Signs Windows files (an .exe, an installer, install.ps1) with the code-signing certificate.
#
#   powershell -ExecutionPolicy Bypass -File tools\sign-windows.ps1 [-Thumbprint ABC123...] FILE [FILE...]
#
# The certificate's private key lives on its hardware token or in its cloud signing
# service (required for code-signing certificates since 2023), so this runs on the PC
# where that token is plugged in / that service's tool is installed. With one code-signing
# certificate installed it's found by itself; with several, pass -Thumbprint.
# Needs signtool.exe from the Windows SDK ("Windows SDK Signing Tools for Desktop Apps").
# See docs/code-signing.md.

param(
    [string]$Thumbprint = $env:NUMPAD_SIGN_THUMBPRINT,
    [string]$TimestampUrl = "http://timestamp.digicert.com",
    [Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)][string[]]$Files
)
$ErrorActionPreference = "Stop"

function Find-SignTool {
    $onPath = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    $kits = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
    $found = Get-ChildItem -Path $kits -Recurse -Filter signtool.exe -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -like "*\x64\*" } | Sort-Object FullName -Descending | Select-Object -First 1
    if (-not $found) { throw "signtool.exe wasn't found - install the Windows SDK's signing tools." }
    return $found.FullName
}

if (-not $Thumbprint) {
    $certs = @(Get-ChildItem Cert:\CurrentUser\My -CodeSigningCert | Where-Object { $_.NotAfter -gt (Get-Date) })
    if ($certs.Count -eq 0) { throw "No valid code-signing certificate is installed (is the token plugged in?)." }
    if ($certs.Count -gt 1) {
        $certs | ForEach-Object { Write-Host "  $($_.Thumbprint)  $($_.Subject)  (until $($_.NotAfter.ToShortDateString()))" }
        throw "Several code-signing certificates: pass -Thumbprint with one of the above."
    }
    $Thumbprint = $certs[0].Thumbprint
}

$signtool = Find-SignTool
foreach ($file in $Files) {
    Write-Host "Signing $file"
    # SHA-256 signature, RFC 3161 timestamp: the signature stays valid after the certificate expires.
    & $signtool sign /fd SHA256 /sha1 $Thumbprint /tr $TimestampUrl /td SHA256 $file
    if ($LASTEXITCODE -ne 0) { throw "signtool couldn't sign $file (exit code $LASTEXITCODE)." }
    & $signtool verify /pa $file | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "$file was signed but doesn't verify." }
}
Write-Host "Done: $($Files.Count) file(s) signed and verified."
