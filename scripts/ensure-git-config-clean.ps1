# Ensure .git/config does not contain the [extensions] worktreeConfig = true block.
# Gemini CLI and Gemini Antigravity silently stop responding when that block is present.
# See: C:\Users\goldm\.claude\plans\can-we-have-a-robust-pudding.md (Part 6 - Gemini guard).
# Idempotent; safe to run anytime, even mid-session.

param()
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$gitConfigPath = [System.IO.Path]::GetFullPath((Join-Path $scriptDir "..\.git\config"))

if (-not (Test-Path $gitConfigPath)) {
    Write-Host "ensure-git-config-clean: .git/config not found - skipping."
    exit 0
}

$original = Get-Content $gitConfigPath -Raw
if ([string]::IsNullOrEmpty($original)) {
    exit 0
}

$content = $original

# 1. Strip "worktreeConfig = true" lines (tolerate varied whitespace).
$content = [regex]::Replace($content, "(?im)^[ \t]*worktreeConfig[ \t]*=[ \t]*true[ \t]*\r?\n", "")

# 2. Remove any [extensions] header that is now empty (immediately followed by next section header or EOF).
$content = [regex]::Replace($content, "(?ims)^\[extensions\][ \t]*\r?\n(?=[ \t]*(\[|\z))", "")

# 3. Collapse triple-or-more newlines down to a single blank line.
$content = [regex]::Replace($content, "(?s)(\r?\n){3,}", "`r`n`r`n")

if ($content -ne $original) {
    # Preserve LF line endings to match git config convention; write without BOM.
    $content = $content -replace "`r`n", "`n"
    [System.IO.File]::WriteAllText($gitConfigPath, $content, (New-Object System.Text.UTF8Encoding $false))
    Write-Host "ensure-git-config-clean: stripped [extensions] worktreeConfig=true from .git/config (Gemini guard)."
} else {
    Write-Host "ensure-git-config-clean: .git/config already clean."
}
