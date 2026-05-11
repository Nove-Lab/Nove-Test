---
name: context-modeling
description: Define the system boundary and identify external actors for a software system from a user's system goal, product idea, or requirements sketch. Classify actors, iteratively confirm with the user, and save a structured context model using a dedicated template.
metadata:
  short-description: Define system boundary and actors
---

# Context Modeling

## Overview

Use this skill to define the **system boundary** and identify **external actors**.

This produces a **context model artifact**, which serves as the foundation for:
- use-case modeling
- domain modeling
- requirement specification

---

## Inputs

- Required:
  - User-provided system description, product idea, or requirements sketch
- Optional:
  - Existing context model artifact:
    - `context-model.md`: Context model (system boundary and actors)

If an existing context model is present:

- DO NOT regenerate from scratch
- Treat it as the current working context model
- Refine, correct, and extend it incrementally
- Preserve:
  - validated system boundary
  - confirmed actors
- NEVER remove or rename existing actors unless explicitly instructed

If not provided:
- Ask the user for:
  - system purpose
  - target users
  - external systems
- Or proceed with reasonable assumptions and document them

---

## Workflow

### 1. Gather system context

- If the system is not described, ask for:
  - System purpose
  - Target users
  - External integrations
  - Operating environment

- Proceed with assumptions if needed
- Record them explicitly

---

### 2. Define system boundary

- Clearly define:
  - What is inside the system
  - What is outside

- Rules:
  - Actors must be outside the boundary
  - Internal components must not appear as actors

- If unclear:
  - Infer boundary
  - Record under **Assumptions**

---

### 3. Identify actors

- Include only:
  - External human roles
  - External systems

- Exclude:
  - Internal services, DB, UI components

- Naming:
  - Use role-based names

- For each actor:
  - Provide description
  - Explain interaction purpose
  - Specify parent actor if a generalization relationship exists

---

### 4. Classify actors

- Primary actor: initiates interaction
- Supporting actor: provides services
- Offstage actor: indirect interest

---

### 5. Validate model

Check:

- Boundary correctness
- Actor clarity
- Naming consistency

---

### 6. Confirm and refine

- Present boundary + actors
- Ask ≤ 3 focused questions
- Iterate until stable

---

### 7. Capture assumptions and open questions

- Record:
  - Boundary decisions
  - Missing knowledge

- Questions MUST be limited to the current modeling scope
- Do NOT ask questions about downstream models or future steps
- Only capture assumptions and open questions that directly affect the current artifact

---

### 8. Save the context model

- Use template:
  - `assets/context-model-template.md`

- Output rules:
  - Use Markdown tables
  - Keep structure unchanged

- Save location:
  - User-specified path if provided
  - Otherwise: `context-model.md`

- After saving:
  - Report file path
  - Summarize assumptions
  - Highlight open questions

---

## Output Guidance

- Ask at most 3 clarification questions at a time
- Prefer progress with explicit assumptions
- Ensure output is structured and reviewable

---

## Resources

- `assets/context-model-template.md`: Template for context modeling