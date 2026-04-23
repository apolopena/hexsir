### CRITICAL: SSH Git Commands
ALWAYS use `./scripts/git-ai.sh` for git commands requiring SSH (commit, push, pull, fetch, clone, remote, ls-remote, submodule). Prevents SSH askpass errors via keychain + adds AI attribution.

### GitHub Operations
CRITICAL: Mark agent (subagent_type=mark) is responsible for ALL GitHub write operations (PRs, issues, comments, releases).
Mark gathers context and dispatches .github/workflows/gh-dispatch-ai.yml with proper provenance.
