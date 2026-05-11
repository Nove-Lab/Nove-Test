---
name: requirements-specification
description: Generate a structured requirement specification from system responsibility, use-case, and domain models. Decompose responsibilities into multiple concrete requirements, organize them into groups, maintain traceability, and produce a distributed requirement artifact structure.
metadata:
  short-description: Generate requirement specification
---

# Requirement Specification

## Overview

Use this skill to transform system responsibilities into a structured **requirement specification**.

This step:
- Decomposes system responsibilities into one or more concrete requirements
- Organizes requirements into logical groups
- Maintains traceability across all upstream models
- Produces a scalable, distributed artifact structure

---

## Inputs

- Required:
  - `context-model.md`: Context model (system boundary and actors)
  - `use-case-model.md`: Use-case model (system behavior)
  - `domain-model.md`: Domain model (entities and relationships)
  - `system-responsibility-model.md`: System responsibility model (functional responsibilities)
- Optional:
  - Existing requirement artifacts:
    - `requirements-specification/index.md`: Requirements index
    - `requirements-specification/groups/<group>.md`: Requiments specifications

If existing requirement files are present:

- DO NOT regenerate from scratch
- Treat them as the current working specification
- Update, refine, and extend them incrementally
- Preserve:
  - existing requirement IDs
  - existing statuses
  - approved requirements
- NEVER delete or overwrite approved requirements unless explicitly instructed

If not provided:
- Ask the user
- Or infer with assumptions

---

## Workflow

### 1. Understand system responsibilities

- Extract all responsibilities
- Understand:
  - related use cases
  - related entities

---

### 2. Decompose responsibilities into requirements

For each responsibility:

- Derive one or more requirements as needed

Rules:
- A responsibility MAY map to multiple requirements
- Each requirement must be:
  - atomic
  - testable
  - system-centric

Convert into:

The system shall <specific behavior>

Example:

Responsibility:
- process payment

Requirements:
- The system shall validate payment details
- The system shall authorize payment with external provider
- The system shall record payment transaction

---

### 3. Propose requirement grouping

Cluster requirements into logical groups based on:

- domain area
- related entities
- functional cohesion

Examples:
- Order Management
- Payment Processing
- User Management

---

### 4. Confirm grouping with user

- Present suggested groups
- Allow:
  - rename
  - merge
  - split

Do NOT finalize without confirmation

---

### 5. Assign requirements to groups

- Map each requirement to exactly one group
- Avoid duplication
- Ensure cohesion within each group

---

### 6. Derive non-functional requirements per group

For each group:

- Identify applicable constraints:

  - performance
  - reliability
  - security
  - usability

Rules:

- NFRs must be:
  - specific
  - measurable when possible
  - scoped to the group

Example:

- The system shall process orders within 2 seconds
- The system shall ensure payment data is encrypted in transit

---

### 7. Assign metadata

For each requirement:

- ID (globally unique, follow the naming rules in the template)
- priority (High / Medium / Low)
- status (Draft)

---

### 8. Maintain traceability

Each requirement must link to:

- source responsibility
- related use cases
- related entities

---

### 9. Validate requirements

Check:

- completeness (all responsibilities covered)
- correctness (no conflicting requirements)
- granularity (appropriately decomposed)
- traceability (clear lineage)

---

### 10. Generate artifacts

Create:

- `requirements-specification/index.md`
- `requirements-specification/groups/<group>.md`

Rules:

- Use a grouped directory structure
- All group files MUST be placed under `groups/`

- Each group file MUST contain BOTH:
  - functional requirements
  - non-functional requirements

- Do NOT separate non-functional requirements into a global file
- Do NOT duplicate upstream artifacts

---

### 11. Capture assumptions and open questions

- missing requirements
- unclear decomposition
- uncertain constraints

- Questions MUST be limited to the current modeling scope
- Do NOT ask questions about downstream models or future steps
- Only capture assumptions and open questions that directly affect the current artifact

---

### 12. Output summary

Report:

- created files
- total requirement count
- group structure
- key assumptions

---

## Output Guidance

- Ask at most 3 clarification questions at a time
- Prefer clarity over completeness when uncertain
- Maintain structured, non-redundant output

- All newly generated requirements MUST have status set to `Draft`
- After human review, instruct the user to update requirement status from `Draft` to `Approved`
- Clearly communicate that status transitions should follow: `Draft` → `Approved` → `Implemented` → `Verified`

---

## Resources

- `assets/requirements-index-template.md`: Template for requirements index
- `assets/requirements-group-template.md`: Template for requirements specification for each group
- `context-model.md`: Context model artifact (system boundary and actors)
- `use-case-model.md`: Use-case model artifact (system behavior)
- `domain-model.md`: Domain model artifact (entities and relationships)
- `system-responsibility-model.md`: System responsibility model artifact (system functional responsibilities)