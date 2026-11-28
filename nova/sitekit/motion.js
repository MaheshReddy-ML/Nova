// NOVA site kit motion layer. Progressive enhancement: the page is complete without this file, and nothing here
// runs for visitors who ask for reduced motion. Only transform/translate/scale and opacity animate (no layout shift).
(() => {
  const form = document.querySelector(".demo-form");
  if (form) form.addEventListener("submit", (event) => {
    event.preventDefault();
    form.reset();
    form.querySelector('[role="status"]').textContent = "Concept preview: nothing was sent.";
  });

  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
  if (reduce.matches || !("IntersectionObserver" in window)) return;
  const root = document.documentElement;
  root.classList.add("motion");
  const reveal = (element) => element.classList.add("is-in");
  const showAll = () => document.querySelectorAll("[data-reveal], [data-reveal-group]").forEach(reveal);
  window.addEventListener("beforeprint", showAll);
  reduce.addEventListener?.("change", () => { showAll(); root.classList.remove("motion"); });

  const seen = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      reveal(entry.target);
      seen.unobserve(entry.target);
      entry.target.querySelectorAll("[data-count]").forEach(count);
    }
  }, { rootMargin: "0px 0px -6% 0px", threshold: 0.08 });
  document.querySelectorAll("[data-reveal], [data-reveal-group]").forEach((element) => seen.observe(element));

  // Counters: the real number is already in the HTML; count up to it once, ~0.9 s, ease-out.
  function count(element) {
    const target = Number(element.dataset.count);
    const suffix = element.textContent.replace(/^\d+/, "");
    if (!target) return;
    const start = performance.now();
    const step = (now) => {
      const progress = Math.min(1, (now - start) / 900);
      element.textContent = Math.round(target * (1 - Math.pow(1 - progress, 3))) + suffix;
      if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  // Subtle parallax: the story photo drifts at most 28 px while it is on screen; one rAF per frame, no layout reads
  // beyond a single getBoundingClientRect.
  const drifting = new Set();
  const parallax = new IntersectionObserver((entries) => {
    for (const entry of entries) entry.isIntersecting ? drifting.add(entry.target) : drifting.delete(entry.target);
  });
  document.querySelectorAll("[data-parallax]").forEach((element) => parallax.observe(element));
  let pending = false;
  const frame = () => {
    pending = false;
    for (const element of drifting) {
      const box = element.getBoundingClientRect();
      const offset = (box.top + box.height / 2 - innerHeight / 2) / (innerHeight + box.height);
      const image = element.querySelector("img");
      if (image) image.style.translate = `0 ${(offset * -56).toFixed(1)}px`;
    }
  };
  addEventListener("scroll", () => { if (!pending && drifting.size) { pending = true; requestAnimationFrame(frame); } }, { passive: true });
})();
