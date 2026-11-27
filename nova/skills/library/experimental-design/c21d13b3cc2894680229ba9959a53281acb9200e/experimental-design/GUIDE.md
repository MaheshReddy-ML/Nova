# Experimental Design
## Experimental Design
## Overview
- **Randomization** — assign treatments at random so that confounders, known and unknown, are balanced in expectation. This is what turns a comparison into a causal claim.
- **Replication** — independent repetition at the right level, so you can estimate variability and your effects aren't artifacts of a single unit. The most common fatal error is **pseudoreplication**: counting repeated measurements on the same unit as independent replicates.
- **Blocking / local control** — group similar units (by batch, day, site, litter) and randomize within blocks, removing that nuisance variation from the error term instead of letting it inflate noise.
## When to Use This Skill
- Planning any comparative experiment or trial and deciding how to assign units
- Randomizing subjects/samples to arms (simple, blocked, stratified, or cluster)
- Removing nuisance variation by blocking or stratification
- Designing multi-factor experiments: full or fractional factorial, screening designs
- Optimizing a response over continuous factors (response-surface designs)
- Within-subject / repeated-measures, crossover, split-plot, or Latin-square designs
- Cluster- or group-randomized designs (sites, clinics, classrooms, litters)
- Deciding the number and level of replicates and avoiding pseudoreplication
- Sequential, group-sequential, or adaptive designs with interim analyses
- Laying out plates/batches and randomizing run order to defeat drift
## Installation
## Choosing a design
- **Randomization, blocking, stratification, controls** → `references/randomization_and_blocking.md`
- **Factorial, fractional-factorial, screening, response-surface, DOE concepts (aliasing, resolution)** → `references/factorial_and_doe.md`
- **Crossover, repeated-measures, split-plot, Latin-square, cluster, nested designs** → `references/design_types.md`
- **Sequential, group-sequential, and adaptive designs (interim analyses)** → `references/sequential_and_adaptive.md`
## Generating the design
## The mistakes that ruin studies
1. **Pseudoreplication.** Treating repeated measurements of one unit as independent
2. **Confounding by a nuisance variable.** Running all treatment samples on Monday
3. **No or broken randomization.** Convenience assignment (first-come → treatment)
4. **No proper control.** Without a concurrent control (and, where relevant, a
5. **Batch effects mistaken for biology.** In omics especially, process samples in a
## Workflow
1. **State the question, the unit, and the response.** What is randomized? What is
2. **List nuisance factors** (batch, day, site, operator, position) — plan to block,
3. **Pick the design** using the decision tree and reference files.
4. **Decide replication** at the correct level (and get n from the
## Resources
## Scripts
## References
- `references/randomization_and_blocking.md` — randomization methods, blocking,
- `references/factorial_and_doe.md` — factorial and fractional designs, resolution
- `references/design_types.md` — completely randomized, randomized block, crossover,
- `references/sequential_and_adaptive.md` — group-sequential designs, alpha spending,
## Related skills
- **statistical-power** — required sample size / power for the design you've chosen.