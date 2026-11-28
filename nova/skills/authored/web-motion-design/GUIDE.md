# Web motion design

Motion should direct attention, explain change and signal quality; anything else is cost.

## Principles
- One signature moment per page (e.g. a slow hero photo zoom); everything else stays quiet.
- The headline and primary button are readable at first paint; never hide the main message behind an animation.
- Plan copy and sections so motion has something meaningful to reveal: a clear hero, a set of offerings that can
  stagger in, real numbers (only if they are in the facts) that can count up.

## Values
- Hover/press feedback 150-250 ms ease-out; block reveals 600-900 ms with cubic-bezier(.2,.7,.2,1), travel 16-32 px.
- Stagger siblings 60-100 ms, total under ~450 ms. Hero Ken Burns 18-30 s, scale 1 to 1.06-1.1, alternate.
- Image hover zoom at most 1.05. Parallax drift at most 20-40 px, only while in view.
- Counters only for real sourced counts ("40+ workshops"), never years or invented statistics.

## Accessibility
- prefers-reduced-motion: reduce turns non-essential motion off and shows final states.
- Content is visible without JavaScript; reveal styles apply only after the script checks the preference.
- Nothing that must be read keeps moving; no flashing.

## Performance
- Animate only transform/translate/scale and opacity (compositor-only, zero layout shift).
- Reserve image space (width/height or aspect-ratio); IntersectionObserver, not scroll handlers, for reveals.
- Tiny script, no libraries, passive listeners, will-change only on continuously animated elements.
