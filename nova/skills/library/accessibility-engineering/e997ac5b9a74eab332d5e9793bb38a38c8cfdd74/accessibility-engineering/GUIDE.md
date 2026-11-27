# Accessibility Engineering
## Accessibility Engineering
## Overview
## When to Use
- Before shipping a user-facing change that needs an accessibility audit
- When a11y issues are reported (e.g., "screen reader can't read this", "keyboard navigation broken")
- When auditing an existing interface for compliance
- When triaging axe-core or pa11y findings
- When remediating verified accessibility violations
## Workflow
## Phase 1: Route New UI Work
## Phase 2: Run Automated Audit
- **Critical** — Blocks screen reader access entirely (missing alt text on info images, empty buttons)
- **Serious** — Makes content difficult or impossible to access (low contrast, missing labels)
- **Moderate** — Causes confusion or extra effort (heading level skips, redundant ARIA)
- **Minor** — Cosmetic or progressive enhancement (missing lang attribute on inner elements)
## Phase 3: Manual Testing
1. Tab through every interactive element — can you see where you are?
2. Activate buttons and links with Enter/Space
3. Close modals with Escape
4. Navigate lists with Arrow keys
5. Verify no keyboard traps exist
1. Navigate by heading (VoiceOver: Ctrl+Option+Cmd+H) — is the structure logical?
2. Navigate by landmark (open the rotor with Ctrl+Option+U, choose Landmarks) — are regions labeled?
3. Navigate by link (open the rotor with Ctrl+Option+U, choose Links) — do link descriptions make sense out of context?
4. Interact with a form — are labels announced? Are error messages read?
5. Navigate a dynamic update — are changes announced?
1. Verify color contrast (4.5:1 text, 3:1 large text, 3:1 UI components)
2. Zoom to 200% — does layout break or overlap?
3. Test with forced colors / high contrast mode (Windows High Contrast)
4. Reduce motion (prefers-reduced-motion) — are animations disabled?
5. Test focus visibility — is the focus ring visible against all backgrounds?
## Phase 4: Fix Violations
1. **Fix the root cause** — Replace a `<div>` with `<button>`, add `<label>`, set `alt` text
2. **Add ARIA as bridge** — If native HTML can't express the pattern, add ARIA attributes
3. **Test the fix** — Re-run the automated check and manual verification
## Common Rationalizations
## Red Flags
- Elements that look clickable but aren't keyboard-focusable
- Color as the sole indicator of state (red for error, green for success)
- Focus outline removed without a visible replacement
- Missing labels on form inputs
- No heading hierarchy or skipped heading levels
- Empty or unlabeled buttons and links
- Modals that don't trap focus or restore focus on close
- No `alt` text on meaningful images (or `alt=""` missing on decorative ones)
- Touch targets that fail SC 2.5.8's 24x24 CSS px size-or-spacing requirement and do not qualify for an exception (AA; 44x44 is the AAA target, SC 2.5.5)
- Autoplaying video or audio without controls
- Low contrast text (especially on hover, disabled states, placeholders)
## See Also
- `references/shared/accessibility-checklist.md` — Quick reference for WCAG 2.2 AA
- `../frontend-ui-engineering/SKILL.md` — Building accessible components from the start
- `../../agents/accessibility-auditor.md` — Dedicated a11y audit persona for deep reviews
## Verification
- [ ] Automated audit passes with no Critical or Serious violations