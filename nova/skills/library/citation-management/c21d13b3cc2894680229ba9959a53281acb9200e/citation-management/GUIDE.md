# Citation Management

One sentence: makes NOVA better at finding, verifying, and formatting academic citations into accurate BibTeX bibliographies.

## When to use

Use when searching for papers, converting DOIs/PMIDs/arXiv IDs to BibTeX, extracting complete metadata, validating existing citations, deduplicating references, checking for published versions of preprints, or building a bibliography for a manuscript or thesis.

## Workflow (numbered steps adapted to NOVA's tools)

1. **Discover papers across multiple databases.** Coverage differs sharply; never rely on one source. Use `search_papers` for scholarly papers with abstracts, years, and citation counts. For biomedical topics, supplement with `web_search` targeting PubMed. Google Scholar is broad but scraped and unreliable; treat it as a supplement only.
2. **Convert identifiers to metadata.** For a DOI, PMID, PMCID, arXiv ID, or article URL, use `search_papers` or `deep_research` to read the publisher record and CrossRef/OpenAlex record. Extract authors, title, journal/venue, year, volume, issue, pages or article number, and DOI.
3. **Enrich incomplete metadata.** APIs routinely omit fields. After extraction, check OpenAlex or CrossRef against PubMed for missing fields. Online-first articles may lack volume/pages; use the article-number field where appropriate. Never invent pages, volume, or DOI. Record unavailable fields as not applicable in an audit log; add a rendered `note` only when useful or required by style.
4. **Format clean BibTeX entries.** Draft entries manually in Markdown using standard BibTeX entry types (`article`, `inproceedings`, `book`, etc.) and required fields. Use a consistent citation-key scheme (e.g., `AuthorYearTitle`). When merging sources, rekey so the same paper collapses to one entry keyed by DOI.
5. **Validate citations.** Check completeness (required fields present), venue conformance, DOI resolution, and agreement with the manuscript. Confirm duplicates by DOI and bibliographic identity, not title alone. Flag missing required fields, malformed years, and unresolved citations before submission.
6. **Save the bibliography.** Use `save_document` to store the final BibTeX or annotated reference list in the owner's workspace. Long deliverables must go into `save_document`, not spoken replies.

## Quality bar (checklist)

- [ ] At least two databases searched per topic
- [ ] Every citation has authors, title, year, venue, and DOI (or valid reason for absence)
- [ ] Metadata spot-checked against publisher record
- [ ] No invented pages, volume, or DOI; missing fields logged as not applicable
- [ ] Duplicates merged by DOI; single citation key per paper
- [ ] Preprints checked for published journal versions
- [ ] BibTeX keys validated and special characters escaped
- [ ] Final bibliography saved via `save_document`

## Pitfalls

- **Single-source bias:** One database misses papers. Always merge OpenAlex/CrossRef and PubMed results.
- **Blind metadata acceptance:** Publisher records control content; verify against the original source.
- **Ignoring DOI errors:** Unresolved DOIs break bibliographies. Validate before submission.
- **Inconsistent formatting:** Mixed key styles create confusion. Standardize keys and entry types.
- **Duplicate entries:** Same paper under different keys. Deduplicate by DOI.
- **Missing required fields:** Distinguish missing from not applicable or not yet assigned; never invent metadata.
- **Outdated preprints:** Citing a preprint when a published version exists. Check and update.
- **Manual BibTeX entry:** Typing by hand introduces errors. Always extract from metadata sources.
- **Shell injection risk:** Titles containing `$`, backticks, or quotes become shell syntax if pasted into commands. Never build shell strings from metadata.