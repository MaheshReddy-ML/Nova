---
name: web-motion-design
description: Web motion design for marketing and small-business landing pages. Use when adding entrance reveals, hero image motion, parallax, galleries, counters or hover feedback, choosing timing and easing, honouring reduced motion, and keeping motion within performance budgets.
license: MIT
metadata:
  author: NOVA
  version: "1.0"
---

# Web motion design

Motion on a landing page has three legitimate jobs: direct attention (what to look at first), explain change (what
just happened), and give the page a sense of quality and life. Anything else is decoration that costs performance and
accessibility. This playbook gives concrete values.

## 1. Purpose before effect

- Each motion answers "what does this help the visitor notice or understand?" If nothing, remove it.
- One signature moment per page (for example a slow hero image zoom). Everything else is quiet: short reveals and hover
  feedback.
- Never animate the main message so it is unreadable at first paint: the headline and primary button must be visible
  within ~300 ms.

## 2. Timing and easing

| Use | Duration | Easing |
| --- | --- | --- |
| Hover and press feedback | 150-250 ms | ease-out |
| Entrance reveal of a block | 600-900 ms | cubic-bezier(.2, .7, .2, 1) |
| Stagger between siblings | 60-100 ms, max ~450 ms total | same |
| Counter roll-up | 800-1200 ms | ease-out cubic |
| Hero Ken Burns | 18-30 s, alternate, scale 1 -> 1.06-1.1 | ease-in-out |
| Image hover zoom | 500-800 ms, scale <= 1.05 | ease-out |

- Distances are small: reveals travel 16-32 px. Large slides look cheap and cause motion sickness.
- Exits are faster than entrances. Never bounce or elastic on a business site unless the brand is playful.

## 3. Techniques

- Scroll reveals: IntersectionObserver adds a class once (unobserve after), threshold ~0.1, rootMargin bottom -5%.
  Never scroll event listeners for reveals.
- Parallax: at most 20-40 px of drift, only while in view, one requestAnimationFrame per scroll frame, image
  over-scaled ~1.1 inside an overflow-hidden frame so edges never show.
- Galleries/marquees: pause on hover and focus; never move text that must be read; provide a static layout.
- Counters: only for real, sourced numbers ("40+ workshops"), never years or invented stats; the final value is in the
  HTML so it is correct without JavaScript.

## 4. Accessibility and progressive enhancement

- Respect prefers-reduced-motion: reduce. Disable non-essential animation entirely (not just shorten it) and show all
  content in its final state.
- Content must be visible without JavaScript: hide-before-reveal styles apply only under a class that the script adds
  after it has checked the motion preference.
- Nothing auto-plays longer than 5 s without a way to pause, except very subtle background motion (WCAG 2.2.2).
- No flashing more than 3 times per second.

## 5. Performance budget

- Animate only transform-family properties (transform, translate, scale, rotate) and opacity: they run on the
  compositor and cause no layout shift (CLS 0).
- Never animate width, height, top, left, margin, box-shadow on large areas, or filter: blur on big images.
- Reserve image space with width/height or aspect-ratio so lazy images cause no shift.
- Motion script budget: under 3 KB, no libraries, no layout reads in loops, passive scroll listeners.
- Use will-change only on the one or two elements that animate continuously.
