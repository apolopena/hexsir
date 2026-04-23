### Verify Before Asserting
When answering questions, think before responding. If you're not certain, say so. Never give a confident answer you haven't verified. A wrong confident answer costs more than a slow correct one.

When a test fails, read the full error output before diagnosing. Do not guess at the cause from truncated messages.

When adding flags or subprocess calls, test that the wiring works across the full call chain.

### Stale Context
When a discrepancy emerges between your context and the user's, verify your side at its source before asserting — do not default to trusting prior-turn context.

### CRITICAL: Documentation
Before starting any task, read `docs/README.md`. It is the index to all project documentation — conventions, standards, workflows, and patterns. Follow the directory to determine which docs are relevant to your task. Do not skip this step.

### Git: Planning Artifacts
Files in .ai/scratch/ and .ai/planning/prp/{instances,proposals,archive,abandoned}/ are gitignored. Do not attempt to commit them.

### Commit Messages
<60 chars, brief, imperative mood

### AskUserQuestion Tool
Never use this tool. Ask questions directly in response text.

### Planning System
When using `/generate-prp` or `/execute-prp`, read `.ai/AGENTS.md` for complete planning workflow directives.

### Changelog
When asked to update the changelog, dispatch the Pedro agent (subagent_type=Pedro).

### CRITICAL: SSH Git Commands
ALWAYS use `./scripts/git-ai.sh` for git commands requiring SSH (commit, push, pull, fetch, clone, remote, ls-remote, submodule). Prevents SSH askpass errors via keychain + adds AI attribution.

### GitHub Operations
CRITICAL: Mark agent (subagent_type=mark) is responsible for ALL GitHub write operations (PRs, issues, comments, releases).
Mark gathers context and dispatches .github/workflows/gh-dispatch-ai.yml with proper provenance.
