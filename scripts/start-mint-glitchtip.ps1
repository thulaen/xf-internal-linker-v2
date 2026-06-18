param(
    [string]$MintHost = "mint",
    [string]$MintRepoPath = "/home/mint-helper-01/xf-internal-linker-v2",
    [switch]$KeepWindowsCopies
)

Write-Error "This bridge is retired. GlitchTip now runs from Kubernetes/Dell-backed services, and MSI no longer starts Windows Postgres, Redis, or GlitchTip containers."
exit 2
