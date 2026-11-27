# venue-templates

One sentence: NOVA can locate official author instructions, verify current page limits and anonymity rules, and adapt bundled LaTeX scaffolds to any journal, conference, or grant format without relying on stale templates.

## When to use

Use this skill when NOVA must locate official journal or conference author instructions, check page limits, required sections, anonymity rules, or citation style; choose and adapt a bundled LaTeX scaffold for drafting; prepare NSF, NIH, DOE, DARPA, or foundation proposal documents; design a research poster after checking event-specific dimensions; adapt prose to a venue's audience and reviewer expectations; or inspect a PDF's page count and embedded fonts.

## Workflow

1. **Resolve the exact target**: Ask for or derive venue, year/cycle, track, document type (e.g., research article, R01), submission stage, and authoring format (LaTeX or Word). Do not combine rules from similarly named venues or tracks.

2. **Consult the right reference**: Open the appropriate reference file (e.g., `references/conferences_formatting.md` for conferences, `references/grants_requirements.md` for grants) to summarize current rules. Note that reference files summarize rules but do not override the current official source.

3. **Capture a compliance note**: Before editing, write a short note in the working document or task log recording the target, official source URL, date checked, main-text limit, references/appendices allowance, anonymity status, and official template name.

4. **Start from the official template**: For annual conferences and publisher-managed workflows, download the template from the official source, keep its class/style files unchanged, and add content without overriding margins, font sizes, spacing, or headers. For grants, many components are entered or uploaded separately; do not submit a combined bundled `.tex` file as if it were an agency-issued form.

5. **Validate manually and mechanically**: Verify main-text and total-file page rules, font, margin, line-spacing, and paper-size rules, anonymity and metadata, required sections and disclosures, figure/table placement and accessibility, reference and supplemental-material treatment, and source-package and PDF requirements. A zero exit status means no automated failure was found; manual and skipped inspections still require attention.

## Quality bar

- [ ] Exact venue, year/cycle, track, article type, and stage identified
- [ ] Official source URL recorded with date checked
- [ ] Official template or form used where required
- [ ] Page-limit scope understood, including excluded sections
- [ ] Required statements, checklists, and disclosures present
- [ ] Blind-review files and PDF metadata checked for identity leaks
- [ ] Figures and tables are legible and accessible
- [ ] References, appendices, and supplements follow current rules
- [ ] PDF and source package compile cleanly
- [ ] Submission portal preview reviewed before final submission

## Pitfalls

- Never infer a current style-file name by changing the year in an old filename.
- Never present a generic scaffold as an official venue template.
- Do not combine `--venue` and `--max-pages` in validation; use an explicit limit for a different year, track, stage, or solicitation.
- Do not apply a publisher-wide template when the journal provides its own Guide for Authors.
- Do not submit a combined bundled `.tex` file as an agency-issued form for grants.
- Do not treat bundled files as copies of official templates unless explicitly stated.
- Do not add links to assets that are not bundled in this skill.
- Do not retain unverified numerical limits when official sources are inaccessible; update helper presets and examples together and increment `metadata.version`.