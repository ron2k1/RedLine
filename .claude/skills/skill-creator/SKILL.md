---
name: skill-creator
description: Create new skills, modify and improve existing skills, and measure skill performance. Use when users want to create a skill from scratch, update or optimize an existing skill, run evals to test a skill, benchmark skill performance with variance analysis, or optimize a skill's description for better triggering accuracy.
---

# Skill Creator

A skill for creating new skills and iteratively improving them.

The process of creating a skill:
1. Decide what you want the skill to do and roughly how it should do it
2. Write a draft of the skill
3. Create a few test prompts and run claude-with-access-to-the-skill on them
4. Help the user evaluate the results both qualitatively and quantitatively
5. Rewrite the skill based on feedback
6. Repeat until satisfied
7. Expand the test set and try again at larger scale

## Creating a Skill

### Capture Intent

Understand the user's intent. Extract answers from conversation history first.

1. What should this skill enable Claude to do?
2. When should this skill trigger? (what user phrases/contexts)
3. What's the expected output format?
4. Should we set up test cases to verify the skill works?

### Write the SKILL.md

- **name**: Skill identifier
- **description**: When to trigger, what it does. Include both what the skill does AND specific contexts for when to use it. Make descriptions a little "pushy" to avoid undertriggering.
- **the rest of the skill**

### Skill Writing Guide

#### Anatomy of a Skill

```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter (name, description required)
│   └── Markdown instructions
└── Bundled Resources (optional)
    ├── scripts/    - Executable code for deterministic/repetitive tasks
    ├── references/ - Docs loaded into context as needed
    └── assets/     - Files used in output (templates, icons, fonts)
```

#### Progressive Disclosure

1. **Metadata** (name + description) - Always in context (~100 words)
2. **SKILL.md body** - In context whenever skill triggers (<500 lines ideal)
3. **Bundled resources** - As needed (unlimited)

Keep SKILL.md under 500 lines. Reference files clearly from SKILL.md.

#### Writing Patterns

Prefer using the imperative form in instructions.

**Defining output formats:**
```markdown
## Report structure
ALWAYS use this exact template:
# [Title]
## Executive summary
## Key findings
## Recommendations
```

### Writing Style

Explain to the model WHY things are important rather than heavy-handed MUSTs. Use theory of mind. Start by writing a draft and then look at it with fresh eyes and improve it.

### Test Cases

Come up with 2-3 realistic test prompts. Save to `evals/evals.json`:

```json
{
  "skill_name": "example-skill",
  "evals": [
    {
      "id": 1,
      "prompt": "User's task prompt",
      "expected_output": "Description of expected result",
      "files": []
    }
  ]
}
```

## Improving the Skill

After running tests and getting user feedback:

1. **Generalize from the feedback** — create skills that work for many similar prompts, not just the test examples
2. **Keep the prompt lean** — remove things that aren't pulling their weight
3. **Explain the why** — explain the reasoning behind instructions rather than using rigid ALWAYS/NEVER
4. **Look for repeated work across test cases** — if all test cases resulted in writing similar helper scripts, bundle that script in `scripts/`

## Description Optimization

The description field is the primary mechanism that determines whether Claude invokes a skill. After creating or improving a skill, optimize the description for better triggering accuracy.

Create 20 eval queries — a mix of should-trigger and should-not-trigger. The queries must be realistic and specific, not abstract.

Good: Concrete, detailed prompts with file paths, personal context, column names, backstory.
Bad: Generic one-liners like "Format this data" or "Extract text from PDF".

## Core Loop

1. Figure out what the skill is about
2. Draft or edit the skill
3. Run claude-with-access-to-the-skill on test prompts
4. Evaluate the outputs with the user
5. Repeat until satisfied
6. Package the final skill
