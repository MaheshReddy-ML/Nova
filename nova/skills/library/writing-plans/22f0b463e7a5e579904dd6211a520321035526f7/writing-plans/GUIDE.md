# writing-plans

One sentence: NOVA can break down multi-step tasks into clear, testable steps with exact file paths, signatures, and test cases, so engineers can implement without guessing.

## When to use

- When NOVA has a spec or requirements for a multi-step task
- Before any implementation begins
- When the engineer needs to understand exact interfaces and test expectations

## Workflow (numbered steps adapted to NOVA's tools)

1. **Analyze the spec** - Use `deep_research` to read the full specification document, noting all requirements, constraints, and success criteria
2. **Map file structure** - Determine which files will be created or modified and their responsibilities using `read_website` if referencing existing codebases
3. **Decompose into tasks** - Break the spec into independent subtasks, ensuring each task produces working, testable software on its own
4. **Size tasks appropriately** - Each task should be the smallest unit with its own test cycle; fold setup/configuration into the task that needs its deliverable
5. **Define exact interfaces** - For each task, specify exact file paths, function signatures, parameter types, and return types
6. **Write test-first steps** - Structure each task with: write failing test → verify failure → implement minimal code → verify passing → commit
7. **Document global constraints** - Copy project-wide requirements verbatim from spec (version floors, dependency limits, naming rules)
8. **Identify review focus** - List the five most likely failure modes from spec inputs not exercised by task tests
9. **Self-review the plan** - Check spec coverage, step granularity, type consistency, review focus, and proportion
10. **Save and handoff** - Save plan memory with `save_memory`, then present execution options to the owner

## Quality bar (checklist)

- [ ] Every spec requirement is traced to at least one task
- [ ] Each step lets the implementer write exactly one reasonable thing
- [ ] No step contains "TBD", "handle edge cases", or undefined references
- [ ] Types, signatures, and names are consistent across all tasks
- [ ] Review focus section covers the five most likely failure modes
- [ ] Plan length is proportional to spec (not several times longer)
- [ ] Code blocks are replaced with signatures, test names, and assertions
- [ ] Global constraints are copied verbatim from spec
- [ ] Task interfaces clearly state what consumes and produces

## Pitfalls

- Vague task boundaries where setup, configuration, and documentation are separate from the main deliverable
- Inconsistent function names or signatures across tasks (e.g., `clearLayers()` in one task, `clearFullLayers()` in another)
- Plan longer than the code it describes - this indicates the plan became a transcript rather than a guide
- "TBD" or undefined references in steps - each step must be unambiguous
- Missing review focus entries for spec-implied failure modes
- Not saving the plan to memory for future reference