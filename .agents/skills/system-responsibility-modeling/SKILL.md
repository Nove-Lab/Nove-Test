---
name: system-responsibility-modeling
description: Derive system responsibilities from a use-case model and domain model. Transform actor-driven behaviors into system-centric responsibilities, map them to use cases and domain entities, and produce a structured system responsibility model without duplicating upstream artifacts.
metadata:
  short-description: Derive system responsibilities
---

# System Responsibility Modeling

## Overview

Use this skill to transform **use cases (actor goals)** into **system responsibilities (system actions)**.

This model:
- Defines what the system must do internally
- Bridges use-case modeling and requirement specification
- Connects behavior with domain structure

---

## Inputs

- Required:
  - `context-model.md`: Context model (system boundary and actors)
  - `use-case-model.md`: Use-case model (system behavior)
  - `domain-model.md`: Domain model (entities and relationships)
- Optional:
  - Existing system responsibility model artifact:
    - `system-responsibility-model.md`: System responsibility model (functional responsibilities)

If an existing system responsibility model is present:

- DO NOT regenerate from scratch
- Treat it as the current working system responsibility model
- Refine, correct, and extend it incrementally
- Preserve:
  - existing responsibilities
  - mappings to use cases
  - mappings to domain entities
- NEVER remove or rename existing responsibilities unless explicitly instructed

If not provided:
- Ask the user
- Or infer with clearly documented assumptions

---

## Workflow

### 1. Understand inputs

- Review:
  - Use cases
  - Domain entities

- Identify:
  - Objects manipulated by the system
  - Implied internal system actions

---

### 2. Derive system responsibilities

For each use case:

- Decompose actor-level behavior into system-level actions

Examples:
- validate order data
- calculate total amount
- create order
- initiate payment

---

### 3. Normalize responsibilities

Ensure each responsibility:

- Uses **verb–object format**
- Represents a **single, atomic system action**
- Is **implementation-independent**

Avoid:

- UI actions (e.g., click button)
- Technical details (e.g., call API, write DB)
- Actor-centric phrasing

---

### 4. Consolidate responsibilities

- Merge duplicates across use cases
- Identify shared responsibilities
- Ensure each responsibility is defined only once

---

### 5. Map responsibilities to use cases

For each responsibility:

- List all related use cases

Rules:
- Do NOT duplicate responsibility definitions per use case
- Maintain many-to-many relationships

---

### 6. Map responsibilities to domain entities

For each responsibility:

- Identify related entities from the domain model

Rules:
- All referenced entities must exist in `domain-model.md`
- Do NOT introduce new entities without justification
- If needed, record in Assumptions

---

### 7. Validate model quality

Check:

- Coverage:
  - All use cases are supported by responsibilities

- Consistency:
  - All entities referenced exist in domain model

- Granularity:
  - Responsibilities are neither too broad nor too fine-grained

- Perspective:
  - All responsibilities are system-centric

---

### 8. Confirm and refine

- Present responsibility table
- Ask ≤ 3 focused questions
- Iterate until stable

---

### 9. Capture assumptions and open questions

- Record:
  - Inferred responsibilities
  - Uncertain mappings
  - Missing behaviors

- Questions MUST be limited to the current modeling scope
- Do NOT ask questions about downstream models or future steps
- Only capture assumptions and open questions that directly affect the current artifact

---

### 10. Save the system responsibility model

- Use template:
  - `assets/system-responsibility-model-template.md`

- Populate:
  - Responsibilities table
  - Notes
  - Assumptions
  - Open Questions

- Rules:
  - Do NOT duplicate:
    - context model
    - use-case model
    - domain model

- Save location:
  - Default: `system-responsibility-model.md`
  - Or user-specified path

- After saving:
  - Report file path
  - Highlight key assumptions and gaps

---

## Output Guidance

- Ask at most 3 clarification questions at a time
- Prefer clarity over completeness when uncertain
- Maintain:
  - Consistency with upstream models
  - Minimal redundancy
  - Structured output

---

## Resources

- `assets/system-responsibility-model-template.md`: Template for system responsibility modeling
- `context-model.md`: Context model artifact (system boundary and actors)
- `use-case-model.md`: Use-case model artifact (system behavior)
- `domain-model.md`: Domain model artifact (entities and relationships)