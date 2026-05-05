---
description: Generate PRP from a proposal file
disable-model-invocation: true
---

# Generate PRP

## Feature file: $ARGUMENTS

Generate a complete PRP for general feature implementation with thorough research. Ensure context is passed to the AI agent to enable self-validation and iterative refinement. Read the proposal file first to understand what needs to be created, how the examples provided help, and any other considerations.

The AI agent only gets the context you are appending to the PRP and training data. Assume the AI agent has access to the codebase and the same knowledge cutoff as you, so it's important that your research findings are included or referenced in the PRP. The Agent has Websearch capabilities, so pass urls to documentation and examples.

## Invocation

Invoke with a proposal file path (e.g., `.ai/planning/prp/proposals/POST-IMPL-10_feature.md`):

1. **Read proposal** — extract ID, Title
2. **Generate standalone PRP** using `.ai/planning/prp/templates/prp_standalone.md`
3. **Save** to `.ai/planning/prp/instances/<ID>_<kebab-title>.md`

**CRITICAL: Proposal Content Preservation**

The proposal IS the specification. **Do NOT summarize, condense, or "extract" from proposals.** The PRP instance must:

1. **Preserve ALL proposal content** — every section, code block, table, example, and detail
2. **Be LARGER than the proposal** — the PRP adds structure (Success Criteria, Validation Loop, Step Checkpoints, Integration Test Assertions, Confidence Score) on top of the full proposal content
3. **Never abstract away implementation details** — if the proposal has complete function implementations, include them verbatim. If it has template placeholder tables, include them verbatim.

**Size check:** If your PRP instance is smaller than the proposal, you dropped content. Stop and include the missing sections.

The proposal author spent time writing detailed specifications. Your job is to add PRP structure, not to rewrite or summarize their work.

### ID Assignment for Multiple Engineers

When multiple engineers work simultaneously, assign ID blocks to avoid conflicts:
- Engineer A: POST-IMPL-10 to POST-IMPL-19
- Engineer B: POST-IMPL-20 to POST-IMPL-29
- Engineer C: POST-IMPL-30 to POST-IMPL-39

It is up to the team to establish rules that avoid overlap. Check existing proposals to determine next available ID in your assigned block.

## Research Process

1. **Codebase Analysis**
   - Search for similar features/patterns in the codebase
   - Identify files to reference in PRP
   - Note existing conventions to follow
   - Check test patterns for validation approach

2. **External Research**
   - Search for similar features/patterns online
   - Library documentation (include specific URLs)
   - Implementation examples (GitHub/StackOverflow/blogs)
   - Best practices and common pitfalls

3. **User Clarification** (if needed)
   - Specific patterns to mirror and where to find them?
   - Integration requirements and where to find them?

## PRP Generation

Use `.ai/planning/prp/templates/prp_standalone.md` as the template.

### Critical Context to Include and pass to the AI agent as part of the PRP
- **Documentation**: URLs with specific sections
- **Code Examples**: Real snippets from codebase
- **Gotchas**: Library quirks, version issues
- **Patterns**: Existing approaches to follow

### Implementation Blueprint
- Start with pseudocode showing approach
- Reference real files for patterns
- Include error handling strategy
- list tasks to be completed to fullfill the PRP in the order they should be completed

### Validation Gates (Must be Executable) eg for python
```bash
# Syntax/Style
ruff check --fix && mypy .

# Unit Tests
uv run pytest tests/ -v

```

*** CRITICAL AFTER YOU ARE DONE RESEARCHING AND EXPLORING THE CODEBASE BEFORE YOU START WRITING THE PRP ***

*** ULTRATHINK ABOUT THE PRP AND PLAN YOUR APPROACH THEN START WRITING THE PRP ***

## Output
Save as: `.ai/planning/prp/instances/<ID>_<kebab-title>.md`

## Quality Checklist
- [ ] All necessary context included
- [ ] Validation gates are executable by AI
- [ ] References existing patterns
- [ ] Clear implementation path
- [ ] Error handling documented

Score the PRP on a scale of 1-10 (confidence level to succeed in one-pass implementation using claude codes)

Remember: The goal is one-pass implementation success through comprehensive context.
