# Planning System Directives

## File Locations
- **Tasks template**: `.ai/planning/templates/TASKS_TEMPLATE.md`
- **Work ledger**: `.ai/TASKS.md` (untracked, created from TASKS_TEMPLATE.md if missing)
- **PRP templates**: `.ai/planning/prp/templates/` (tracked)
- **Generated PRPs**: `.ai/planning/prp/instances/` (untracked)
- **Proposal seeds**: `.ai/planning/prp/proposals/` (untracked)
- **Archived PRPs**: `.ai/planning/prp/archive/` (untracked)

## Context Engineering Workflow
> **CRITICAL:** Steps marked [HUMAN] must NEVER be run by an AI agent under any circumstances.

1. [HUMAN] Collaborate with user to create proposal in `.ai/planning/prp/proposals/`
2. [HUMAN] Peer review proposal with `/peer-review-plan` — repeat until no issues
3. [HUMAN] Run `/generate-prp` with proposal file to create instance (instance must be larger than proposal)
4. [HUMAN] Peer review instance with `/peer-review-plan` — repeat until no issues
5. [HUMAN] Run `/execute-prp` — agent implements features from instance file
6. [AI] Update work ledger per `.ai/planning/templates/TASKS_TEMPLATE.md`

## Execution Discipline
- Use only dependencies present in the repo configuration or current PRP context
- Do not delete or overwrite existing code without explicit user direction
- Ask questions whenever requirements or context feel ambiguous—never invent details

## Testing & Completion
- Run validation commands specified in PRPs before declaring work complete
- Summarize changes and surface follow-up questions before task completion
