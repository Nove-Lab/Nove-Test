---
name: domain-modeling
description: Derive a domain model consisting of entities, attributes, and relationships from a context model and use-case model. Define domain structure, establish relationships with cardinality, construct a domain narrative, and produce a consistent domain model artifact without duplicating upstream information.
metadata:
  short-description: Model domain entities and relationships
---

# Domain Modeling

## Overview

Use this skill to construct a **domain model** that captures:

- Core domain entities
- Their attributes
- Relationships between entities (including cardinality)
- A coherent domain-level narrative

This model provides:
- A shared vocabulary
- Structural understanding of the system
- A foundation for requirement specification

---

## Inputs

- Required:
  - `context-model.md`: Context model (system boundary and actors)
  - `use-case-model.md`: Use-case model (system behavior)
- Optional:
  - Existing domain model artifact:
    - `domain-model.md`: Domain model (entities and relationships)

If an existing domain model is present:

- DO NOT regenerate from scratch
- Treat it as the current working domain model
- Refine, correct, and extend it incrementally
- Preserve:
  - existing entities
  - established relationships
  - agreed-upon domain vocabulary
- NEVER remove or rename existing entities unless explicitly instructed

If not provided:
- Ask the user
- Or infer with clearly documented assumptions

---

## Workflow

### 1. Understand context and behavior

- Review:
  - System boundary
  - Actors
  - Use cases

- Extract:
  - Domain concepts implied by behavior
  - Objects actors interact with

---

### 2. Identify candidate entities

- Derive from:
  - Use-case descriptions
  - Domain inference
  - Common domain knowledge

- Include:
  - Domain concepts (e.g., Order, Product, Payment)

- Exclude:
  - UI elements (forms, pages)
  - Technical components (APIs, DBs, services)

- Important:
  - Entities are NOT limited to use cases
  - Add inferred entities when necessary

---

### 3. Refine entities

- Remove duplicates
- Normalize naming
- Ensure:
  - Clear domain meaning
  - Implementation independence

For each entity:
- Provide a concise description

---

### 4. Define attributes

- For each entity:
  - Identify key attributes

- Guidelines:
  - Include identifiers when appropriate
  - Focus on domain-relevant properties
  - Avoid excessive detail

---

### 5. Define relationships

- Identify relationships between entities

- For each relationship:
  - Source entity
  - Target entity
  - Relationship name (verb phrase)

---

### 6. Define cardinality

- Specify quantity constraints:

Examples:
- 1 to 1
- 1 to 0..*
- 1 to 1..*

- Use realistic domain assumptions
- If uncertain:
  - Document in Assumptions

---

### 7. Build domain description

- Write a concise narrative describing:
  - Overall domain flow
  - Key interactions between entities

Requirements:
- Every entity MUST be mentioned at least once
- Each entity MUST be bolded (e.g., **Order**, **Customer**)
- Keep it readable and high-level
- Do NOT enumerate all relationships or cardinalities

---

### 8. Build glossary

- Define key domain terms
- Ensure consistent vocabulary
- Align with entity definitions

---

### 9. Validate model quality

Check:

- All use-case-relevant concepts are represented
- No internal/technical artifacts included
- Relationships are meaningful and complete
- Cardinalities are reasonable
- Naming is consistent

---

### 10. Confirm and refine

- Present:
  - Entities
  - Relationships
  - Domain description

- Ask ≤ 3 focused questions
- Iterate until stable

---

### 11. Capture assumptions and open questions

- Record:
  - Inferred entities
  - Uncertain relationships
  - Ambiguous cardinalities

- Questions MUST be limited to the current modeling scope
- Do NOT ask questions about downstream models or future steps
- Only capture assumptions and open questions that directly affect the current artifact

---

### 12. Save the domain model

- Use template:
  - `assets/domain-model-template.md`

- Populate all sections

- Rules:
  - Do NOT duplicate:
    - Context model contents
    - Use-case model contents

- Save location:
  - Default: `domain-model.md`
  - Or user-specified path

- After saving:
  - Report file path
  - Highlight assumptions and open questions

---

## Output Guidance

- Ask at most 3 clarification questions at a time
- Prefer clarity over completeness when uncertain
- Maintain:
  - Structural consistency
  - Vocabulary consistency
  - Minimal redundancy

---

## Resources

- `assets/domain-model-template.md`: Template for domain modeling
- `context-model.md`: Context model artifact (system boundary and actors)
- `use-case-model.md`: Use-case model artifact (system behavior)