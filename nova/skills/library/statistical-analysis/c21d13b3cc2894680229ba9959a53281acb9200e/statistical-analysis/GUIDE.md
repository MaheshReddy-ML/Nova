# statistical-analysis

One sentence: Guided statistical analysis for research data—test selection, assumption checking, effect sizes, power analysis, Bayesian alternatives, and APA-formatted reporting.

## When to use

- Conducting hypothesis tests (t-tests, ANOVA, chi-square, non-parametric)
- Performing regression or correlation analyses
- Running Bayesian statistical analyses
- Checking statistical assumptions and diagnostics
- Calculating effect sizes and conducting power analyses
- Reporting statistical results in APA format
- Analyzing experimental or observational data for research

## Workflow (numbered steps adapted to NOVA's tools)

1. **Frame the question before touching data.** State the hypothesis, outcome and predictor variables, and the design (independent vs. paired, number of groups). Specify the target effect, sampling unit, dependence, contrasts and multiplicity family before outcome-driven selection. Label adaptive exploration explicitly.
2. **Inspect the data.** Per group: n, mean, SD, median, missing values. Plot the raw data (histograms or box plots) before any test. Unequal group sizes, missingness, floor/ceiling effects, and outliers all change what test is appropriate — surface them to the user rather than silently working around them.
3. **Select the test** using the quick reference below, or `references/test_selection_guide.md` for designs beyond the basics (counts, time-to-event, reliability, factorial).
4. **Check assumptions** with `scripts/assumption_checks.py`. Interpret plots and screens alongside the design and estimand; do not switch tests automatically at a diagnostic p-value threshold. Report justified sensitivity analyses and any departures from the plan.
5. **Run the test** and always compute the effect size alongside it — a p-value assesses incompatibility with the null model; the effect estimate and its uncertainty support judgments about practical importance.
6. **Report** using the APA templates below, including descriptives, exact statistics, effect sizes with CIs, and the assumption checks performed.

If the user only needs one step (e.g., "how many participants do I need?"), jump straight to that section — but still confirm the design assumptions the calculation rests on.

## Quality bar (checklist)

- Hypothesis, variables, and design are stated before data inspection
- Raw data plotted before any test is chosen
- Test selected via prespecified criteria, not p-hacking
- Assumptions checked and reported; no automatic test-switching at p < .05
- Effect size computed and reported with confidence interval for every test
- APA-style report includes descriptives, exact statistics, effect sizes, assumption checks, and all planned analyses
- Multiple comparisons corrected when running families of tests
- Non-significant findings included; sensitivity analysis run if study was underpowered

## Pitfalls

- **Testing until something works:** Switching tests, subgroups, or outlier-removal schemes until p < .05 invalidates the p-value and constitutes p-hacking.
- **Assuming n = 30 guarantees robustness:** Tail weight, skewness, imbalance, dependence, and the target estimator matter more than sample size.
- **Non-significant Shapiro/Levene results do not verify assumptions:** A non-rejection does not confirm normality or equal variance.
- **Using observed (post-hoc) power:** It is a deterministic function of the p-value and is circular; always run a sensitivity analysis instead.
- **Reporting only significant findings:** Omitting non-significant results is cherry-picking; every planned analysis must appear in the report.
- **Ignoring multiplicity:** Running multiple tests without correction inflates Type I error; specify which correction (Tukey, Holm, Benjamini-Hochberg) was used.
- **Bayes factor misinterpretation:** Posterior probability statements are not Bayes factors; specify likelihood, prior, and comparison explicitly when using Bayesian methods.