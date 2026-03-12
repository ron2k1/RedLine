---
name: simplify
description: Review changed code for reuse, quality, and efficiency, then fix any issues found. Use after writing or modifying code to catch over-engineering, dead code, and unnecessary complexity.
---

# Code Simplifier

Review recently changed files and simplify them. Focus on the delta — only files touched in the current branch or session.

## Step 1: Identify Changed Files

```bash
git diff --name-only HEAD~1 -- '*.py' 2>/dev/null || git diff --name-only --cached -- '*.py'
```

If no git changes, ask the user which files to review.

## Step 2: Analyze Each Changed File

For every changed `.py` file in `redline/`, check for:

### Complexity Smells (fix these)
- **Dead code**: unused imports, unreachable branches, commented-out blocks
- **Over-abstraction**: helpers/utilities used only once — inline them
- **Redundant validation**: checks that duplicate framework guarantees or caller contracts
- **Premature generalization**: feature flags, config options, or parameters nobody uses yet
- **Verbose patterns**: `if x is not None: return x` → `return x if x is not None else ...`
- **Unnecessary intermediate variables**: `result = func(); return result` → `return func()`
- **Duplicate logic**: same 3+ lines repeated — extract only if used 3+ times

### Style (flag but don't over-fix)
- Functions > 40 lines → consider splitting only if there's a natural seam
- Nested depth > 3 → consider early returns
- Boolean parameters → only flag if they create confusing call sites

### Do NOT touch
- Working code that's already clean
- Test files (unless explicitly requested)
- Comments that explain *why* (only remove *what* comments)
- Type annotations already present
- Import ordering (leave for linters)

## Step 3: Apply Fixes

Use the Edit tool to fix each issue. For each edit:
1. State the smell in one line
2. Show the fix
3. Move on

## Step 4: Verify

After all edits, run:

```bash
python -m pytest redline/tests/ -v
```

If tests fail, fix the regression before finishing.

## Rules

- **Minimum viable change**: if removing 2 lines makes code clearer, don't rewrite 20
- **No new abstractions**: simplifying means fewer moving parts, not different ones
- **Preserve behavior**: every simplification must be behavior-preserving
- **One file at a time**: finish one file before moving to the next
- **Senior developer standard**: would a senior dev accept this in code review?
