Param(
  [string]$Repo = "raven-dev-ops/Executive_Assistant_AI_SaaS",
  [string]$Branch = "main"
)

$ErrorActionPreference = "Stop"

# Required checks should be job names as they appear in the PR checks UI.
# Keep this list in sync with workflow/job names under `.github/workflows/`.
$requiredContexts = @(
  "gitleaks",
  "prod-config",
  "perf-smoke",
  "review",
  "Python dependency audit",
  "Generate SBOM",
  "tests (3.11)",
  "tests (3.12)",
  "tests (3.13)"
)

$body = @{
  required_status_checks = @{
    strict = $true
    contexts = $requiredContexts
  }
  enforce_admins = $true
  required_pull_request_reviews = @{
    dismiss_stale_reviews = $true
    require_code_owner_reviews = $false
    required_approving_review_count = 1
  }
  restrictions = $null
  required_linear_history = $true
  allow_force_pushes = $false
  allow_deletions = $false
  required_conversation_resolution = $true
}

$json = $body | ConvertTo-Json -Depth 10

Write-Host "Applying branch protection for ${Repo}:${Branch}"
Write-Host "Required contexts:"
$requiredContexts | ForEach-Object { Write-Host " - $_" }

$json | gh api `
  -X PUT `
  "repos/$Repo/branches/$Branch/protection" `
  --input - | Out-Null

Write-Host "Done."
