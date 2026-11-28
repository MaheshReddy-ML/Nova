# Accessibility Engineering

One sentence: Audits existing interfaces for WCAG 2.2 AA conformance and remediates verified violations using automated checks plus manual keyboard, screen reader, and visual testing.

## When to use

- Before shipping a user-facing change that needs an accessibility audit
- When accessibility issues are reported (e.g., screen reader can't read content, keyboard navigation broken)
- When auditing an existing interface for WCAG 2.2 AA compliance
- When triaging automated accessibility findings
- When remediating verified accessibility violations

Do not use for building new UI components from scratch; use frontend-ui-engineering for construction guidance. Do not use for backend-only changes, CLIs, or library code with no UI output.

## Workflow

1. Route new UI work. For component construction, interaction patterns, and focus-management guidance, use frontend-ui-engineering. Return to this workflow once an interface exists and needs auditing or remediation.
2. Run automated audits. Use web_search or deep_research to locate current guidance on running axe-core or pa11y against the target URL or local server. Save any reports with save_document. Review violations grouped by severity:
   - Critical — blocks screen reader access entirely (missing alt text on informative images, empty buttons)
   - Serious — makes content difficult or impossible to access (low contrast, missing labels)
   - Moderate — causes confusion or extra effort (heading level skips, redundant ARIA)
   - Minor — cosmetic or progressive enhancement (missing lang attribute on inner elements)
   For each violation, verify it is a real issue, not a false positive, by inspecting the element with read_website or browser inspection.
3. Complete manual testing. Automated checks are a smoke test, not proof of conformance.
   - Keyboard audit: Tab through every interactive element; verify visible focus, Enter/Space activation, Escape to close modals, arrow-key list navigation, and no keyboard traps.
   - Screen reader audit: navigate by heading, landmark, and link; verify link text makes sense out of context; check that form labels and error messages are announced; verify dynamic updates are announced.

## Quality bar

- Automated audit passes with no Critical or Serious violations
- All interactive elements are keyboard accessible (Tab, Enter, Escape, Arrow keys)
- Screen reader navigation by heading, landmark, and link verified with a named browser and assistive technology pair, or recorded as manual and untested — never reported as verified without testing
- Focus order matches visual order
- Color contrast passes 4.5:1 text / 3:1 large text / 3:1 UI components
- All form inputs have associated labels
- All images have appropriate `alt` text
- Dynamic content changes are announced (aria-live)
- Page is usable at 200% zoom with no content loss
- Touch targets satisfy SC 2.5.8's 24x24 CSS px size-or-spacing requirement or a normative exception (AA); 44x44 is the enhanced AAA target (SC 2.5.5)

## Pitfalls

- Treating automated tools as proof of conformance; they cannot check keyboard or screen reader behavior
- Delaying remediation with "we'll fix accessibility later," which compounds across components and can create legal liability
- Using `aria-label` everywhere instead of semantic HTML first; ARIA is a bridge, not a foundation
- Assuming internal tools are exempt; they are subject to the same regulations
- Removing focus outlines without a visible replacement
- Using color as the sole indicator of state (red for error, green for success)
- Assuming a passing axe-core or Lighthouse score means the interface is accessible
- Reporting manual checks as verified without a named browser and assistive technology pair