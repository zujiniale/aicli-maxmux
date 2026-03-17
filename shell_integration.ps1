# aicli shell integration for PowerShell (Windows)
# Install: Add the content below to your $PROFILE
# Or run: aicli config install-shell --shell powershell
#
# Usage: Press Ctrl+G in PowerShell to generate an aicli shell command
#        from your current command buffer and paste it into the prompt.
#
# Requirements:
#   - aicli installed: pip install aicli-maxmux[lite]
#   - PSReadLine module (included with PowerShell 5.1+)

# ── Ctrl+G hotkey: generate shell command from current buffer ─────────────────

if (Get-Module -ListAvailable -Name PSReadLine) {
    Set-PSReadLineKeyHandler -Key Ctrl+g -ScriptBlock {
        param($key, $arg)

        # Get current buffer content
        $line = $null
        $cursor = $null
        [Microsoft.PowerShell.PSConsoleReadLine]::GetBufferState([ref]$line, [ref]$cursor)

        $prompt = $line.Trim()

        if (-not $prompt) {
            # Empty buffer — ask user inline
            Write-Host "`n[aicli] Enter prompt: " -NoNewline -ForegroundColor Cyan
            $prompt = Read-Host
        }

        if (-not $prompt) {
            # Still empty — abort
            return
        }

        Write-Host "`n[aicli] Generating command..." -ForegroundColor DarkGray

        try {
            # Run aicli cmd in lite+dry-run mode for minimal overhead
            $result = & aicli cmd --lite --dry-run $prompt 2>$null
            $result = $result.Trim()

            if ($result) {
                # Clear current buffer and insert generated command
                [Microsoft.PowerShell.PSConsoleReadLine]::DeleteLine()
                [Microsoft.PowerShell.PSConsoleReadLine]::Insert($result)
                Write-Host "`r[aicli] Command ready (Enter to run, Ctrl+C to cancel)" -ForegroundColor DarkGray
            } else {
                Write-Host "`r[aicli] No command generated." -ForegroundColor Yellow
            }
        } catch {
            Write-Host "`r[aicli] Error: $_" -ForegroundColor Red
        }
    }

    Write-Host "[aicli] Ctrl+G hotkey registered (shell command generation)" -ForegroundColor DarkGray
} else {
    Write-Warning "[aicli] PSReadLine not available — Ctrl+G hotkey not installed."
    Write-Warning "        Install PSReadLine: Install-Module PSReadLine"
}
