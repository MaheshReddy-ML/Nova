# Experimental Design

One sentence: this skill makes NOVA better at planning studies before data is collected — choosing designs, randomizing, blocking, and laying out treatment combinations so results are interpretable.

## When to use

Use whenever someone is planning a study, asks how to assign subjects or samples to groups, mentions randomization, blocking, stratification, controls, factorial or fractional-factorial designs, design of experiments (DOE), screening many factors, response-surface optimization, crossover or repeated-measures or split-plot designs, cluster/group randomization, Latin squares, plate layouts, batch/run-order effects, replication vs. pseudoreplication, or sequential/adaptive/group-sequential designs. Trigger even for informal phrasings like "how should I set up this experiment," "how do I avoid confounding," "what's the best way to test these 6 factors," or "assign these mice to conditions." For computing sample size or power once the design is chosen, use statistical-power; for analyzing data already collected, use statistical-analysis.

## Workflow (numbered steps adapted to NOVA's tools)

1. **State the question, the unit, and the response.** What is randomized? What is measured? At what level is a true independent replicate? This determines everything.
2. **List nuisance factors** (batch, day, site, operator, position) — plan to block, stratify, or randomize across each.
3. **Pick the design** using the decision tree below:
   - Compare a few predefined conditions with independent units → completely randomized, or randomized block if a known nuisance factor exists.
   - Each unit can receive every condition in sequence with washout → crossover / repeated-measures (watch carry-over).
   - Only groups can be randomized (schools, clinics, litters) → cluster-randomized design.
   - Screen many factors (5+) to find the few that matter → fractional factorial or Plackett-Burman screening design.
   - Quantify main effects and interactions among a handful of factors → full 2^k factorial design.

## Quality bar (checklist)

- The experimental unit and the replication level are explicitly stated and match the treatment assignment level.
- Randomization is used to assign treatments; no convenience or first-come assignment.
- Known nuisance factors are blocked, stratified, or randomized across — never aligned with treatment.
- A concurrent control (and vehicle/sham where relevant) is included.
- Plate positions and run order are randomized or blocked to defeat drift and edge effects.
- Fractional factorial designs report resolution and alias structure; main effects are not confounded with interactions.
- Response-surface designs include axial or center runs to estimate curvature; a two-level factorial alone is not used to claim an interior optimum.
- Cluster-randomized designs treat the cluster, not the individual, as the unit of randomization and replication.
- The design, seed, schedule, and pre-specified analysis are saved to the owner's workspace via save_document.

## Pitfalls

- **Pseudoreplication:** 3 mice with 100 cells each is n = 3 mice, not n = 300 cells, for any treatment applied to the mouse. This single error invalidates a large share of published experiments.
- **Confounding by a nuisance variable:** running all treatment samples on Monday and all controls on Tuesday confounds treatment with day.
- **No or broken randomization:** convenience assignment lets confounders sneak in. Use a seeded schedule and follow it.
- **No proper control:** without a concurrent control, you cannot separate treatment effects from time, placebo, or handling.
- **Batch effects mistaken for biology:** never let batch align with condition; randomize or block across batches.
- **Edge/position effects on plates:** do not put all controls in column 1; randomize or block sample positions.