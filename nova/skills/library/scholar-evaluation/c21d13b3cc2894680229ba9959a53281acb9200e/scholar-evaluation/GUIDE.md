# Scholar Evaluation

This skill makes NOVA better at giving developmental, evidence-traceable feedback on scholarly works and auditing low-stakes research-assessment rubrics, without ranking people or influencing consequential decisions.

## When to use

Use this skill to review a paper, draft, protocol, literature synthesis, or research idea when the goal is formative improvement, not selection. It is appropriate for low-stakes assessment-process audits only. Never use it for hiring, promotion, tenure, admissions, grants, prizes, honors, awards, discipline, dismissal, sanctions, or any high-impact personnel decision. Never rank people or reduce a person to a composite score. Do not issue publication-readiness, accept/reject, or “top-tier” judgments.

## Workflow

1. Confirm allowed use and authorization. Record the developmental purpose, unit of assessment (`scholarly_work`), work type, stage, discipline, language, audience, authorized source location, data classification, accountable committee owner, conflicts and recusals, accessibility and accommodation process, appeal or correction route, and data purpose, access, retention, and deletion. Stop if the context is prohibited or requires unnecessary private data.
2. Define the construct before criteria. State what quality or support is being examined, excluded constructs, intended interpretation, contexts where it does not travel, evidence requirements, and known limitations. Start with values and disciplinary context, not available metrics.
3. Adapt and validate the rubric. Begin with `assets/rubric_template.json`, then obtain qualified disciplinary, assessment-methods, stakeholder, accessibility, privacy, and fairness review. The template records content validity as `not_established`; do not change that status without documented evidence for the exact intended use. Read `references/evaluation_framework.md` for construct, anchor, validity, and rater guidance.

## Quality bar

- Construct is defined and documented before any criteria or scores.
- Every scored criterion has evidence IDs, bounded uncertainty, and a local rationale reference.
- `missing` and `not_applicable` are never encoded as zero.
- Evidence-access date and work revision are frozen before rating.
- Correction/retraction and Crossmark status are checked for public papers and recorded as unresolved when no notice exists.
- Inter-rater disagreement is documented, not suppressed.
- Composite scores, if used, never override criterion evidence or qualified judgment.
- No output recommends acceptance, rejection, ranking, or any personnel or funding outcome.
- A qualified human committee reviews and signs off before any organizational release.

## Pitfalls

- Treating journal impact, h-index, citation counts, altmetrics, venue, institution, affiliation, or author reputation as quality evidence. These are prohibited scoring inputs.
- Conflating agreement with reliability, validity, fairness, or correctness.
- Interpreting the bundled uncertainty range as a confidence interval.
- Assuming normalization repairs incomplete evidence or that stable results under tested weights establish validity.
- Inferring novelty from a failure to find prior work.
- Using this skill for consequential decisions about people, even with a human-in-the-loop.
- Treating absence of a retraction notice as verification of soundness.
- Citing ScholarEval results as validated psychometrics or generalizing them beyond the documented study. The primary record is Moussa et al., *ScholarEval: Research Idea Evaluation Grounded in Literature*, arXiv:2510.16234v2, revised 2026-02-28; no peer-reviewed publication status was verified during the dated review.
- Omitting dissent or implying consensus in the final report.