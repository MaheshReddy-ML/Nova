# Citation Management
## Citation Management
## Overview
## When to Use This Skill
- Searching for specific papers on Google Scholar or PubMed
- Converting DOIs, PMIDs, or arXiv IDs to properly formatted BibTeX
- Extracting complete metadata for citations (authors, title, journal, year, etc.)
- Validating existing citations for accuracy
- Cleaning and formatting BibTeX files
- Finding highly cited papers in a specific field
- Verifying that citation information matches the actual publication
- Building a bibliography for a manuscript or thesis
- Checking for duplicate citations
- Ensuring consistent citation formatting
## Core Workflow
## Phase 1: Paper Discovery and Search
## Phase 2: Metadata Extraction
## Phase 2.5: Metadata Enrichment via Web Search (MANDATORY)
## Phase 3: BibTeX Formatting
## Phase 4: Citation Validation
## Phase 5: Integration with Writing Workflow
## Reference Files
- [references/core_workflow.md](references/core_workflow.md): all five phases in full.
- [references/search_strategies.md](references/search_strategies.md): OpenAlex, Google Scholar, and PubMed query construction.
- [references/best_practices.md](references/best_practices.md): search, extraction, BibTeX quality, validation.
- [references/example_workflows.md](references/example_workflows.md): four end-to-end worked examples.
- [references/google_scholar_search.md](references/google_scholar_search.md), [references/pubmed_search.md](references/pubmed_search.md): advanced search syntax.
- [references/metadata_extraction.md](references/metadata_extraction.md), [references/bibtex_formatting.md](references/bibtex_formatting.md), [references/citation_validation.md](references/citation_validation.md): per-topic detail.
## Common Pitfalls to Avoid
1. **Single source bias**: Only using one database
- **Solution**: Search at least OpenAlex and PubMed, then merge with
2. **Accepting metadata blindly**: Not verifying extracted information
- **Solution**: Spot-check extracted metadata against original sources
3. **Ignoring DOI errors**: Broken or incorrect DOIs in bibliography
- **Solution**: Run validation before final submission
4. **Inconsistent formatting**: Mixed citation key styles, formatting
5. **Duplicate entries**: Same paper cited multiple times with different keys
- **Solution**: Use duplicate detection in validation
- **Solution**: Check the publisher record, distinguish missing from not applicable or not yet assigned, and log unresolved fields without inventing metadata.
- **Solution**: Check if preprints have been published, update to journal version
- **Solution**: Use proper escaping or Unicode in BibTeX
- **Solution**: Always run validation as final check
- **Solution**: Always extract from metadata sources using scripts
## Integration with Other Skills
## Literature Review Skill
- **Literature Review**: Multi-database systematic search and synthesis
- **Citation Management**: Metadata extraction and validation
1. Use literature-review for systematic search methodology
2. Use citation-management to extract and validate citations
3. Use literature-review to synthesize findings
4. Use citation-management to ensure bibliography accuracy
## Scientific Writing Skill