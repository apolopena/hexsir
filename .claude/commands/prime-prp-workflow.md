---
description: Explain the PRP proposal workflow to prime a new session
disable-model-invocation: true
---

## Instructions

Read `.ai/AGENTS.md`.

Explain the PRP workflow to the human in plain, friendly language with emojis. Assume they are new. Be succinct — each step should be 2 bullet points max. No walls of text.

---

### 🗂️ What is a PRP?

**PRP = Planning Request Package**
   A self-contained unit of work an AI can fully digest and implement in one pass
   — a full PRD is too large for any single context window

---

### 🔄 The Workflow

**1 — 📝 Write the Proposal** *(You + AI)*
   Collaborate with AI to capture What, Why, and How
   Saved to `.ai/planning/prp/proposals/`

**2 — 🔍 Peer Review the Proposal** *(You + optional separate AI)*
   Share with a fresh AI session to catch ambiguity, gaps, redundant scope
   Update and repeat until clean (2–15 rounds) — use `/peer-review-plan`

**3 — ⚙️ Generate the Instance** *(You trigger it)*
   Run `/generate-prp <proposal_path>` — AI expands proposal into a detailed implementation plan
   Saved to `.ai/planning/prp/instances/` — always larger than the proposal

**4 — 🔍 Peer Review the Instance** *(You + optional separate AI)*
   Share with a fresh AI session to catch implementation gaps, missing context, test coverage
   Update and repeat until clean (2–15 rounds) — use `/peer-review-plan`

**5 — 🚀 Execute** *(You trigger it, AI does the work)*
   Run `/execute-prp <instance_path>` — AI implements, validates (lint → tests), marks done

---

> ⚠️ `/generate-prp` and `/execute-prp` are always triggered by you — never by AI autonomously.

---

### 🏷️ Naming Conventions

Proposals & instances: `<ID>_<kebab-case-title>.md`

📌 ID prefixes:
   POST-IMPL-X  — substantial new features
   MAINT-X      — fixes, tweaks, minor refactoring
   REFACT-X     — major refactoring efforts
   RAG-X        — RAG-related work
   WP-X         — initial project seed packages (used during project creation only)

Example: `POST-IMPL-57_deterministic-md-converter.md`

---

### 📁 Key Files

📋 `PLANNING.md`
   Founding doc: vision, goals, constraints + master work table for PRP generation

📝 `TASKS.md`
   Running ledger: all work completed or in progress — PRP packages and non-PRP tasks (MAINT-X, fixes, tweaks)

---

**End with:** "📋 PRP workflow primed!"

**CRITICAL:** Present everything in one message. Do not ask follow-up questions.
