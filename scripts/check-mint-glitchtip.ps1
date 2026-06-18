param(
    [string]$MintHost = "mint",
    [string]$MintRepoPath = "/home/mint-helper-01/xf-internal-linker-v2",
    [string]$BaseUrl = "http://10.10.10.91:1337",
    [string]$LoginEmail = $env:GLITCHTIP_LOGIN_EMAIL,
    [string]$LoginPassword = $env:GLITCHTIP_LOGIN_PASSWORD
)

Write-Error "This check is retired. GlitchTip now runs from Kubernetes/Dell-backed services; use .githooks/check-observability-stack.py instead."
exit 2
