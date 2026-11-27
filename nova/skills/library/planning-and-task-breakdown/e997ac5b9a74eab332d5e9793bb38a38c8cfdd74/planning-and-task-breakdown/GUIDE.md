# planning-and-task-breakdown

One sentence: Breaking work into small, verifiable tasks with explicit acceptance criteria prevents tangled messes and enables reliable implementation, parallelization, and scope estimation.

## When to use

- You have a spec and need to break it into implementable units
- A task feels too large or vague to start
- Work needs to be parallelized across multiple agents or sessions
- You need to communicate scope to a human
- The implementation order isn't obvious

**When NOT to use:** Single-file changes with obvious scope, or when the spec already contains well-defined tasks.

## Workflow (numbered steps adapted to NOVA's tools)

1. **Enter Plan Mode:** Read the spec and relevant context. Identify existing patterns, map dependencies, and note risks. **Do NOT write code during planning.** Output is a plan document and task list, not implementation.

2. **Identify the Dependency Graph:** Map what depends on what. Implementation order follows the dependency graph bottom-up: build foundations first.

3. **Slice Vertically:** Build one complete feature path at a time rather than all database, then all API, then all UI. Each vertical slice delivers working, testable functionality.

4. **Write Tasks:** Each task follows this structure:

   ```markdown
   ## Task [N]: [Short descriptive title]

   **Description:** One paragraph explaining what this task accomplishes.

   **Acceptance criteria:**
   - [ ] [Specific, testable condition]
   - [ ] [Specific, testable condition]

   **Verification:**
   - [ ] Tests pass: [the repository's focused-test command]
   - [ ] Build succeeds: [the repository's build command]
   - [ ] Manual check: [description of what to verify]

   **Dependencies:** [Task numbers this depends on, or "None"]

   **Files likely touched:**
   - `src/path/to/file.ts`
   - `tests/path/to/test.ts`

   **Estimated scope:** [Small: 1-2 files | Medium: 3-5 files | Large: 5+ files]
   ```

5. **Order and Checkpoint:** Arrange tasks so dependencies are satisfied, each task leaves the system in a working state, verification checkpoints occur after every 2-3 tasks, and high-risk tasks are early. Add explicit checkpoints to the task list target.

## Quality bar (checklist)

- [ ] Every task has acceptance criteria
- [ ] Every task has a verification step
- [ ] Task dependencies are identified and ordered correctly
- [ ] Tasks are recorded in the task list target (default `tasks/todo.md`)
- [ ] No pre-existing incomplete plan was overwritten without explicit user confirmation
- [ ] No task touches more than ~5 files
- [ ] Checkpoints exist between major phases
- [ ] The human has reviewed and approved the plan

## Pitfalls

- Starting implementation without a written task list
- Overwriting a `tasks/plan.md` or `tasks/todo.md` that still has unchecked tasks for different work, without asking
- Writing `tasks/todo.md` when the project has designated an external tracker (or scattering tasks across both)
- Tasks that say "implement the feature" without acceptance criteria
- No verification steps in the plan
- All tasks are XL-sized
- No checkpoints between tasks
- Dependency order isn't considered