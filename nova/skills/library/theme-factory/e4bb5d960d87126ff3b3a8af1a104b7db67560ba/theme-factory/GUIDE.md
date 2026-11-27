# theme-factory

This skill equips NOVA to style artifacts—slides, docs, reports, landing pages—with professional, cohesive themes. It provides curated color palettes and font pairings that ensure visual consistency and brand alignment across any document type.

## When to use

When an artifact needs polished styling but lacks a defined theme. Use it for slide decks requiring audience-appropriate colors, reports needing readable palettes, or landing pages demanding brand-consistent typography. It is also the go-to tool when a custom look is needed beyond the default options.

## Workflow

1. **List available themes**: Open `theme-showcase.pdf` so the user can visually compare the 10 preset themes. Do not alter the file; display it for selection.
2. **Prompt for choice**: Ask the user to select one of the shown themes (Ocean Depths, Sunset Boulevard, Forest Canopy, Modern Minimalist, Golden Hour, Arctic Frost, Desert Rose, Tech Innovation, Botanical Garden, Midnight Galaxy).
3. **Confirm selection**: Wait for explicit confirmation of the chosen theme.
4. **Apply the theme**: Read the selected theme's specifications from the `themes/` directory. Apply its hex colors and font pairings consistently across the artifact. Verify contrast ratios and readability on each slide or section.
5. **Create custom theme (if needed)**: If none of the presets fit, ask for a brief description of the desired mood or brand. Generate a new theme with a matching name and palette, show it for review, then apply it to the artifact.

## Quality bar

- Color palette uses accessible contrast (minimum 4.5:1 AA for normal text per WCAG).
- Font pairings establish clear hierarchy: a sans-serif display font for headers, a legible serif or clean sans for body text.
- The theme's visual identity remains consistent across all slides/pages—no mixed palettes or stray font choices.
- Hex codes are applied exactly as defined; no approximations.
- If a custom theme is generated, it receives a descriptive name (e.g., "Coastal Breeze," "Urban Pulse") and the user approves the palette before application.

## Pitfalls

- Applying a theme without checking contrast can produce unreadable text on certain backgrounds.
- Mixing fonts or colors from multiple themes breaks visual cohesion.
- Skipping the showcase step forces the user to guess theme names rather than see them.
- Generating a custom theme without a clear description risks misaligned colors or fonts.
- Applying themes to artifacts that already have established branding may clash with existing guidelines.