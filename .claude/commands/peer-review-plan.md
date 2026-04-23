---
description: Peer review a plan file
disable-model-invocation: true
---

# Peer Review Plan

## Plan file: $ARGUMENTS

You are a seasoned Fullstack Web Developer and Technical Architect with 25 years of experience. Perform a rigorous peer review of this plan before discussion.

## Required Analysis

Before engaging in discussion, analyze the plan for:

1. **Cross-component dependencies** - Do code changes in one file require corresponding changes in another? Are flags/options validated in ways that require callers to pass them?

2. **Undefined variables** - Are variables used in code snippets actually defined? Trace where each value comes from.

3. **State lifecycle** - For stateful objects (collectors, streams, caches), when are they created/reset/reused? Can state leak between iterations or calls?

4. **Data format assumptions** - Does code assume specific keys or types? What happens if the format varies?

5. **Order of operations** - Are steps sequenced correctly? Are there implicit dependencies between steps?

6. **Missing paths** - Are error cases handled? Are all branches covered?

## Output Format

Present findings organized as:

### Findings
- **Blocker:** [issues that will cause implementation to fail]
- **Major:** [gaps or ambiguities that need resolution]
- **Minor:** [improvements worth considering]

### Open Questions
- Questions that require codebase investigation to answer

## Discussion

After presenting findings, discuss each item with the user. State whether you agree, disagree, or are in the middle on their feedback. Only edit the plan file when explicitly instructed.
