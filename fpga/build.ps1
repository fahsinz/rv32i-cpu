# Compile a DE10-Lite project, and optionally program the board.
#
#   .\build.ps1                           compile the CPU (de10_cpu)
#   .\build.ps1 -Program                  compile, then download over USB-Blaster
#   .\build.ps1 -Revision de10_lite       compile the combinational ALU demo
#
# Quartus writes some progress to stderr, which PowerShell treats as an error,
# so the compile runs through cmd and the exit code is what decides pass/fail.
param(
    [string]$Revision = "de10_cpu",
    [switch]$Program
)

$bin = "C:\altera_lite\25.1std\quartus\bin64"

Push-Location $PSScriptRoot
try {
    cmd /c "`"$bin\quartus_sh.exe`" --flow compile $Revision > ${Revision}_compile.log 2>&1"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "compile FAILED - see fpga/${Revision}_compile.log"
        Select-String -Path "${Revision}_compile.log" -Pattern 'Error \(' |
            Select-Object -First 10 | ForEach-Object { $_.Line.Trim() }
        exit 1
    }

    Select-String -Path "${Revision}_compile.log" -Pattern 'Full Compilation|Timing requirements' |
        ForEach-Object { ($_.Line -replace '\s+', ' ').Trim() }

    $summary = "output_files\$Revision.fit.summary"
    if (Test-Path $summary) {
        Get-Content $summary | Where-Object { $_ -match 'Total (logic|registers|pins|memory)' } |
            ForEach-Object { $_.Trim() }
    }

    if ($Program) {
        & "$bin\quartus_pgm.exe" -m jtag -o "p;output_files/$Revision.sof"
    }
} finally {
    Pop-Location
}
