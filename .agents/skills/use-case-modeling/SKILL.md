---
name: use-case-modeling
description: Derive actor-goal-level use cases and relationships from a defined context model. Reference the context model instead of duplicating it, and produce a consistent use-case model.
metadata:
  short-description: Derive system use cases
---

# Use Case Modeling

## Overview

Use this skill to derive a **use-case model** based on a previously defined **context model**.

This skill must:
- Treat the context model as the **single source of truth**
- Avoid duplicating boundary or actor definitions
- Focus only on behavioral modeling

---

## Inputs

- Required:
  - `context-model.md`: Context model (system boundary and actors)
- Optional:
  - Existing use-case model artifact:
    - `use-case-model.md`: Use-case model (system behavior)

If an existing use-case model is present:

- DO NOT regenerate from scratch
- Treat it as the current working use-case model
- Refine, correct, and extend it incrementally
- Preserve:
  - existing use cases
  - actor associations
  - validated relationships (include/extend)
- NEVER remove or rename existing use cases unless explicitly instructed

If not provided:
- Ask the user
- Or infer and clearly mark assumptions

---

## Workflow

### 1. Load context model

- Extract:
  - System boundary
  - Actors

- Do NOT modify context model contents
- If issues are found:
  - Raise clarification questions

---

### 2. Identify use cases

- For each actor:
  - Identify goals achieved via the system

- Naming:
  - Verb–object format

- Each use case must:
  - Represent a complete goal
  - Deliver observable value
  - Be externally visible

---

### 3. Control abstraction level

- Prefer user-goal level

- Avoid:
  - Summary-level
  - Subfunction-level

---

### 4. Define relationships

- `used by`:
  - Actor names from context model only

- `includes`:
  - Mandatory reuse

- `extends`:
  - Optional/conditional behavior

---

### 5. Validate model

Check:

- All actors referenced exist in context model
- No new actors introduced
- No internal behaviors
- Proper granularity
- Consistent naming

---

### 6. Confirm and refine

- Present use cases
- Ask ≤ 3 questions
- Iterate

---

### 7. Capture assumptions and open questions

- Only include:
  - Use-case-specific uncertainties
- Do NOT repeat context assumptions

- Questions MUST be limited to the current modeling scope
- Do NOT ask questions about downstream models or future steps
- Only capture assumptions and open questions that directly affect the current artifact

---

### 8. Save the use-case model

- Use template:
  - `assets/use-case-model-template.md`

- Populate:
  - Context Reference (file path)
  - Use Cases
  - Assumptions (use-case level only)
  - Open Questions

- Rules:
  - Do NOT copy:
    - System Summary
    - Actors

- Save location:
  - Default: `use-case-model.md`

- After saving:
  - Report file path
  - Highlight:
    - new assumptions
    - inconsistencies with context

---

## Output Guidance

- Ask at most 3 clarification questions
- Keep output minimal and non-redundant
- Ensure strong consistency with context model

---

## Resources

- `assets/use-case-model-template.md`: Template for use-case modeling
- `context-model.md`: Context model artifact (system boundary and actors)