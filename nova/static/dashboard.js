const $ = (id) => document.getElementById(id);
let conversationTask = null;
let emailDraft = null;
let deliveryPreview = null;
let featuredId = null;

function selectConversationTask(id) {
  conversationTask = id;
  sendVoice({type:"task_context", task_id:id});
}

function renderFeatured(task) {
  if (featuredId === task?.id) return;
  featuredId = task?.id;
  $("featured-project").hidden = !task;
  if (!task) return;
  $("feature-image").src = "/projects/" + encodeURIComponent(task.id) + "/desktop.png";
  $("feature-title").textContent = task.title;
}
const el = (tag, value, className) => {
  const node = document.createElement(tag);
  if (value !== undefined) node.textContent = value;
  if (className) node.className = className;
  return node;
};
const formatState = (state) => state.replaceAll("_", " ");
const terminal = new Set(["completed", "failed", "cancelled"]);
const money = new Intl.NumberFormat("en-IN", {style: "currency", currency: "INR", maximumFractionDigits: 0});
const ledgerMoney = new Intl.NumberFormat("en-IN", {style:"currency", currency:"INR", maximumFractionDigits:2});
const clock = new Intl.DateTimeFormat(undefined, {hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false});
const dateTime = new Intl.DateTimeFormat(undefined, {dateStyle:"medium", timeStyle:"short"});
const titles = {
  overview:"Overview", profile:"Profile", leads:"Customers", projects:"Projects", communications:"Communications",
  approvals:"Approvals", finance:"Finance", skills:"Skills observatory", models:"Model observatory", memory:"Memory",
};
const localHeaders = {"Content-Type":"application/json", "x-nova-owner":"1"};
let current;
let events = [];
let feed;
let refreshTimer;
let refreshGeneration = 0;
let lastPage = "";
let missionFilter = "all";
let detailTask = "";
let detailRequest = 0;
let detailRefresh;
let activeStage = "";
let replayEvent = null;
let studioRequest = 0;
let skillsRequest = 0;
let activeDraft = null;
const listKeys = new Map();

async function api(path, options) {
  const response = await fetch(path, options);
  const result = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(result.message || "The request could not be completed.");
    error.status = response.status;
    throw error;
  }
  return result;
}
const post = (path, value, method = "POST") => api(path, {method, headers:localHeaders, body:JSON.stringify(value)});
function report(message) {
  $("banner").textContent = message;
  $("banner").hidden = false;
}
function action(label, callback, className = "quiet") {
  const button = el("button", label, className);
  button.type = "button";
  button.addEventListener("click", async () => {
    button.disabled = true;
    try { await callback(); }
    catch (error) { report(error.message); }
    finally { button.disabled = false; }
  });
  return button;
}
function link(label, href) {
  let address;
  try { address = new URL(href, location.origin); }
  catch { return el("span", label); }
  if (!["https:", "http:"].includes(address.protocol)) return el("span", label);
  const anchor = el("a", label);
  anchor.href = address.href;
  anchor.target = "_blank";
  anchor.rel = "noopener noreferrer";
  return anchor;
}
function pill(state) {
  const badge = el("span", formatState(state), "pill");
  badge.dataset.state = state;
  return badge;
}
function renderList(id, data, emptyMessage, signature) {
  if (signature !== undefined && listKeys.get(id) === signature) return;
  listKeys.set(id, signature);
  const container = $(id);
  const focused = container.contains(document.activeElement) ? document.activeElement.dataset.focus : null;
  container.replaceChildren(...(data.length ? data : [el("p", emptyMessage, "empty")]));
  if (focused) container.querySelector('[data-focus="' + CSS.escape(focused) + '"]')?.focus({preventScroll:true});
}
function renderEvents(latest) {
  const entries = events.slice(-18).toReversed().map((event) => {
    const item = el("li");
    item.dataset.event = event.kind;
    if (event.id === latest) item.classList.add("event-new");
    const time = el("time", clock.format(event.time * 1000));
    time.dateTime = new Date(event.time * 1000).toISOString();
    const message = el("div");
    message.append(el("span", formatState(event.kind), "event-kind"), el("span", event.message, "event-label"));
    if (event.task_id) {
      const target = el("div", undefined, "event-task");
      const task = current?.tasks.find((record) => record.id === event.task_id);
      const inspect = action(task?.title || event.task_id, () => inspectTask(event.task_id), "");
      inspect.dataset.focus = "event-" + event.id;
      target.append(inspect);
      message.append(target);
    }
    item.append(time, message);
    return item;
  });
  const focus = $("events").contains(document.activeElement) ? document.activeElement.dataset.focus : null;
  $("events").replaceChildren(...(entries.length ? entries : [el("li", "Mission and provider events will appear here.", "empty")]));
  if (focus) $("events").querySelector('[data-focus="' + CSS.escape(focus) + '"]')?.focus({preventScroll:true});
  $("event-count").textContent = events.length ? String(events.length) + " recent" : "";
}
function setFeed(online) {
  $("feed-status").textContent = online ? "Live connection" : "Reconnecting";
  $("feed-status").toggleAttribute("data-offline", !online);
}
function connectFeed() {
  const last = events.at(-1)?.id || 0;
  feed = new EventSource("/api/events?after=" + last);
  feed.onopen = () => setFeed(true);
  feed.onerror = () => setFeed(false);
  feed.onmessage = ({data}) => {
    const event = JSON.parse(data);
    if (event.id <= (events.at(-1)?.id || 0)) return;
    events.push(event);
    events = events.slice(-40);
    renderEvents(event.id);
    if (event.kind === "notification" && micEnabled && ($("notifications").checked || wakeMode) && !playing && !recording && !turnPending) {
      sendVoice({type:"announce", id:event.id});
    }
    if (event.kind === "voice") queueRefresh();
    if (["task","checkpoint","model","approval","system","memory","notification","skill","schedule","draft","finance","lead"].includes(event.kind)) queueRefresh();
    if (event.kind === "skill" && lastPage === "skills") loadSkills().catch((error) => report(error.message));
    if (event.kind === "schedule" && lastPage === "overview") loadSchedules().catch((error) => report(error.message));
    if (event.kind === "finance" && lastPage === "finance") loadFinance().catch((error) => report(error.message));
    if (event.kind === "draft" && lastPage === "communications") loadDrafts().catch((error) => report(error.message));
    if (event.task_id === detailTask && $("details-dialog").open && !detailRefresh) {
      detailRefresh = setTimeout(() => {
        detailRefresh = null;
        if ($("details-dialog").open) inspectTask(detailTask, true).catch((error) => report(error.message));
      }, 540);
    }
  };
}
function queueRefresh() {
  if (!refreshTimer) refreshTimer = setTimeout(() => {
    refreshTimer = null;
    refresh().catch((error) => report(error.message));
  }, 300);
}
async function refresh() {
  const generation = ++refreshGeneration;
  const next = await api("/api/state");
  if (generation !== refreshGeneration) return;
  current = next;
  if (!feed) {
    events = current.recent_events;
    renderEvents();
    connectFeed();
  }
  renderState();
}

function controls(task) {
  const row = el("div", undefined, "task-actions");
  if (!terminal.has(task.state)) {
    const verb = task.state === "paused" ? "resume" : "pause";
    for (const name of [verb, "cancel"]) {
      const button = action(name[0].toUpperCase() + name.slice(1), async () => {
        await post("/api/tasks/" + task.id + "/control", {action:name});
        await refresh();
      });
      button.dataset.focus = task.id + "-" + name;
      row.append(button);
    }
  }
  return row;
}
function artifacts(task, build) {
  const items = el("div", undefined, "links");
  const base = "/projects/" + task.id + "/";
  const paths = [["Preview","index.html"], ["Desktop","desktop.png"], ["Mobile","mobile.png"], ["Proposal","proposal.json"]];
  if (build?.revision) paths.push(["Tablet","tablet.png"], ["Design brief","design.json"], ["Verification","verification.json"], ["Delivery notes","delivery.md"]);
  for (const [name, file] of paths) {
    items.append(link(name, base + file));
  }
  return items;
}
function fields(entries) {
  const list = el("dl", undefined, "key-values");
  for (const [label, value] of entries) {
    if (value === null || value === undefined || value === "") continue;
    const field = el("div");
    const definition = el("dd");
    if (value instanceof Node) definition.append(value);
    else definition.textContent = value;
    field.append(el("dt", label), definition);
    list.append(field);
  }
  return list;
}
function formatDate(timestamp) {
  return Number.isFinite(timestamp) && timestamp > 0 ? dateTime.format(timestamp * 1000) : "";
}
function displayName(value) {
  const words = formatState(String(value || ""));
  return words.replace(/^./, (letter) => letter.toUpperCase());
}
function stageEvidence(result, stage) {
  const box = el("div", undefined, "stage-result");
  const state = displayName(stage.state);
  box.append(el("strong", stage.name + " · " + state));
  if (!result) {
    box.append(el("p", "Evidence appears when this stage saves a checkpoint."));
    return box;
  }
  const list = el("ul");
  const values = [
    result.summary,
    result.message,
    result.direction,
    result.design?.direction,
    Number.isFinite(result.score) ? "Opportunity score " + result.score + "/100" : null,
    result.selected?.name ? "Selected " + result.selected.name : null,
    Array.isArray(result.candidates) ? result.candidates.length + " candidates" : null,
    Number.isFinite(result.bytes) ? (result.bytes / 1024).toFixed(1) + " KiB of project files" : null,
    result.draft?.business ? "Draft for " + result.draft.business : null,
    ...((result.findings || []).map((finding) => finding.observation)),
  ].filter(Boolean);
  list.append(...values.map((value) => el("li", value)));
  if (list.childElementCount) box.append(list);
  const publicSource = result.url || result.source;
  if (typeof publicSource === "string" && /^https?:/.test(publicSource)) box.append(link("Review source", publicSource));
  if (result.desktop || result.mobile || result.tablet) box.append(verificationCards(result));
  return box;
}
function workflowSection(stages, checkpoints) {
  const section = el("section", undefined, "inspection-section");
  const title = el("h3", "Workflow");
  const list = el("ol", undefined, "workflow-steps");
  const result = el("div");
  result.id = "stage-result";
  const buttons = new Map();
  let selected = stages.find((stage) => stage.id === activeStage) ||
    stages.find((stage) => ["running", "failed", "paused"].includes(stage.state)) ||
    stages.find((stage) => stage.state === "pending") || stages.at(-1);
  function select(stage) {
    selected = stage;
    activeStage = stage.id;
    result.replaceChildren(stageEvidence(checkpoints[stage.id], stage));
    for (const [id, button] of buttons) button.setAttribute("aria-pressed", String(id === selected.id));
  }
  for (const stage of stages) {
    const item = el("li");
    const button = el("button", stage.name);
    button.type = "button";
    button.dataset.state = stage.state === "completed" ? "complete" : stage.state === "running" ? "current" : stage.state;
    button.dataset.focus = "stage-" + stage.id;
    button.setAttribute("aria-controls", result.id);
    button.setAttribute("aria-label", stage.name + " " + displayName(stage.state));
    button.addEventListener("click", () => select(stage));
    buttons.set(stage.id, button);
    item.append(button);
    list.append(item);
  }
  if (selected) select(selected);
  section.append(title, list, result);
  return section;
}
function replaySection(history) {
  const section = el("section", undefined, "inspection-section");
  const controls = el("div", undefined, "replay-controls");
  const entry = el("div", undefined, "replay-entry");
  const position = el("input");
  position.type = "range";
  position.min = 0;
  position.max = history.length - 1;
  position.dataset.focus = "replay-position";
  position.setAttribute("aria-label", "Execution replay position");
  const preserved = history.findIndex((event) => event.id === replayEvent);
  position.value = preserved >= 0 ? preserved : history.length - 1;
  function show(remember = false) {
    const index = Number(position.value);
    const event = history[index];
    if (remember) replayEvent = event.id;
    const saved = history.slice(0, index + 1).filter((record) => record.kind === "checkpoint").length;
    entry.replaceChildren(el("strong", event.message),
      el("p", [formatDate(event.time), displayName(event.kind), saved + " checkpoints reached"].filter(Boolean).join(" · "), "tip"));
    position.setAttribute("aria-valuetext", (index + 1) + " of " + history.length + " · " + event.message);
    prev.disabled = index === 0;
    next.disabled = index === history.length - 1;
  }
  const prev = el("button", "Previous event", "secondary");
  const next = el("button", "Next event", "secondary");
  prev.type = next.type = "button";
  prev.addEventListener("click", () => { position.stepDown(); show(true); });
  next.addEventListener("click", () => { position.stepUp(); show(true); });
  prev.dataset.focus = "replay-prev";
  next.dataset.focus = "replay-next";
  position.addEventListener("input", () => show(true));
  controls.append(prev, position, next);
  show();
  section.append(el("h3", "Execution replay"), controls, entry);
  return section;
}
async function inspectTask(id, live = false) {
  if (!live) selectConversationTask(id);
  const generation = ++detailRequest;
  const freshSelection = detailTask !== id;
  if (freshSelection) {
    detailTask = id;
    activeStage = "";
    replayEvent = null;
  }
  const data = await api("/api/tasks/" + encodeURIComponent(id));
  if (generation !== detailRequest || (live && !$("details-dialog").open)) return;
  const {task, checkpoints, tool_calls, execution_seconds, audit_cache_hits, usage, skill_activations, workflow_stages} = data;
  const detail = $("detail-body");
  const focused = detail.contains(document.activeElement) ? document.activeElement.dataset.focus : null;
  $("detail-title").textContent = task.title;
  const namedDependency = current?.tasks.find((item) => item.id === task.depends_on);
  const dependency = task.depends_on ? action(namedDependency?.title || task.depends_on, () => inspectTask(task.depends_on), "task-title") : "";
  const tokenUsage = (usage || []).reduce((total, row) => total + (row.reported_tokens || 0), 0);
  const estimatedTokens = (usage || []).reduce((total, row) => total + (row.estimated_tokens || 0), 0);
  const modelNames = (data.events || []).filter((event) => event.kind === "model" && event.data?.model)
    .map((event) => event.data.model);
  const models = [...new Set(modelNames)].join(", ");
  detail.replaceChildren(fields([
    ["Mission ID", task.id], ["Status", pill(task.state)], ["Workflow", displayName(task.spec.workflow)],
    ["Created", formatDate(task.created)], ["Scheduled", task.spec.run_at ? formatDate(task.spec.run_at) : ""],
    ["Dependency", dependency], ["Execution", execution_seconds + " s · " + tool_calls + " tool steps"],
    ["Audit cache", audit_cache_hits + " hits"], ["Inference calls", (usage || []).reduce((count, row) => count + row.calls, 0)],
    ["Reported tokens", tokenUsage], ["Estimated tokens", estimatedTokens || null], ["Selected model", models],
  ]));

  const stages = workflow_stages?.length ? workflow_stages : Object.keys(checkpoints).map((id) => ({id, name:displayName(id), state:"completed"}));
  if (stages.length) detail.append(workflowSection(stages, checkpoints));
  if (skill_activations?.length) {
    const list = el("ul");
    for (const activation of skill_activations) {
      const names = activation.skill_ids || [activation.skill_id || activation.id].filter(Boolean);
      const attributes = [
        displayName(activation.stage), names.join(", "),
        activation.injected_tokens ? activation.injected_tokens + " tokens injected" : "",
        activation.outcome ? displayName(activation.outcome) : "",
      ];
      list.append(el("li", attributes.filter(Boolean).join(" · ")));
    }
    detail.append(el("h3", "Activated skills"), list);
  }
  if (data.events?.length) detail.append(replaySection(data.events));

  const audits = Object.entries(checkpoints).filter(([step]) => step.startsWith("audit_"));
  if (checkpoints.discover) {
    detail.append(link("Discovery source", checkpoints.discover.source),
      el("p", checkpoints.discover.candidates.length + " linked business homepages", "tip"));
  }
  if (audits.length) {
    const notes = el("ul");
    for (const [, audit] of audits) {
      const item = el("li");
      item.append(link(audit.name, audit.url), " · ", audit.error ? audit.message : audit.score + "/100");
      for (const finding of audit.findings || []) item.append(el("p", finding.observation, "tip"));
      notes.append(item);
    }
    detail.append(el("h3", "Website evidence"), notes);
  }
  if (checkpoints.sources?.sources) {
    detail.append(el("h3", "Research sources"));
    for (const source of checkpoints.sources.sources) {
      detail.append(link(source.name, source.url), el("p", source.extract, "tip"));
    }
  }
  if (checkpoints.brief) {
    detail.append(el("h3", "Planning brief"), el("p", checkpoints.brief.summary));
    for (const [title, lines] of [["Assumptions", checkpoints.brief.assumptions], ["Next steps", checkpoints.brief.next_steps]]) {
      if (lines?.length) {
        const items = el("ul");
        items.append(...lines.map((line) => el("li", line)));
        detail.append(el("h3", title), items);
      }
    }
  }
  if (checkpoints.proposal?.draft) {
    const draft = checkpoints.proposal.draft;
    detail.append(el("h3", draft.business),
      el("p", money.format(draft.proposed_price_inr) + " estimate · " + draft.effort_hours + " hours"),
      el("p", draft.rate_basis, "tip"), artifacts(task, checkpoints.build));
  }
  if (task.error) detail.append(el("p", "Issue " + formatState(task.error), "form-error"));
  if (!$("details-dialog").open && !live) $("details-dialog").showModal();
  if (focused) detail.querySelector('[data-focus="' + CSS.escape(focused) + '"]')?.focus({preventScroll:true});
}
function scheduled(task) {
  return ["queued", "retry_scheduled"].includes(task.state) && task.due > Date.now() / 1000;
}
function renderMissions(tasks) {
  const filtered = tasks.filter((task) => {
    if (missionFilter === "all") return true;
    if (missionFilter === "active") return !terminal.has(task.state) && !scheduled(task);
    if (missionFilter === "scheduled") return scheduled(task);
    return task.state === "completed";
  });
  $("mission-count").textContent = filtered.length ? filtered.length + " " + (filtered.length === 1 ? "mission" : "missions") : "";
  renderList("tasks", filtered.map((task) => {
    const row = el("article", undefined, "task");
    const head = el("div", undefined, "task-head");
    const inspect = action(task.title, () => inspectTask(task.id), "task-title");
    inspect.dataset.focus = task.id + "-inspect";
    head.append(inspect, pill(scheduled(task) ? "scheduled" : task.state));
    const dependency = task.depends_on && tasks.find((record) => record.id === task.depends_on);
    const details = el("div", undefined, "task-tools");
    const count = task.cursor ? task.cursor + " saved " + (task.cursor === 1 ? "step" : "steps") : "No saved steps";
    details.append(el("span", [displayName(task.spec.workflow), count, scheduled(task) ? formatDate(task.due) : ""].filter(Boolean).join(" · "), "tip"));
    row.append(head, details);
    if (task.depends_on) {
      const predecessor = action("Depends on " + (dependency?.title || task.depends_on), () => inspectTask(task.depends_on), "quiet");
      predecessor.dataset.focus = task.id + "-dependency";
      row.append(predecessor);
    }
    row.append(controls(task));
    return row;
  }), missionFilter === "all" ? "Queue a website review or planning brief to start." : "No missions match this view.",
    JSON.stringify([missionFilter, filtered, filtered.map((task) => scheduled(task))]));
}
function websiteProjects(tasks = current?.tasks || []) {
  return tasks.filter((task) => task.state === "completed" && task.spec.workflow === "website");
}
const compact = new Intl.NumberFormat(undefined, {notation:"compact", maximumFractionDigits:1});
function meter(bar, label, used, limit) {
  const ratio = limit ? Math.min(1, used / limit) : 0;
  $(bar).style.width = (ratio * 100).toFixed(1) + "%";
  $(bar).dataset.level = ratio > .8 ? "high" : "normal";
  $(label).textContent = compact.format(used) + " / " + compact.format(limit);
}
function initials(name) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0].toUpperCase()).join("") || "?";
}
let profileData = null;
async function loadBench() {
  const {results, routing} = await api("/api/models/bench");
  const models = Object.keys(results);
  $("bench-note").textContent = models.length ? models.length + " models · NOVA's real tasks" : "No benchmark yet: run uv run python tools/model_bench.py";
  const roles = {};
  for (const [role, model] of Object.entries(routing)) (roles[model] ||= []).push(role.replace("_", " "));
  const head = el("tr");
  for (const label of ["Model", "Tool calls", "Tool latency", "Chat first token", "Site design", "Site technical", "Plan time", "Used for"]) head.append(el("th", label));
  const rows = models.map((model) => {
    const r = results[model];
    const tr = el("tr");
    const site = r.site || {};
    const cells = [
      model.split("/").pop(),
      r.tools ? r.tools.correct + " / " + r.tools.of : "—",
      r.tools?.median_s != null ? r.tools.median_s.toFixed(1) + " s" : "—",
      r.chat?.ttft != null ? r.chat.ttft.toFixed(2) + " s" : (r.chat?.error || "—"),
      site.ok ? String(site.design ?? "—") : (site.error ? "failed" : "—"),
      site.ok ? String(site.technical) : "—",
      site.ok ? site.seconds + " s" : "—",
      (roles[model] || []).join(", ") || "",
    ];
    cells.forEach((value, index) => {
      const td = el("td", value);
      if (index === 0) td.title = model;
      if (index === 7 && value) td.className = "bench-role";
      tr.append(td);
    });
    return tr;
  });
  $("bench-table").replaceChildren(el("thead"), el("tbody"));
  $("bench-table").tHead.append(head);
  $("bench-table").tBodies[0].append(...rows);
}
async function loadProfile() {
  profileData = await api("/api/profile");
  renderProfile(profileData);
}
function chip(text, className = "chip") { return el("span", text, className); }
function renderProfile(data) {
  const has = Boolean(data?.name);
  $("profile-name").textContent = has ? data.name : "Tell NOVA who you are";
  $("profile-avatar").textContent = has ? initials(data.name) : "?";
  $("profile-headline").textContent = data.headline || "Add your headline, experience and goals so NOVA can work as your personal agent.";
  $("profile-meta").textContent = [data.location, data.email].filter(Boolean).join("  ·  ");
  $("profile-links").replaceChildren(...(data.links || []).map((item) => { const a = link(item.label, item.url); a.className = "link-pill"; return a; }));
  $("profile-status-line").textContent = data.status || "";
  $("profile-status-line").hidden = !data.status;
  $("profile-summary").textContent = data.summary || "";
  const stats = [["Publications", (data.publications || []).length], ["Projects", (data.projects || []).length],
    ["Roles", (data.experience || []).length], ["Skills", Object.values(data.skills || {}).flat().length]];
  $("profile-stats").replaceChildren(...stats.map(([label, value]) => { const d = el("div"); d.append(el("dt", label), el("dd", String(value))); return d; }));
  $("profile-experience").replaceChildren(...(data.experience || []).map((role) => {
    const item = el("li");
    const head = el("div", undefined, "cv-head");
    head.append(el("strong", role.role), el("span", role.period, "cv-period"));
    const list = el("ul");
    list.append(...(role.points || []).map((point) => el("li", point)));
    item.append(head, el("p", role.org, "cv-org"), list);
    return item;
  }));
  $("profile-publications").replaceChildren(...(data.publications || []).map((pub) => {
    const card = el("article", undefined, "pub");
    card.append(el("span", pub.year, "pub-year"));
    const body = el("div");
    body.append(el("h3", pub.title), el("p", pub.venue || "Research paper", "tip"));
    if (pub.doi) { const a = link("DOI " + pub.doi, "https://doi.org/" + pub.doi); a.className = "doi"; body.append(a); }
    card.append(body);
    return card;
  }));
  $("profile-projects").replaceChildren(...(data.projects || []).map((project) => {
    const card = el("article", undefined, "project-card");
    const head = el("div", undefined, "project-card-head");
    head.append(el("h3", project.name));
    if (project.url) { const a = link("Code", project.url); a.className = "link-pill small"; head.append(a); }
    const chips = el("div", undefined, "chips");
    chips.append(...(project.tech || []).map((tech) => chip(tech)));
    card.append(head, el("p", project.summary), chips);
    return card;
  }));
  $("profile-skills").replaceChildren(...Object.entries(data.skills || {}).map(([group, items]) => {
    const block = el("div", undefined, "skill-group");
    const chips = el("div", undefined, "chips");
    chips.append(...items.map((item) => chip(item)));
    block.append(el("h3", group, "sub-rule"), chips);
    return block;
  }));
  $("profile-goals").replaceChildren(...(data.goals || []).map((goal) => el("li", goal)));
  $("profile-focus").replaceChildren(...(data.focus || []).map((item) => chip(item, "chip accent")));
  $("profile-achievements").replaceChildren(...(data.achievements || []).map((item) => el("li", item)));
  $("profile-education").replaceChildren(...(data.education || []).map((item) => {
    const block = el("div", undefined, "edu");
    block.append(el("strong", item.role), el("p", [item.org, item.period].filter(Boolean).join(" · "), "tip"));
    return block;
  }));
  $("profile-rules").replaceChildren(...(data.agent_rules || []).map((rule) => el("li", rule)));
}
$("edit-profile").addEventListener("click", () => {
  const {updated, ...editable} = profileData || {};
  $("profile-json").value = JSON.stringify(editable, null, 2);
  $("profile-error").hidden = true;
  $("profile-dialog").showModal();
});
$("profile-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    profileData = await post("/api/profile", JSON.parse($("profile-json").value), "PUT");
    renderProfile(profileData);
    $("profile-dialog").close();
    report("Profile saved. NOVA will use it from your next request.");
    await refresh();
  } catch (error) {
    $("profile-error").textContent = error instanceof SyntaxError ? "That isn't valid JSON: " + error.message : error.message;
    $("profile-error").hidden = false;
  }
});
function renderAgentStatus() {
  const {email, agent, outbox, owner} = current;
  const me = current.me;
  $("owner-chip").hidden = !me;
  if (me) {
    $("owner-initials").textContent = initials(me.name);
    $("owner-name").textContent = me.name;
    $("owner-headline").textContent = me.headline.split("·")[0].trim();
  }
  if (owner) $("greeting").textContent = $("greeting").textContent.split(",")[0] + ", " + owner;
  $("email-dot").dataset.ok = email.configured ? "true" : "false";
  $("email-status").textContent = email.configured ? "Sending as " + email.sender + " · " + email.sent_last_hour + "/" + email.hourly_limit + " this hour"
    : "Not configured — set EMAIL_HOST, EMAIL_USER, EMAIL_PASS";
  const waiting = outbox.filter((item) => ["awaiting_confirmation", "needs_recipient"].includes(item.status)).length;
  const sent = outbox.filter((item) => item.status === "sent").length;
  $("outbox-dot").dataset.ok = waiting ? "warn" : "true";
  $("outbox-status").textContent = (waiting ? waiting + " waiting for you" : "Nothing waiting") + " · " + sent + " sent";
  $("agent-model").textContent = agent.model.split("/").pop();
  $("profile-dot").dataset.ok = current.profile_complete ? "true" : "warn";
  $("profile-status").textContent = current.profile_complete ? "Emails introduce you and your business"
    : "Add OWNER_NAME, BUSINESS_NAME, BUSINESS_ABOUT to .env";
  meter("calls-bar", "calls-used", agent.calls_last_hour, agent.calls_hour_limit);
  meter("tokens-bar", "tokens-used", agent.tokens_today, agent.daily_token_limit);
  if (lastPage === "communications") renderOutbox(outbox);
}
const outboxLabels = {awaiting_confirmation:"Ready to send", needs_recipient:"Needs recipient", sent:"Sent", failed:"Failed",
  discarded:"Discarded", unconfirmed:"Unconfirmed", sending:"Sending"};
const OPEN_STATES = ["awaiting_confirmation", "needs_recipient", "failed", "unconfirmed"];
let mailFolder = "drafts";
let selectedMail = null;
let mailMessages = [];
const relative = new Intl.RelativeTimeFormat(undefined, {numeric:"auto"});
function ago(timestamp) {
  const seconds = Math.round(timestamp - Date.now() / 1000);
  for (const [unit, size] of [["day", 86400], ["hour", 3600], ["minute", 60]]) {
    if (Math.abs(seconds) >= size) return relative.format(Math.round(seconds / size), unit);
  }
  return "just now";
}
function folderOf(message) {
  if (message.status === "sent") return "sent";
  if (OPEN_STATES.includes(message.status)) return "drafts";
  return "other";
}
function renderOutbox(messages) {
  mailMessages = messages;
  const counts = {drafts:0, sent:0};
  for (const message of messages) if (counts[folderOf(message)] !== undefined) counts[folderOf(message)] += 1;
  $("count-drafts").textContent = counts.drafts || "";
  $("count-sent").textContent = counts.sent || "";
  $("count-all").textContent = messages.length || "";
  $("outbox-count").textContent = messages.length + " messages";
  const missions = mailFolder === "missions";
  $("outbox-list").hidden = missions;
  $("draft-list").hidden = !missions;
  $("mail-search").hidden = missions;
  if (missions) return;
  const query = $("mail-search").value.trim().toLowerCase();
  const shown = messages.filter((message) => (mailFolder === "all" || folderOf(message) === mailFolder) &&
    (!query || [message.recipient, message.subject, message.body, message.business].join(" ").toLowerCase().includes(query)));
  renderList("outbox-list", shown.map((message) => {
    const item = el("button", undefined, "mail-item");
    item.type = "button";
    item.setAttribute("role", "option");
    item.setAttribute("aria-selected", String(selectedMail === message.id));
    item.dataset.focus = "mail-" + message.id;
    const top = el("div", undefined, "mail-item-top");
    const who = message.business && message.business !== "Owner" ? message.business : (message.recipient || "No recipient yet");
    top.append(el("strong", who), el("time", ago(message.updated)));
    const status = el("span", outboxLabels[message.status] || formatState(message.status), "mail-dot");
    status.dataset.state = message.status;
    item.append(top, el("span", message.subject, "mail-item-subject"),
      el("span", message.body.replace(/\s+/g, " ").slice(0, 110), "mail-item-snippet"), status);
    item.addEventListener("click", () => selectMail(message.id));
    return item;
  }), mailFolder === "sent" ? "Nothing sent yet." : "No drafts. Ask NOVA to email someone, or press Compose.",
    JSON.stringify([mailFolder, query, selectedMail, shown.map((message) => [message.id, message.status, message.updated])]));
  if (selectedMail && !messages.some((message) => message.id === selectedMail)) selectedMail = null;
  if (!selectedMail && shown.length && window.innerWidth > 900) selectMail(shown[0].id);
  else showMail(messages.find((message) => message.id === selectedMail));
}
function selectMail(id) {
  selectedMail = id;
  for (const node of $("outbox-list").querySelectorAll(".mail-item")) node.setAttribute("aria-selected", String(node.dataset.focus === "mail-" + id));
  showMail(mailMessages.find((message) => message.id === id));
}
let shownMail = "";
function showMail(message) {
  $("mail-empty").hidden = Boolean(message);
  $("mail-view").hidden = !message;
  if (!message) { shownMail = ""; return; }
  const signature = [message.id, message.status, message.updated].join("|");
  if (shownMail === signature) return;
  shownMail = signature;
  $("mail-subject").textContent = message.subject;
  $("mail-status").textContent = outboxLabels[message.status] || formatState(message.status);
  $("mail-status").dataset.state = message.status;
  $("mail-from").textContent = current?.email?.sender || "Not configured";
  $("mail-to").textContent = message.recipient || "No recipient yet";
  $("mail-date").textContent = formatDate(message.updated);
  $("mail-error").textContent = message.error || "";
  $("mail-error").hidden = !message.error;
  $("mail-frame").src = "/api/outbox/" + encodeURIComponent(message.id) + "/preview?v=" + Math.round(message.updated);
  const actions = $("mail-actions");
  actions.replaceChildren();
  const open = OPEN_STATES.includes(message.status);
  if (open && message.recipient) actions.append(action("Send now", () => sendOutbox(message.id), "primary"));
  if (open) actions.append(action(message.recipient ? "Edit" : "Add recipient", () => openOutbox(message), "secondary"));
  actions.append(action("Duplicate", () => openOutbox({...message, id:null, status:"new"}), "quiet"),
    action("Copy text", async () => {
      await navigator.clipboard.writeText(message.subject + "\n\n" + message.body);
      report("Copied to clipboard.");
    }, "quiet"));
  if (open) actions.append(action("Discard", async () => {
    await post("/api/outbox/" + message.id + "/discard");
    report("Message discarded.");
    await refresh();
  }, "quiet danger"));
}
async function sendOutbox(id) {
  try {
    const sent = await post("/api/outbox/" + id + "/send");
    report("Email sent to " + sent.recipient + ".");
  } catch (error) { report(error.message); }
  await refresh();
}
for (const tab of document.querySelectorAll("[data-folder]")) {
  tab.addEventListener("click", () => {
    mailFolder = tab.dataset.folder;
    for (const other of document.querySelectorAll("[data-folder]")) other.setAttribute("aria-selected", String(other === tab));
    selectedMail = null;
    if (mailFolder === "missions") { $("mail-empty").hidden = false; $("mail-view").hidden = true; loadDrafts(); }
    if (current) renderOutbox(current.outbox);
  });
}
$("mail-search").addEventListener("input", () => current && renderOutbox(current.outbox));

let outboxMessage = null;
let previewTimer = 0;
function livePreview() {
  clearTimeout(previewTimer);
  $("subject-count").textContent = $("outbox-subject").value.length + "/160";
  const words = $("outbox-body").value.trim().split(/\s+/).filter(Boolean).length;
  $("body-count").textContent = words + " words" + (words > 220 ? " · consider trimming" : "");
  previewTimer = setTimeout(() => {
    const params = new URLSearchParams({subject:$("outbox-subject").value, body:$("outbox-body").value});
    $("outbox-live").src = "/api/email/render?" + params;
  }, 350);
}
for (const id of ["outbox-subject", "outbox-body"]) $(id).addEventListener("input", livePreview);
for (const button of document.querySelectorAll("[data-width]")) {
  button.addEventListener("click", () => {
    for (const other of document.querySelectorAll("[data-width]")) other.setAttribute("aria-pressed", String(other === button));
    document.querySelector(".compose-preview-frame").dataset.width = button.dataset.width;
  });
}
for (const button of document.querySelectorAll("[data-assist]")) {
  button.addEventListener("click", async () => {
    if (!$("outbox-body").value.trim()) return;
    const buttons = document.querySelectorAll("[data-assist]");
    buttons.forEach((item) => { item.disabled = true; });
    button.textContent = "Rewriting…";
    try {
      const result = await post("/api/outbox/rewrite", {subject:$("outbox-subject").value, body:$("outbox-body").value,
        instruction:button.dataset.assist});
      $("outbox-subject").value = result.subject;
      $("outbox-body").value = result.body;
      livePreview();
    } catch (error) { $("outbox-error").textContent = error.message; $("outbox-error").hidden = false; }
    finally {
      buttons.forEach((item) => { item.disabled = false; });
      button.textContent = {shorter:"Make it shorter", warmer:"Warmer tone", specific:"More specific"}[button.dataset.assist];
    }
  });
}
function openOutbox(message = null) {
  outboxMessage = message?.id ? message : null;
  $("outbox-title").textContent = outboxMessage ? "Edit email" : "Compose email";
  $("outbox-recipient").value = message?.recipient || "";
  $("outbox-business").value = message?.business || "";
  $("outbox-business").disabled = Boolean(outboxMessage);
  $("outbox-subject").value = message?.subject || "";
  $("outbox-body").value = message?.body || "";
  $("outbox-error").hidden = true;
  const email = current?.email;
  $("outbox-sender").textContent = email?.configured ? "From " + email.sender + " · nothing is sent until you press Send." :
    "Email is not configured, so you can save and copy drafts only.";
  $("outbox-send").disabled = !email?.configured;
  livePreview();
  if (!$("outbox-dialog").open) $("outbox-dialog").showModal();
}
async function saveOutbox() {
  const body = {recipient:$("outbox-recipient").value.trim(), subject:$("outbox-subject").value.trim(), body:$("outbox-body").value};
  if (outboxMessage) return post("/api/outbox/" + outboxMessage.id, body, "PUT");
  return post("/api/outbox", {...body, business:$("outbox-business").value.trim()});
}
$("outbox-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    outboxMessage = await saveOutbox();
    selectedMail = outboxMessage.id;
    $("outbox-dialog").close();
    report("Draft saved.");
    await refresh();
  } catch (error) { $("outbox-error").textContent = error.message; $("outbox-error").hidden = false; }
});
$("outbox-send").addEventListener("click", async () => {
  if (!$("outbox-form").reportValidity()) return;
  if (!$("outbox-recipient").value.trim()) { $("outbox-error").textContent = "Add a recipient first."; $("outbox-error").hidden = false; return; }
  $("outbox-send").disabled = true;
  try {
    const saved = await saveOutbox();
    const sent = await post("/api/outbox/" + saved.id + "/send");
    selectedMail = sent.id;
    $("outbox-dialog").close();
    report("Email sent to " + sent.recipient + ".");
    await refresh();
  } catch (error) { $("outbox-error").textContent = error.message; $("outbox-error").hidden = false; }
  finally { $("outbox-send").disabled = false; }
});
$("compose-email").addEventListener("click", () => openOutbox());
function renderState() {
  const {tasks, counts, leads, approvals, usage, routes, voice} = current;
  $("version").textContent = "v" + current.version;
  $("active-count").textContent = Object.entries(counts).filter(([state]) => !terminal.has(state) && state !== "paused").reduce((a, [, value]) => a + value, 0);
  $("completed-count").textContent = counts.completed || 0;
  $("qualified-count").textContent = new Set(leads.filter((lead) => lead.score > 0).map((lead) => lead.url)).size;
  const pending = approvals.filter((review) => review.state === "pending").length;
  $("pending-count").textContent = pending;
  $("review-count").hidden = !pending;
  $("review-count").textContent = pending;
  $("stop").textContent = current.stopped ? "Reset emergency stop" : "Emergency stop";
  renderAgentStatus();
  $("open-mission").disabled = current.stopped;
  renderMissions(tasks);
  renderList("lead-list", leads.map((lead) => {
    const row = el("article", undefined, "record");
    const flags = el("ul");
    flags.append(...(lead.evidence.findings || []).map((flag) => el("li", flag.observation)));
    row.append(el("h3", lead.name), el("p", lead.score + "/100 · " + formatState(lead.stage), "tip"),
      link("Public source", lead.url));
    if (flags.children.length) row.append(flags);
    if (lead.evidence.scope) row.append(el("p", lead.evidence.scope, "tip"));
    if (lead.evidence.source_directory) row.append(link("Directory source", lead.evidence.source_directory));
    if (lead.stage !== "archived" && (!lead.allowed_stages || lead.allowed_stages.length)) row.append(leadControl(lead));
    return row;
  }), "Completed website research will appear here.", JSON.stringify(leads));
  const projects = websiteProjects(tasks);
  renderFeatured(projects[0] || null);
  renderList("project-list", projects.map((task) => {
    const row = el("article", undefined, "record");
    const head = el("div", undefined, "record-head");
    const studio = action("Open Design Studio", () => openStudio(task.id), "secondary");
    studio.dataset.focus = task.id + "-studio";
    head.append(el("h3", task.title), studio);
    const thumb = el("img", undefined, "project-thumb");
    thumb.src = "/projects/" + encodeURIComponent(task.id) + "/desktop.png";
    thumb.alt = "";
    thumb.loading = "lazy";
    thumb.addEventListener("error", () => thumb.remove());
    row.append(thumb, head, el("p", "Chromium verification completed", "tip"), artifacts(task));
    return row;
  }), "Verified website concepts will appear here.", JSON.stringify(projects));
  $("new-draft").disabled = !projects.length;
  renderList("approval-list", approvals.map((approval) => {
    const row = el("article", undefined, "record");
    const draft = approval.payload.proposal;
    row.append(el("h3", approval.payload.business),
      el("p", money.format(draft.proposed_price_inr) + " proposal estimate · " + approval.state),
      action("Review proposal", () => inspectTask(approval.task_id), "secondary"));
    if (approval.state === "pending") {
      const actions = el("div", undefined, "links");
      for (const approved of [true, false]) {
        actions.append(action(approved ? "Approve draft" : "Reject draft", async () => {
          await post("/api/approvals/" + approval.task_id, {digest:approval.digest, approved});
          report("Proposal decision recorded.");
          await refresh();
        }));
      }
      row.append(actions, el("p", "Approval records your review for a possible manual handoff.", "tip"));
    }
    return row;
  }), "No proposals are waiting for review.", JSON.stringify(approvals));
  const inventory = el("div", undefined, "record");
  inventory.append(el("h3", "Provider access"), el("p", current.catalogue_count === null ? "Catalogue check pending" : current.catalogue_count + " catalogue models"),
    el("p", money.format(current.spending_limit_inr) + " spending limit · NVIDIA Build trial", "tip"));
  renderList("routes", [inventory, ...Object.entries(routes).map(([capability, model]) => {
    const row = el("div", undefined, "record");
    row.append(el("h3", formatState(capability)), el("p", model || "Awaiting catalogue verification", "tip"));
    return row;
  })], "", JSON.stringify([current.catalogue_count, routes]));
  $("usage-total").textContent = usage.length ? usage.reduce((total, group) => total + group.calls, 0) + " calls" : "";
  renderList("usage", usage.map((group) => {
    const row = el("div", undefined, "record");
    row.append(el("h3", formatState(group.capability) + " · " + group.lane),
      el("p", group.calls + " calls · " + (group.mean_ms ?? "—") + " ms mean · " + group.errors + " errors"),
      el("p", "P50 " + (group.p50_ms ?? "—") + " ms · P95 " + (group.p95_ms ?? "—") + " ms", "tip"),
      el("p", group.lane === "speech" ? "Audio request metrics" :
        (group.reported_tokens ?? "—") + " reported tokens · " + (group.estimated_tokens ?? "—") + " estimated tokens", "tip"));
    return row;
  }), "NVIDIA request metrics will appear here.", JSON.stringify(usage));
  $("voice-toggle").disabled = !voice.enabled;
  $("voice-mode").textContent = (voice.asr_streaming ? "NVIDIA live transcription. " : "NVIDIA transcribes after each utterance. ") +
    (voice.provider === "deepgram" ? "Deepgram Aura speaks. " : "NVIDIA Magpie speaks. ") +
    "With speakers, use Stop audio before speaking over playback.";
  const select = $("voice-choice");
  const last = select.value;
  const deepgram = voice.provider === "deepgram";
  // Deepgram voices arrive pre-filtered by language (aura-2-athena-en); Magpie names carry it inline (….EN-US.Sofia).
  const available = deepgram ? voice.voices
    : voice.voices.filter((name) => name.toUpperCase().includes("." + voice.language.toUpperCase() + "."));
  const voiceLabel = (name) => deepgram
    ? name.split("-").slice(-2, -1)[0].replace(/^./, (c) => c.toUpperCase()) + (name.startsWith("aura-2-") ? "" : " (Aura 1)")
    : name.split(".").slice(2).join(" · ");
  if (available.join("|") !== select.dataset.options) {
    const configured = deepgram ? "Configured voice (" + voiceLabel(voice.preferred) + ", Deepgram)" : "Configured Magpie voice";
    select.replaceChildren(new Option(configured, ""), ...available.map((name) => new Option(voiceLabel(name), name)));
    select.value = available.includes(last) ? last : "";
    select.dataset.options = available.join("|");
  }
}
const projectPath = (taskId, filename, revision) => {
  const root = "/projects/" + encodeURIComponent(taskId) + "/";
  return root + (revision ? "revisions/" + encodeURIComponent(revision) + "/" : "") + encodeURIComponent(filename);
};
function verificationCards(report) {
  const grid = el("div", undefined, "studio-verification");
  for (const device of ["desktop", "tablet", "mobile"]) {
    const result = report?.[device];
    if (!result) continue;
    const card = el("article", undefined, "device-check");
    const number = (value, unit) => Number.isFinite(value) ? value + unit : null;
    const accessibility = result.accessibility;
    const violations = Array.isArray(accessibility?.violations) ? accessibility.violations : [];
    const evidence = [
      ["Viewport", number(result.width, " px")],
      ["Navigation", result.navigation === undefined ? null : result.navigation ? "Passed" : "Issue recorded"],
      ["Enquiry preview", result.enquiry_preview_verified ? "Passed" : null],
      ["Console errors", Number.isFinite(result.console_errors) ? result.console_errors : null],
      ["Load time", number(result.document_load_ms, " ms")],
      ["First contentful paint", number(result.performance?.fcp_ms, " ms")],
      ["Largest contentful paint", number(result.performance?.lcp_ms, " ms")],
      ["Layout shift", Number.isFinite(result.performance?.cls) ? result.performance.cls.toFixed(3) : null],
      ["Accessibility", accessibility?.engine && accessibility.engine + " · " + violations.length + " reported issues"],
      ["Contrast", result.visual?.contrast?.min_ratio !== undefined ? result.visual.contrast.min_ratio + ":1 minimum" : null],
    ];
    card.append(el("h3", displayName(device)), fields(evidence));
    if (violations.length) {
      const list = el("ul");
      for (const issue of violations) list.append(el("li", issue.summary || issue.id));
      card.append(list);
    }
    if (accessibility?.manual_review?.length) {
      const checks = el("details");
      const list = el("ul");
      list.append(...accessibility.manual_review.map((note) => el("li", typeof note === "string" ? note : note.label || note.check)));
      checks.append(el("summary", "Accessibility review"), list);
      card.append(checks);
    }
    grid.append(card);
  }
  return grid;
}
function designDescription(design) {
  const section = el("section", undefined, "inspection-section");
  section.append(el("h3", "Creative direction", "studio-heading"), fields([
    ["Industry", displayName(design.category)], ["Direction", design.direction],
    ["Composition", design.composition], ["Audience", design.audience], ["Visitor action", design.conversion],
    ["Headings", design.typography?.heading], ["Body text", design.typography?.body],
    ["Grounding", typeof design.source === "string" ? design.source : design.source?.business],
    ["Skills", design.skills?.map((skill) => typeof skill === "string" ? skill : skill.id).filter(Boolean).join(", ")],
  ]));
  const palette = el("div", undefined, "palette");
  for (const [name, color] of Object.entries(design.palette || {})) {
    if (typeof color !== "string" || !/^#[da-f]{3,8}$/i.test(color)) continue;
    const part = el("div", undefined, "swatch");
    const chip = el("i");
    chip.style.backgroundColor = color;
    chip.setAttribute("aria-hidden", "true");
    part.append(chip, el("span", name), el("span", color));
    palette.append(part);
  }
  if (palette.children.length) section.append(palette);
  return section;
}
function studioPreview(task, build, verification) {
  const section = el("div", undefined, "studio-preview");
  const toolbar = el("div", undefined, "studio-preview-toolbar");
  const devices = el("div", undefined, "segmented");
  devices.setAttribute("aria-label", "Preview device");
  const modes = el("div", undefined, "segmented");
  modes.setAttribute("aria-label", "Preview format");
  const viewport = el("div", undefined, "studio-viewport");
  const deviceButtons = new Map();
  const modeButtons = new Map();
  let device = "desktop";
  let mode = "live";
  function display() {
    viewport.dataset.device = device;
    for (const [name, button] of deviceButtons) button.setAttribute("aria-pressed", String(device === name));
    for (const [name, button] of modeButtons) button.setAttribute("aria-pressed", String(mode === name));
    if (mode === "verified") {
      const screenshot = verification?.[device];
      if (!screenshot) {
        viewport.replaceChildren(el("p", "This revision has no " + device + " screenshot.", "empty"));
        return;
      }
      const image = el("img", undefined, "studio-shot");
      image.alt = displayName(device) + " verification screenshot";
      image.src = projectPath(task.id, device + ".png");
      image.addEventListener("error", () => {
        if (image.isConnected) image.replaceWith(el("p", "The screenshot is unavailable.", "empty"));
      }, {once:true});
      viewport.replaceChildren(image);
      return;
    }
    const existing = viewport.querySelector("iframe");
    if (existing) {
      existing.title = task.title + " " + device + " preview";
      return;
    }
    const iframe = el("iframe", undefined, "studio-frame");
    iframe.title = task.title + " " + device + " preview";
    iframe.setAttribute("sandbox", "allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox");
    iframe.referrerPolicy = "no-referrer";
    iframe.src = projectPath(task.id, "index.html");
    viewport.replaceChildren(iframe);
  }
  for (const name of ["desktop", "tablet", "mobile"]) {
    const button = el("button", displayName(name));
    button.type = "button";
    button.addEventListener("click", () => { device = name; display(); });
    devices.append(button);
    deviceButtons.set(name, button);
  }
  for (const [name, label] of [["live", "Live"], ["verified", "Screenshot"]]) {
    const button = el("button", label);
    button.type = "button";
    button.addEventListener("click", () => { mode = name; display(); });
    modes.append(button);
    modeButtons.set(name, button);
  }
  toolbar.append(devices, modes);
  section.append(toolbar, viewport);
  display();
  return section;
}
function revisionReview(task, currentBuild, revisions, findings = []) {
  const section = el("section", undefined, "inspection-section");
  const currentRevision = currentBuild?.revision;
  section.append(el("h3", "Revision history", "studio-heading"));
  if (currentRevision) section.append(el("p", "Current " + currentRevision, "tip"));
  if (findings.length > 1) {
    const label = el("label", "Prioritize an audit finding");
    const priority = el("select");
    priority.append(...findings.slice(0, 3).map((finding, index) => new Option(finding.observation, String(index))));
    label.append(priority);
    section.append(label, action("Build an alternate", async () => {
      const alternate = await post("/api/tasks/" + encodeURIComponent(task.id) + "/revisions", {
        priority_index: Number(priority.value),
      });
      await openStudio(task.id);
      report(alternate.created ? "Verified an alternate revision." : "That revision is already available.");
    }, "secondary"));
  }
  const archived = revisions.filter((entry) => entry.revision && entry.revision !== currentRevision);
  if (!archived.length) {
    section.append(el("p", "This is the first recorded revision.", "tip"));
    return section;
  }
  const selector = el("select");
  selector.setAttribute("aria-label", "Revision to compare");
  selector.append(...archived.map((entry) => new Option(entry.revision + (entry.updated ? " · " + formatDate(entry.updated) : ""), entry.revision)));
  const comparison = el("div", undefined, "revision-compare");
  function compare() {
    comparison.replaceChildren(...[
      ["Archived " + selector.value, projectPath(task.id, "desktop.png", selector.value)],
      ["Current " + currentRevision, projectPath(task.id, "desktop.png")],
    ].map(([label, path]) => {
      const screenshot = el("img");
      screenshot.src = path;
      screenshot.alt = label + " desktop screenshot";
      screenshot.loading = "lazy";
      screenshot.addEventListener("error", () => {
        if (screenshot.isConnected) screenshot.replaceWith(el("p", "This revision has no desktop screenshot.", "tip"));
      }, {once:true});
      const figure = el("figure");
      figure.append(screenshot, el("figcaption", label));
      return figure;
    }));
  }
  selector.addEventListener("change", compare);
  section.append(selector, comparison);
  compare();
  return section;
}
function visualReviewSection(taskId) {
  const section = el("section", undefined, "inspection-section");
  const result = el("div", undefined, "stage-result");
  const button = action("Request NVIDIA visual review", async () => {
    result.textContent = "Waiting for NVIDIA visual review…";
    try {
      const review = await post("/api/tasks/" + encodeURIComponent(taskId) + "/visual-review", {});
      const critique = review.critique;
      result.replaceChildren(el("p", [review.model, review.cache_hit ? "Cached review" : ""].filter(Boolean).join(" · "), "tip"));
      if (typeof critique === "string") result.append(el("p", critique));
      else if (critique) {
        for (const [key, value] of Object.entries(critique)) {
          if (typeof value === "string") result.append(el("h4", displayName(key)), el("p", value));
          else if (Array.isArray(value)) {
            const list = el("ul");
            list.append(...value.flatMap((item) => {
              if (typeof item === "string") return [el("li", item)];
              const text = item?.summary || item?.finding || item?.observation;
              return typeof text === "string" ? [el("li", text)] : [];
            }));
            if (list.children.length) result.append(el("h4", displayName(key)), list);
          }
        }
      }
    } catch (error) {
      result.replaceChildren(el("p", error.message, "form-error"));
    }
  }, "secondary");
  section.append(el("h3", "Visual review", "studio-heading"),
    el("p", "This action sends the verified desktop screenshot to NVIDIA for a visual critique.", "tip"), button, result);
  return section;
}
async function openStudio(id) {
  selectConversationTask(id);
  const generation = ++studioRequest;
  const {task, checkpoints, revisions = [], execution_seconds, tool_calls} = await api("/api/tasks/" + encodeURIComponent(id));
  if (generation !== studioRequest) return;
  const build = checkpoints.build;
  const verification = checkpoints.verify;
  const detail = $("studio-detail");
  const body = $("studio-body");
  $("studio-title").textContent = "Design Studio";
  const title = el("div", undefined, "studio-title");
  title.append(el("h3", task.title), el("p", [build?.revision, execution_seconds + " s", tool_calls + " workflow steps"].filter(Boolean).join(" · "), "tip"));
  body.replaceChildren(title, studioPreview(task, build, verification));
  if (build?.design || checkpoints.design) body.append(designDescription(build?.design || checkpoints.design));
  if (verification) {
    const reviewed = el("section", undefined, "inspection-section");
    reviewed.append(el("h3", "Verification evidence", "studio-heading"), verificationCards(verification));
    body.append(reviewed);
  }
  if (build?.revision || revisions.length) {
    body.append(revisionReview(task, build, revisions, checkpoints.rank?.selected?.findings || []));
  }
  if (checkpoints.proposal?.draft) {
    const draft = checkpoints.proposal.draft;
    body.append(fields([["Proposal", money.format(draft.proposed_price_inr) + " estimate"], ["Estimate basis", draft.rate_basis]]));
  }
  body.append(artifacts(task, build));
  const exports = el("div", undefined, "links");
  for (const [label, format] of [["Proposal document", "docx"], ["Review deck", "pptx"], ["Evidence workbook", "xlsx"]]) {
    exports.append(link(label, "/api/tasks/" + encodeURIComponent(id) + "/export/" + format));
  }
  body.append(exports);
  if (verification?.desktop) body.append(visualReviewSection(task.id));
  detail.hidden = false;
  detail.scrollIntoView({block:"start", behavior:"instant"});
  $("close-studio").focus({preventScroll:true});
}
$("close-studio").addEventListener("click", () => {
  studioRequest += 1;
  $("studio-detail").hidden = true;
  $("studio-body").replaceChildren();
  $("project-list").querySelector("button")?.focus({preventScroll:true});
});
let skillCategory = "all";
const categoryNames = {research:"Research", outreach:"Outreach", growth:"Growth", design:"Design", engineering:"Engineering",
  planning:"Planning", communication:"Communication", analysis:"Analysis", motion:"Motion"};
async function loadSkills() {
  const sequence = ++skillsRequest;
  try {
    const {skills} = await api("/api/skills?q=" + encodeURIComponent($("skill-query").value));
    if (sequence !== skillsRequest) return;
    const installed = skills.filter((skill) => skill.installed).length;
    const enabled = skills.filter((skill) => skill.enabled).length;
    const uses = skills.reduce((total, skill) => total + (skill.stats?.uses || 0), 0);
    $("skill-summary").textContent = [skills.length + " skills", enabled + " enabled", uses + " activations"].join(" · ");
    const categories = [...new Set(skills.map((skill) => skill.category))].sort();
    const filters = $("skill-filters");
    filters.replaceChildren(...["all", ...categories].map((category) => {
      const button = el("button", (categoryNames[category] || displayName(category)) + " " +
        (category === "all" ? skills.length : skills.filter((skill) => skill.category === category).length));
      button.type = "button";
      button.setAttribute("aria-pressed", String(skillCategory === category));
      button.addEventListener("click", () => { skillCategory = category; loadSkills(); });
      return button;
    }));
    const shown = skills.filter((skill) => skillCategory === "all" || skill.category === skillCategory);
    renderList("skill-list", shown.map((skill) => {
      const card = el("article", undefined, "skill-card");
      card.dataset.category = skill.category;
      const head = el("div", undefined, "skill-card-head");
      const details = action(skill.title || skill.name || skill.id, () => inspectSkill(skill.id), "task-title");
      details.dataset.focus = "skill-" + skill.id;
      head.append(details, pill(skill.status));
      const source = (skill.source || "").replace("https://github.com/", "");
      const foot = el("div", undefined, "skill-card-foot");
      foot.append(chip(categoryNames[skill.category] || displayName(skill.category), "chip accent"), chip(skill.license),
        el("span", source, "skill-source"), el("span", (skill.stats?.uses || 0) + " uses", "skill-uses"));
      card.append(head, el("p", skill.description), foot);
      return card;
    }), "No skills match this search.", JSON.stringify([skillCategory, skills]));
  } catch (error) {
    if (sequence !== skillsRequest) return;
    $("skill-summary").textContent = "";
    renderList("skill-list", [], error.message);
  }
}
function skillActions(skill) {
  const controls = el("div", undefined, "links");
  const revisions = skill.available_revisions || [];
  const select = el("select");
  select.setAttribute("aria-label", "Reviewed revision");
  if (revisions.length) {
    select.append(...revisions.map((entry) => new Option(
      (entry.version ? entry.version + " · " : "") + entry.revision.slice(0, 12), entry.revision,
    )));
  }
  function mutation(label, operation, needsRevision = false, style = "secondary") {
    return action(label, async () => {
      const payload = needsRevision && select.value ? {revision:select.value} : {};
      await post("/api/skills/" + encodeURIComponent(skill.id) + "/" + operation, payload);
      await inspectSkill(skill.id);
      await loadSkills();
    }, style);
  }
  if (!skill.installed && skill.status === "available") {
    if (revisions.length > 1) controls.append(select);
    controls.append(mutation("Install reviewed skill", "install", true, "primary"));
  }
  if (skill.installed && skill.status !== "quarantined") {
    controls.append(mutation(skill.enabled ? "Disable" : "Enable", skill.enabled ? "disable" : "enable"));
    if (revisions.some((entry) => entry.revision !== skill.revision)) {
      const recommended = revisions.find((entry) => entry.revision !== skill.revision);
      select.value = recommended.revision;
      controls.append(select, mutation("Update revision", "update", true));
    }
    if (skill.rollback_revision) controls.append(mutation("Roll back", "rollback"));
    controls.append(mutation("Run skill evaluation", "evaluate"));
  }
  return controls;
}
async function inspectSkill(id) {
  const result = await api("/api/skills/" + encodeURIComponent(id));
  const skill = result.skill || result;
  $("skill-title").textContent = skill.title || skill.name || id;
  const detail = $("skill-detail");
  const stats = skill.stats || {};
  const evaluation = skill.evaluation;
  detail.replaceChildren(
    el("p", skill.description),
    fields([
      ["Status", pill(skill.status)], ["Version", skill.version], ["Revision", skill.revision],
      ["License", skill.license], ["Trust", displayName(skill.trust)],
      ["Source", skill.source ? link(skill.source_path || "Upstream repository", skill.source) : null],
      ["Last validated", formatDate(skill.validated_at) || skill.validated_at],
      ["Last activated", formatDate(stats.latest_at) || stats.latest_at],
      ["Activations", stats.uses], ["Successful", stats.successes], ["Failed", stats.failures],
      ["Estimated context", stats.estimated_tokens === undefined ? null : stats.estimated_tokens + " tokens"],
      ["Permissions", (skill.permissions || []).map(displayName).join(", ")],
      ["Dependencies", (skill.dependencies || []).map(displayName).join(", ")],
    ]),
  );
  if (evaluation) {
    const summary = typeof evaluation === "string" ? evaluation : evaluation.summary || evaluation.result;
    if (summary) detail.append(el("h3", "Evaluation"), el("p", summary));
  }
  const files = Object.entries(skill.files || {});
  if (files.length) {
    const reviewed = el("details");
    const list = el("ul");
    for (const [path, metadata] of files) {
      list.append(el("li", path + (metadata.sha256 ? " · SHA-256 " + metadata.sha256.slice(0, 12) : "")));
    }
    reviewed.append(el("summary", "Verified files"), list);
    detail.append(reviewed);
  }
  const actions = skillActions(skill);
  if (actions.children.length) detail.append(actions);
  if (!$("skill-dialog").open) $("skill-dialog").showModal();
}
$("skill-form").addEventListener("submit", (event) => { event.preventDefault(); loadSkills(); });

async function loadDrafts() {
  try {
    const {drafts} = await api("/api/drafts");
    renderList("draft-list", drafts.map((draft) => {
      const row = el("article", undefined, "record");
      const head = el("div", undefined, "record-head");
      const inspect = action(draft.subject, () => openDraft(draft), "task-title");
      inspect.dataset.focus = "draft-" + draft.id;
      head.append(inspect, pill(draft.status));
      row.append(head, el("p", [draft.business, displayName(draft.kind), formatDate(draft.updated)].filter(Boolean).join(" · "), "tip"));
      if (draft.body) row.append(el("p", draft.body.replace(/\s+/g, " ").slice(0, 180) + (draft.body.length > 180 ? "…" : ""), "draft-excerpt"));
      const controls = el("div", undefined, "links");
      controls.append(action("Edit draft", () => openDraft(draft), "secondary"));
      if (draft.status !== "rejected") controls.append(action("Review delivery", () => openEmail(draft), "secondary"));
      const base = "/api/drafts/" + encodeURIComponent(draft.id);
      controls.append(link("Plain text", base + "/export/txt"), link("HTML", base + "/export/html"));
      if (draft.status === "pending") {
        for (const approved of [true, false]) {
          controls.append(action(approved ? "Approve draft" : "Reject draft", async () => {
            await post(base + "/review", {digest:draft.digest, approved});
            await loadDrafts();
            report(approved ? "Draft approved for manual handoff." : "Draft rejected.");
          }));
        }
      }
      row.append(controls);
      return row;
    }), "Create a draft from a completed project.", JSON.stringify(drafts));
  } catch (error) {
    renderList("draft-list", [], error.message);
  }
}
function showChannels(channels) {
  $("email-provider").textContent = channels.configured ? "The configured mailbox can send this message after your confirmation." :
    "SMTP is not configured. You can copy the draft or use the official contact page.";
  const addresses = channels.emails || [];
  $("public-email-addresses").replaceChildren(...addresses.map((address) => new Option(address, address)));
  if (addresses.length === 1 && !$("email-recipient").value) $("email-recipient").value = addresses[0];
  const box = $("email-channels");
  box.replaceChildren();
  if (channels.source) box.append(link("Public source", channels.source));
  if (channels.contact_page) box.append(link("Official contact page", channels.contact_page));
  if (channels.source) {
    box.append(action("Find public contact details", async () => {
      const selected = emailDraft;
      const found = await post("/api/drafts/" + selected.id + "/channels", {});
      if (emailDraft === selected && $("email-dialog").open) {
        showChannels(found);
        if (!found.emails.length) $("email-provider").textContent += " No public email address was found on the inspected page.";
      }
    }));
  }
}
function clearDeliveryReview() {
  deliveryPreview = null;
  $("email-preview").replaceChildren();
  $("email-action").textContent = "Review recipient and message";
  $("email-action").disabled = false;
}
async function openEmail(draft) {
  if ($("draft-dialog").open) $("draft-dialog").close();
  emailDraft = draft;
  $("email-recipient").value = "";
  $("email-recipient").disabled = false;
  $("email-error").hidden = true;
  clearDeliveryReview();
  $("email-provider").textContent = "Checking contact details…";
  $("email-channels").replaceChildren();
  $("public-email-addresses").replaceChildren();
  if (!$("email-dialog").open) $("email-dialog").showModal();
  $("email-recipient").focus();
  const channels = await api("/api/drafts/" + draft.id + "/channels");
  if (emailDraft === draft && $("email-dialog").open) showChannels(channels);
}
$("email-recipient").addEventListener("input", () => {
  clearDeliveryReview();
  $("email-error").hidden = true;
});
$("email-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = $("email-action");
  const base = "/api/drafts/" + emailDraft.id + "/email/";
  const recipient = $("email-recipient").value.trim();
  $("email-error").hidden = true;
  button.disabled = true;
  try {
    if (!deliveryPreview) {
      const preview = await post(base + "preview", {recipient});
      deliveryPreview = preview;
      $("email-preview").replaceChildren(el("strong", preview.subject),
        el("p", "To: " + preview.recipient, "tip"), el("p", preview.body));
      if (preview.configured && preview.state === "ready") button.textContent = "Confirm and send email";
      else {
        $("email-preview").append(el("p", preview.state === "ready" ? "A sender mailbox is required." : "Delivery status: " + preview.state, "tip"));
        return;
      }
    } else {
      $("email-recipient").disabled = true;
      const delivery = await post(base + "deliver", {recipient, digest:deliveryPreview.digest});
      $("email-preview").append(el("p", delivery.state === "accepted" ? "The mail server accepted the message." :
        "Delivery status: " + delivery.state + ". Verify it in your mailbox.", "tip"));
      button.textContent = "Delivery " + delivery.state;
      return;
    }
  } catch (error) {
    $("email-error").textContent = error.message;
    $("email-error").hidden = false;
    $("email-recipient").disabled = false;
    clearDeliveryReview();
  }
  button.disabled = false;
});
function openDraft(draft = null) {
  activeDraft = draft;
  $("draft-title").textContent = draft ? "Edit draft" : "New draft";
  $("draft-source").hidden = Boolean(draft);
  $("draft-editor").hidden = !draft;
  $("draft-copy").hidden = !draft;
  $("draft-error").hidden = true;
  $("draft-project").replaceChildren(...websiteProjects().map((task) => new Option(task.title, task.id)));
  $("draft-subject").value = draft?.subject || "";
  $("draft-body").value = draft?.body || "";
  $("draft-save").textContent = draft ? "Save draft" : "Create draft";
  if (!$("draft-dialog").open) $("draft-dialog").showModal();
  (draft ? $("draft-subject") : $("draft-project")).focus();
}
$("new-draft").addEventListener("click", () => openDraft());
$("draft-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("draft-save").disabled = true;
  $("draft-error").hidden = true;
  try {
    if (activeDraft) {
      await post("/api/drafts/" + encodeURIComponent(activeDraft.id), {
        subject:$("draft-subject").value.trim(), body:$("draft-body").value.trim(), digest:activeDraft.digest,
      }, "PUT");
      $("draft-dialog").close();
      report("Draft saved for review.");
    } else {
      const result = await post("/api/drafts", {task_id:$("draft-project").value, kind:$("draft-kind").value});
      const draft = result.draft || result;
      if (draft.id) openDraft(draft);
      else $("draft-dialog").close();
      report("Draft prepared for review.");
    }
    await loadDrafts();
  } catch (error) {
    $("draft-error").textContent = error.message;
    $("draft-error").hidden = false;
  } finally {
    $("draft-save").disabled = false;
  }
});
$("draft-copy").addEventListener("click", async () => {
  try {
    await navigator.clipboard.writeText($("draft-subject").value + "\n\n" + $("draft-body").value);
    $("draft-copy").textContent = "Copied";
    setTimeout(() => { $("draft-copy").textContent = "Copy text"; }, 1200);
  } catch {
    $("draft-error").textContent = "The browser could not copy the draft.";
    $("draft-error").hidden = false;
  }
});
async function loadSchedules() {
  try {
    const {schedules} = await api("/api/schedules");
    $("schedule-count").textContent = schedules.length ? schedules.filter((schedule) => schedule.enabled).length + " active" : "";
    renderList("schedule-list", schedules.map((schedule) => {
      const row = el("article", undefined, "record");
      const head = el("div", undefined, "record-head");
      head.append(el("h3", schedule.name), pill(schedule.enabled ? "enabled" : "paused"));
      row.append(head, el("p", "Every " + schedule.every_hours + " hours" + (schedule.enabled && schedule.next_due ? " · " + formatDate(schedule.next_due) : ""), "tip"));
      const controls = el("div", undefined, "task-actions");
      controls.append(action(schedule.enabled ? "Pause schedule" : "Resume schedule", async () => {
        await post("/api/schedules/" + encodeURIComponent(schedule.id), {enabled:!schedule.enabled});
        await loadSchedules();
      }));
      const previous = typeof schedule.latest_task === "string" ? schedule.latest_task : schedule.latest_task?.id;
      if (previous) controls.append(action("Inspect latest mission", () => inspectTask(previous)));
      row.append(controls);
      return row;
    }), "Set a repeat interval when you create a mission.", JSON.stringify(schedules));
  } catch (error) {
    renderList("schedule-list", [], error.message);
  }
}
document.querySelector(".schedules").addEventListener("toggle", (event) => {
  if (event.currentTarget.open) loadSchedules();
});
function leadControl(lead) {
  const details = el("details");
  details.className = "lead-control";
  const form = el("form", undefined, "lead-form");
  const stage = el("select");
  const stages = lead.allowed_stages || ["qualified", "contacted", "negotiating", "won", "lost", "delivered", "archived"];
  stage.append(...stages.filter((name) => name !== lead.stage).map((name) => new Option(displayName(name), name)));
  const note = el("input");
  note.maxLength = 500;
  note.placeholder = "Optional owner note";
  const result = el("p", "", "form-error");
  const submit = el("button", "Save stage", "secondary");
  submit.type = "submit";
  if (!stage.options.length) return details;
  const choice = el("label", "Stage");
  choice.append(stage);
  const comment = el("label", "Note");
  comment.append(note);
  form.append(choice, comment, submit, result);
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    submit.disabled = true;
    result.textContent = "";
    try {
      await post("/api/leads/" + encodeURIComponent(lead.task_id) + "/stage", {url:lead.url, stage:stage.value, note:note.value.trim()});
      await refresh();
      report("Customer stage recorded.");
    } catch (error) {
      result.textContent = error.message;
    } finally { submit.disabled = false; }
  });
  details.append(el("summary", "Record stage"), form);
  return details;
}
async function loadFinance() {
  try {
    const data = await api("/api/finance");
    const items = [
      ["Invoiced", data.invoiced_paise], ["Received", data.received_paise],
      ["Outstanding", data.outstanding_paise], ["Expenses", data.expense_paise], ["Net cash", data.net_cash_paise],
    ];
    $("finance-totals").replaceChildren(...items.map(([name, amount]) => {
      const item = el("div");
      item.append(el("dt", name), el("dd", ledgerMoney.format(amount / 100)));
      return item;
    }));
    $("finance-currency").textContent = data.currency;
    renderList("finance-list", (data.entries || []).map((entry) => {
      const row = el("article", undefined, "record");
      const heading = el("div", undefined, "record-head");
      heading.append(el("h3", entry.reference), el("strong", ledgerMoney.format(entry.amount_paise / 100)));
      row.append(heading, el("p", [displayName(entry.kind), entry.occurred_on, entry.invoice_reference].filter(Boolean).join(" · "), "tip"));
      if (entry.note) row.append(el("p", entry.note));
      return row;
    }), "No financial entries have been recorded.", JSON.stringify(data.entries));
  } catch (error) {
    $("finance-totals").replaceChildren();
    renderList("finance-list", [], error.message);
  }
}
function dateValue() {
  const now = new Date();
  return [now.getFullYear(), now.getMonth() + 1, now.getDate()].map((part) => String(part).padStart(2, "0")).join("-");
}
$("new-entry").addEventListener("click", () => {
  $("finance-form").reset();
  $("finance-date").value = dateValue();
  $("finance-error").hidden = true;
  $("finance-task").replaceChildren(new Option("None", ""), ...websiteProjects().map((task) => new Option(task.title, task.id)));
  $("finance-kind").dispatchEvent(new Event("change"));
  $("finance-dialog").showModal();
});
$("finance-kind").addEventListener("change", () => {
  const payment = $("finance-kind").value === "payment";
  $("finance-invoice").required = payment;
  $("finance-invoice-field").hidden = !payment;
});
$("finance-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("finance-error").hidden = true;
  $("save-entry").disabled = true;
  try {
    const paise = Math.round(Number($("finance-amount").value) * 100);
    if (!Number.isSafeInteger(paise) || paise < 1) throw new Error("Enter a valid amount.");
    const payload = {
      kind:$("finance-kind").value, reference:$("finance-reference").value.trim(), amount_paise:paise,
      occurred_on:$("finance-date").value, task_id:$("finance-task").value || null,
      note:$("finance-note").value.trim(),
    };
    if (payload.kind === "payment") payload.invoice_reference = $("finance-invoice").value.trim();
    await post("/api/finance", payload);
    $("finance-dialog").close();
    report("Financial entry recorded.");
    await loadFinance();
  } catch (error) {
    $("finance-error").textContent = error.message;
    $("finance-error").hidden = false;
  } finally { $("save-entry").disabled = false; }
});
function routePage() {
  const page = location.hash.substring(1);
  const selected = Object.hasOwn(titles, page) ? page : "overview";
  for (const section of document.querySelectorAll(".view")) {
    section.hidden = section.id !== selected;
    section.classList.remove("entering");
  }
  for (const anchor of document.querySelectorAll(".sidebar nav a")) {
    if (anchor.hash === "#" + selected) anchor.setAttribute("aria-current", "page");
    else anchor.removeAttribute("aria-current");
  }
  $("breadcrumb").textContent = titles[selected];
  if (selected === "overview") $("voice-home").append($("voice-dock"));
  else {
    if (lastPage !== selected) setTranscript(false);
    $("voice-anchor").after($("voice-dock"));
  }
  if (lastPage !== selected) {
    $(selected).classList.add("entering");
    if (lastPage && page !== "workspace") window.scrollTo(0, 0);
    const loaders = {
      memory:searchMemory, skills:loadSkills, finance:loadFinance, profile:loadProfile, models:loadBench,
      communications:async () => { await loadDrafts(); if (current) renderOutbox(current.outbox); },
    };
    loaders[selected]?.().catch((error) => report(error.message));
  }
  lastPage = selected;
}
async function searchMemory() {
  const notes = await api("/api/memory?q=" + encodeURIComponent($("memory-query").value));
  renderList("memory-list", notes.map((note) => {
    const row = el("article", undefined, "record");
    row.append(el("h3", note.headline), el("p", note.body), el("p", note.source, "tip"),
      action("Delete note", async () => {
        if (!confirm("Delete this recorded memory note?")) return;
        await api("/api/memory/" + note.id, {method:"DELETE", headers:localHeaders});
        await searchMemory();
      }));
    return row;
  }), "No matching memory.");
}
window.addEventListener("hashchange", routePage);
routePage();
$("feature-open").addEventListener("click", () => {
  if (!featuredId) return;
  location.hash = "projects";
  openStudio(featuredId).catch((error) => report(error.message));
});
for (const button of document.querySelectorAll("[data-prompt]")) {
  button.addEventListener("click", () => sendText(button.dataset.prompt));
}
{
  const hour = new Date().getHours();
  $("greeting").textContent = hour < 5 ? "Working late" : hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
}
for (const button of document.querySelectorAll("[data-filter]")) {
  button.addEventListener("click", () => {
    missionFilter = button.dataset.filter;
    for (const choice of document.querySelectorAll("[data-filter]")) {
      choice.setAttribute("aria-pressed", String(choice === button));
    }
    if (current) renderMissions(current.tasks);
  });
}
$("details-dialog").addEventListener("close", () => {
  detailTask = "";
  replayEvent = null;
  clearTimeout(detailRefresh);
  detailRefresh = null;
});
$("memory-form").addEventListener("submit", (event) => {
  event.preventDefault();
  searchMemory().catch((error) => report(error.message));
});
$("stop").addEventListener("click", async () => {
  if (!current) return;
  if (!current.stopped && !confirm("Cancel active and queued missions and stop new execution?")) return;
  try {
    await post("/api/stop/" + (current.stopped ? "reset" : "enable"));
    await refresh();
  } catch (error) { report(error.message); }
});
$("check-providers").addEventListener("click", async () => {
  const button = $("check-providers");
  button.disabled = true;
  try {
    const result = await post("/api/providers");
    const issues = Object.values(result.errors);
    report(issues.length ? issues.join(" ") : result.catalogue + " NVIDIA models and " + result.voices + " voice variants discovered.");
    await refresh();
  } catch (error) { report(error.message); }
  finally { button.disabled = false; }
});
for (const close of document.querySelectorAll("[data-close]")) close.addEventListener("click", () => $(close.dataset.close).close());
$("open-mission").addEventListener("click", () => {
  $("dependency").replaceChildren(new Option("None", ""), ...(current?.tasks || []).map((task) => new Option(task.title, task.id)));
  $("form-error").hidden = true;
  $("mission-dialog").showModal();
});
$("workflow").addEventListener("change", () => {
  const brief = $("workflow").value === "brief";
  $("objective-field").hidden = !brief;
  $("candidate-fields").hidden = brief;
});
$("load-preset").addEventListener("click", () => {
  const candidates = current?.presets.hyderabad_studios;
  if (!candidates) return;
  $("mission-title").value = "Hyderabad pottery studio website review";
  $("candidates").value = candidates.map((candidate) => candidate.name + " | " + candidate.url).join("\n");
  $("directory-url").value = "";
  $("business-search").value = "";
});
$("mission-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  $("queue-mission").disabled = true;
  const workflow = $("workflow").value;
  const payload = {title:$("mission-title").value, workflow, priority:Number($("priority").value)};
  if ($("run-at").value) payload.run_at = new Date($("run-at").value).getTime() / 1000;
  if ($("dependency").value) payload.depends_on = $("dependency").value;
  if (workflow === "brief") payload.objective = $("objective").value;
  else {
    if ($("design-assist").checked) payload.design_assist = true;
    if ($("directory-url").value.trim()) payload.directory_url = $("directory-url").value.trim();
    if ($("business-search").value.trim()) payload.business_search = $("business-search").value.trim();
    payload.candidates = $("candidates").value.split("\n").filter((line) => line.trim()).map((line) => {
      const [name, url] = line.split("|");
      return {name:name.trim(), url:url?.trim() || ""};
    });
  }
  try {
    const repeatHours = Number($("repeat-hours").value);
    if (repeatHours) {
      const firstAt = payload.run_at;
      delete payload.run_at;
      const schedule = {mission:payload, every_hours:repeatHours};
      if (firstAt) schedule.first_at = firstAt;
      await post("/api/schedules", schedule);
      $("mission-dialog").close();
      document.querySelector(".schedules").open = true;
      await loadSchedules();
      report("Recurring schedule created.");
      return;
    }
    const response = await post("/api/tasks", payload);
    $("mission-dialog").close();
    report(response.created ? "Mission queued." : "This mission is already queued.");
    await refresh();
  } catch (error) {
    $("form-error").textContent = error.message;
    $("form-error").hidden = false;
  } finally { $("queue-mission").disabled = false; }
});

let socket;
let reconnect;
let generation = -1;
let micEnabled = false;
let wakeMode = false;
let awake = false;
let awakeUntil = 0;
let wakePhrase = "Hey Nova";
let openingMic = false;
let media;
let audioContext;
let micNode;
let playback;
let playbackGain;
let playbackAnalyser;
let scheduledUntil = 0;
let audioClock;
const pcmSources = new Set();
let audioQueue = [];
let playing = false;
let recording = false;
let turnPending = false;
let quietFrames = 0;
let voicedFrames = 0;
let capturedFrames = 0;
let preRoll = [];
let currentAnswer;
let utteranceEnd;
let firstAudioMs;
let latestTiming;
let micSamples;
let waveFrame = 0;
const wave = $("waveform");
const waveContext = wave.getContext("2d");
const speakerSamples = new Float32Array(512);

function voiceStatus(state, label) {
  if ($("voice-state").dataset.state === state && $("voice-state").textContent === label) return;
  $("voice-state").dataset.state = state;
  $("voice-state").textContent = label;
  $("orb").dataset.state = state;
}
function readyState() {
  if (playing) voiceStatus("speaking","Speaking");
  else if (recording) voiceStatus("listening","Listening");
  else if (turnPending) voiceStatus("processing","Processing");
  else if (wakeMode && !awake) voiceStatus("standby", "Say “" + wakePhrase + "”");
  else voiceStatus("ready", micEnabled ? (wakeMode ? "Awake" : "Listening") : "Ready");
  scheduleWave();
}
function setTranscript(open) {
  $("voice-detail").hidden = !open;
  $("voice-expand").setAttribute("aria-expanded", String(open));
}
function displayVoiceMode(mode) {
  if (!mode || mode === "auto") return;
  $("voice-profile-status").textContent = displayName(mode);
  $("voice-profile-status").hidden = false;
}
function scheduleWave() {
  if (!waveContext || waveFrame || document.hidden) return;
  waveFrame = requestAnimationFrame(drawWave);
}
function drawWave() {
  waveFrame = 0;
  if (document.hidden) return;
  const speaking = playing && playbackAnalyser;
  if (speaking) playbackAnalyser.getFloatTimeDomainData(speakerSamples);
  const input = speaking ? speakerSamples : micEnabled ? micSamples : null;
  const scale = speaking ? 1 : 32768;
  waveContext.clearRect(0, 0, wave.width, wave.height);
  if (!input) return;
  waveContext.strokeStyle = speaking ? "#f1b078" : "#b4e1c7";
  waveContext.lineWidth = 2.4;
  waveContext.lineCap = "round";
  const bars = 26;
  const center = wave.height / 2;
  waveContext.beginPath();
  for (let index = 0; index < bars; index += 1) {
    const from = Math.floor(index * input.length / bars);
    const until = Math.floor((index + 1) * input.length / bars);
    let sumSquares = 0;
    for (let sample = from; sample < until; sample += 1) sumSquares += (input[sample] / scale) ** 2;
    const strength = Math.min(1, Math.sqrt(sumSquares / Math.max(1, until - from)) * 4.2);
    const halfHeight = 1.2 + strength * (center - 2);
    const position = (index + .5) * wave.width / bars;
    waveContext.moveTo(position, center - halfHeight);
    waveContext.lineTo(position, center + halfHeight);
  }
  waveContext.stroke();
  if (speaking) scheduleWave();
}
function clearAudio() {
  clearTimeout(audioClock);
  for (const source of pcmSources) source.stop();
  pcmSources.clear();
  scheduledUntil = 0;
  if (playback) {
    playback.player.pause();
    playback.node?.disconnect();
    URL.revokeObjectURL(playback.url);
    playback = null;
  }
  audioQueue = [];
  playing = false;
  scheduleWave();
}
function updateTiming() {
  const timing = [];
  if (latestTiming?.first_text_ms !== null && latestTiming?.first_text_ms !== undefined) timing.push("First text " + latestTiming.first_text_ms + " ms");
  if (firstAudioMs !== undefined) timing.push("First audio " + firstAudioMs + " ms");
  if (Number.isFinite(latestTiming?.turn_ms)) timing.push("Turn " + latestTiming.turn_ms + " ms");
  $("voice-metrics").textContent = timing.join(" · ");
}
function recordFirstAudio() {
  if (utteranceEnd === undefined || firstAudioMs !== undefined) return;
  firstAudioMs = Math.round(performance.now() - utteranceEnd);
  sendVoice({type:"playback_started", generation, delay_ms:firstAudioMs});
  updateTiming();
}
function playNext() {
  if (pcmSources.size) return;
  if (!micEnabled || recording || playback || !audioQueue.length) {
    if (!playback) playing = false;
    readyState();
    return;
  }
  const binary = Uint8Array.from(atob(audioQueue.shift()), (character) => character.charCodeAt(0));
  const url = URL.createObjectURL(new Blob([binary], {type:"audio/wav"}));
  const player = new Audio(url);
  const thisGeneration = generation;
  const node = audioContext?.createMediaElementSource(player);
  if (node && playbackGain) node.connect(playbackGain);
  playback = {player, url, node};
  if (!node) player.volume = Number($("volume").value);
  player.playbackRate = Number($("rate").value);
  playing = true;
  readyState();
  const finished = () => {
    if (playback?.player !== player) return;
    node?.disconnect();
    URL.revokeObjectURL(url);
    playback = null;
    playing = false;
    if (thisGeneration === generation) playNext();
  };
  player.addEventListener("ended", finished, {once:true});
  player.addEventListener("error", finished, {once:true});
  player.addEventListener("playing", recordFirstAudio, {once:true});
  player.play().catch(finished);
}
function playPCM(base64) {
  if (!micEnabled || !audioContext || !playbackGain || recording || playback) return;
  const currentTime = audioContext.currentTime;
  if (pcmSources.size >= 240 || scheduledUntil > currentTime + 45) return;
  const bytes = Uint8Array.from(atob(base64), (character) => character.charCodeAt(0));
  if (!bytes.length || bytes.length % 2) return;
  const samples = new Int16Array(bytes.buffer);
  const buffer = audioContext.createBuffer(1, samples.length, 16000);
  const channel = buffer.getChannelData(0);
  for (let index = 0; index < samples.length; index += 1) channel[index] = samples[index] / 32768;
  const source = audioContext.createBufferSource();
  source.buffer = buffer;
  source.playbackRate.value = Number($("rate").value);
  source.connect(playbackGain);
  const start = Math.max(scheduledUntil, currentTime + .055);
  const first = !pcmSources.size;
  pcmSources.add(source);
  source.start(start);
  scheduledUntil = start + buffer.duration / source.playbackRate.value;
  source.onended = () => {
    if (!pcmSources.delete(source)) return;
    source.disconnect();
    if (!pcmSources.size) {
      playing = false;
      playNext();
    }
  };
  if (first && utteranceEnd !== undefined && firstAudioMs === undefined) {
    audioClock = setTimeout(recordFirstAudio, Math.max(0, (start - currentTime) * 1000));
  }
  playing = true;
  readyState();
}
function sendVoice(message) {
  if (socket?.readyState !== WebSocket.OPEN) return false;
  socket.send(JSON.stringify(message));
  return true;
}
let turnSteps = null;
let pendingMetrics = null;
let turnEvidence = [];
let thinking = null;
function scrollChat() {
  const log = $("response");
  requestAnimationFrame(() => { log.scrollTop = log.scrollHeight; });
}
function trimChat() {
  const log = $("response");
  while (log.children.length > 60) log.firstElementChild.remove();
}
function addMessage(role, text) {
  const node = el("div", text, "msg " + role);
  $("response").append(node);
  trimChat();
  scrollChat();
  return node;
}
function showThinking() {
  if (thinking) return;
  thinking = el("div", undefined, "msg nova thinking");
  thinking.append(el("i"), el("i"), el("i"));
  $("response").append(thinking);
  scrollChat();
}
function hideThinking() {
  thinking?.remove();
  thinking = null;
}
function showStep(packet) {
  if (!turnSteps) {
    turnSteps = el("div", undefined, "steps");
    if (thinking) thinking.before(turnSteps); else $("response").append(turnSteps);
  }
  let chip = [...turnSteps.children].find((node) => node.dataset.label === packet.label && node.dataset.state === "running");
  if (!chip) {
    chip = el("span", undefined, "step");
    chip.dataset.label = packet.label;
    turnSteps.append(chip);
  }
  chip.dataset.state = packet.state;
  chip.replaceChildren(document.createTextNode(packet.label));
  if (packet.ms !== undefined) chip.append(el("small", (packet.ms / 1000).toFixed(1) + "s"));
  scrollChat();
}
function sendText(text) {
  clearAudio();
  recording = false;
  voicedFrames = 0;
  preRoll = [];
  utteranceEnd = firstAudioMs = latestTiming = undefined;
  if (sendVoice({type:"text", text})) {
    setTranscript(true);
    addMessage("user", text);
    turnSteps = null;
    currentAnswer = null;
    showThinking();
    return true;
  }
  report("The conversation connection is reconnecting.");
  return false;
}
async function openOutboxMessage(id) {
  mailFolder = "all";
  for (const tab of document.querySelectorAll("[data-folder]")) tab.setAttribute("aria-selected", String(tab.dataset.folder === "all"));
  selectedMail = id;
  location.hash = "communications";
  await refresh();
}
function chime() {
  if (!audioContext) return;
  const now = audioContext.currentTime;
  for (const [index, freq] of [[0, 660], [1, 990]]) {
    const osc = audioContext.createOscillator();
    const gain = audioContext.createGain();
    osc.type = "sine";
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0, now + index * .11);
    gain.gain.linearRampToValueAtTime(.12 * Number($("volume").value), now + index * .11 + .02);
    gain.gain.exponentialRampToValueAtTime(.0001, now + index * .11 + .22);
    osc.connect(gain).connect(audioContext.destination);
    osc.start(now + index * .11);
    osc.stop(now + index * .11 + .25);
  }
}
function setWakeButton() {
  const button = $("wake-toggle");
  button.setAttribute("aria-pressed", String(wakeMode));
  button.textContent = wakeMode ? "Wake word on" : "Wake word";
  button.title = "Say “" + wakePhrase + "” to wake NOVA. Audio is checked on this Mac until you wake it.";
}
async function armWake(enabled) {
  if (enabled && !micEnabled) {
    await openMic();
    if (!micEnabled) return false;
  }
  wakeMode = enabled;
  awake = false;
  try { localStorage.setItem("nova.wake", enabled ? "1" : "0"); } catch {}
  sendVoice({type:"standby", enabled});
  setWakeButton();
  readyState();
  return true;
}
function setupVoice() {
  const ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/voice");
  socket = ws;
  ws.onopen = () => {
    if (socket !== ws) return;
    $("send").disabled = false;
    generation = -1;
    sendVoice({type:"voice", enabled:micEnabled, voice:$("voice-choice").value});
    if (conversationTask) selectConversationTask(conversationTask);
    if ($("voice-profile").value !== "auto") sendVoice({type:"mode", mode:$("voice-profile").value});
    if (wakeMode) sendVoice({type:"standby", enabled:true});
  };
  ws.onclose = () => {
    if (socket !== ws) return;
    clearAudio();
    turnPending = recording = false;
    $("send").disabled = true;
    readyState();
    clearTimeout(reconnect);
    reconnect = setTimeout(setupVoice, 1600);
  };
  ws.onmessage = ({data}) => {
    const packet = JSON.parse(data);
    if (packet.generation < generation) return;
    if (packet.mode) displayVoiceMode(packet.mode);
    if (packet.type === "clear") {
      generation = packet.generation;
      clearAudio();
      currentAnswer = null;
      turnPending = false;
      readyState();
    } else if (packet.type === "processing") {
      turnPending = true;
      if (!thinking && !currentAnswer) showThinking();
      readyState();
    } else if (packet.type === "transcript") {
      setTranscript(true);
      const partial = $("response").querySelector(".msg.user.partial");
      if (partial) { partial.textContent = packet.text; partial.classList.remove("partial"); }
      else addMessage("user", packet.text);
      turnSteps = null;
      currentAnswer = null;
      showThinking();
    } else if (packet.type === "partial") {
      setTranscript(true);
      const partial = $("response").querySelector(".msg.user.partial") || addMessage("user partial", "");
      partial.textContent = packet.text;
      scrollChat();
    } else if (packet.type === "wake") {
      awake = true;
      awakeUntil = performance.now() + 12000;
      chime();
      setTranscript(true);
      currentAnswer = null;
      turnSteps = null;
      readyState();
    } else if (packet.type === "sleep") {
      awakeUntil = 0;
    } else if (packet.type === "standby_state") {
      wakePhrase = packet.phrase || wakePhrase;
      setWakeButton();
      readyState();
    } else if (packet.type === "metrics") {
      const parts = [packet.calls + (packet.calls === 1 ? " model call" : " model calls")];
      if (packet.tokens) parts.push(compact.format(packet.tokens) + " tokens");
      if (packet.ms) parts.push((packet.ms / 1000).toFixed(1) + " s");
      if (packet.skills?.length) parts.push("skills: " + packet.skills.join(", "));
      pendingMetrics = el("div", undefined, "turn-footer");
      pendingMetrics.append(el("div", parts.join(" · "), "turn-metrics"));
      const check = packet.verification || {};
      if (check.tool_calls) {
        const box = el("details", undefined, "evidence");
        const okFetches = turnEvidence.filter((item) => item.status === "cache" || (item.status >= 200 && item.status < 300)).length;
        const flagged = check.unverified_sites || [];
        const summary = el("summary", (flagged.length ? "⚠ " : "✓ ") + check.tool_calls + " tool calls · " + turnEvidence.length +
          " sources fetched (" + okFetches + " OK)" + (flagged.length ? " · unverified: " + flagged.join(", ") : " · answer checked against sources"));
        box.dataset.state = flagged.length ? "warn" : "ok";
        const list = el("ul");
        for (const item of turnEvidence.slice(0, 20)) {
          const row = el("li");
          const target = item.url.startsWith("http") ? link(item.url.replace(/^https?:\/\//, "").slice(0, 70), item.url) : el("span", item.url.slice(0, 70));
          row.append(el("span", String(item.status), "ev-status"), target,
            el("span", [item.provider, item.bytes ? Math.round(item.bytes / 1024) + " KB" : "", "sha " + item.sha].filter(Boolean).join(" · "), "ev-meta"));
          list.append(row);
        }
        box.append(summary, list);
        pendingMetrics.append(box);
      }
      turnEvidence = [];
    } else if (packet.type === "step") {
      showStep(packet);
      if (packet.evidence?.length) turnEvidence.push(...packet.evidence.map((item) => ({...item, tool: packet.label})));
    } else if (packet.type === "delta") {
      hideThinking();
      if (!currentAnswer) {
        setTranscript(true);
        currentAnswer = addMessage("nova", "");
      }
      currentAnswer.append(packet.text);
      scrollChat();
    } else if (packet.type === "action") {
      if (packet.task_id) conversationTask = packet.task_id;
      const controls = el("div", undefined, "voice-result-actions");
      for (const item of packet.links || []) {
        const anchor = el("a", item.label, "secondary whatsapp");
        anchor.href = item.url;
        anchor.target = "_blank";
        anchor.rel = "noopener noreferrer";
        controls.append(anchor);
      }
      if (packet.message_id) controls.append(action("Review email", () => openOutboxMessage(packet.message_id).catch((error) => report(error.message)), "secondary"));
      if (packet.draft_id) controls.append(action("Review delivery", async () => {
        const {drafts} = await api("/api/drafts?task_id=" + encodeURIComponent(packet.task_id));
        const draft = drafts.find((item) => item.id === packet.draft_id);
        if (draft) await openEmail(draft);
      }, "secondary"));
      if (packet.task_id) controls.append(action("View mission", () => inspectTask(packet.task_id), "secondary"));
      if (packet.view && packet.view !== "overview" && !packet.message_id) {
        controls.append(action("Open " + (titles[packet.view] || packet.view), () => { location.hash = packet.view; }, "secondary"));
        if (!packet.task_id) location.hash = packet.view;
      }
      if (controls.children.length) { $("response").append(controls); scrollChat(); }
      queueRefresh();
    } else if (packet.type === "pcm") {
      playPCM(packet.data);
    } else if (packet.type === "audio") {
      if (micEnabled && audioQueue.length < 4) {
        audioQueue.push(packet.data);
        playNext();
      }
    } else if (packet.type === "error" || packet.type === "voice_error") {
      hideThinking();
      setTranscript(true);
      addMessage("error", packet.message);
    } else if (packet.type === "done") {
      hideThinking();
      if (pendingMetrics) { $("response").append(pendingMetrics); pendingMetrics = null; scrollChat(); }
      if (wakeMode && awake) awakeUntil = Math.max(awakeUntil, performance.now() + 8000);
      $("response").querySelector(".msg.user.partial")?.remove();
      turnPending = false;
      latestTiming = packet;
      readyState();
      updateTiming();
    }
  };
}
function finishRecording() {
  recording = false;
  preRoll = [];
  utteranceEnd = performance.now();
  firstAudioMs = undefined;
  latestTiming = undefined;
  turnPending = sendVoice({type:"audio_end"});
  readyState();
}
function captureFrame({data}) {
  if (!micEnabled) return;
  const pcm = new Int16Array(data);
  if (!playing && !document.hidden) {
    micSamples = pcm;
    scheduleWave();
  }
  if (socket?.readyState !== WebSocket.OPEN) return;
  if (playing && !$("headphones").checked) return;
  if (wakeMode && awake && !recording && !turnPending && performance.now() > awakeUntil) {
    awake = false;
    readyState();
  }
  if (wakeMode && !awake) {
    if (socket.bufferedAmount < 32000) socket.send(data);
    return;
  }
  if (socket.bufferedAmount > 32000) {
    if (recording) {
      recording = false;
      sendVoice({type:"interrupt"});
      voiceStatus("ready","Network busy");
    }
    return;
  }
  const rms = Math.sqrt(pcm.reduce((sum, sample) => sum + sample * sample, 0) / pcm.length);
  const voiced = rms > 560;
  if (!recording) {
    preRoll.push(data);
    if (preRoll.length > 8) preRoll.shift();
    voicedFrames = voiced ? voicedFrames + 1 : 0;
    if (voicedFrames < 3) return;
    clearAudio();
    sendVoice({type:"audio_start"});
    for (const item of preRoll) socket.send(item);
    recording = true;
    quietFrames = 0;
    capturedFrames = preRoll.length;
    preRoll = [];
    readyState();
    return;
  }
  socket.send(data);
  capturedFrames += 1;
  quietFrames = voiced ? 0 : quietFrames + 1;
  if (quietFrames > 23 || capturedFrames >= 590) finishRecording();
}
async function closeMic() {
  micEnabled = false;
  if (wakeMode) {
    wakeMode = false;
    awake = false;
    sendVoice({type:"standby", enabled:false});
    setWakeButton();
  }
  recording = false;
  turnPending = false;
  voicedFrames = 0;
  preRoll = [];
  clearAudio();
  media?.getTracks().forEach((track) => track.stop());
  media = null;
  micNode?.disconnect();
  micNode = null;
  const context = audioContext;
  audioContext = null;
  playbackGain = null;
  playbackAnalyser = null;
  micSamples = null;
  if (context) await context.close();
  sendVoice({type:"voice", enabled:false});
  $("voice-toggle").textContent = "Enable microphone";
  $("voice-toggle").setAttribute("aria-pressed","false");
  readyState();
}
$("voice-toggle").addEventListener("click", async () => {
  if (micEnabled) { await closeMic(); return; }
  await openMic();
});
async function openMic() {
  if (micEnabled || openingMic) return;
  if (!navigator.mediaDevices || typeof AudioWorkletNode === "undefined") {
    report("Microphone capture is unavailable in this browser.");
    return;
  }
  openingMic = true;
  $("voice-toggle").disabled = true;
  try {
    audioContext = new AudioContext();
    await audioContext.resume();
    playbackGain = audioContext.createGain();
    playbackAnalyser = audioContext.createAnalyser();
    playbackAnalyser.fftSize = speakerSamples.length;
    playbackGain.gain.value = Number($("volume").value);
    playbackGain.connect(playbackAnalyser);
    playbackAnalyser.connect(audioContext.destination);
    media = await navigator.mediaDevices.getUserMedia({audio:{channelCount:1, echoCancellation:true, noiseSuppression:true, autoGainControl:true}});
    await audioContext.audioWorklet.addModule("/static/mic.js");
    micNode = new AudioWorkletNode(audioContext, "nova-mic", {numberOfOutputs:0});
    audioContext.createMediaStreamSource(media).connect(micNode);
    micNode.port.onmessage = captureFrame;
    micEnabled = true;
    sendVoice({type:"voice", enabled:true, voice:$("voice-choice").value});
    $("voice-toggle").textContent = "Disable microphone";
    $("voice-toggle").setAttribute("aria-pressed","true");
    setTranscript(true);
    readyState();
  } catch (error) {
    await closeMic();
    report("Microphone unavailable. " + error.name + ".");
  } finally {
    openingMic = false;
    $("voice-toggle").disabled = false;
  }
}
$("wake-toggle").addEventListener("click", () => armWake(!wakeMode).catch((error) => report(error.message)));
{
  let saved = "0";
  try { saved = localStorage.getItem("nova.wake") || "0"; } catch {}
  if (saved === "1") {
    // Browsers need a user gesture before audio starts; arm on the first click or key press.
    const arm = () => {
      document.removeEventListener("pointerdown", arm);
      document.removeEventListener("keydown", arm);
      if (!wakeMode) armWake(true).catch(() => {});
    };
    document.addEventListener("pointerdown", arm);
    document.addEventListener("keydown", arm);
    report("Wake word is ready: click anywhere to start listening for “Hey Nova”.");
  }
}
$("voice-choice").addEventListener("change", () => sendVoice({type:"voice", enabled:micEnabled, voice:$("voice-choice").value}));
$("voice-profile").addEventListener("change", () => {
  const mode = $("voice-profile").value;
  sendVoice({type:"mode", mode});
  if (mode === "auto") $("voice-profile-status").hidden = true;
  else displayVoiceMode(mode);
});
$("volume").addEventListener("input", () => {
  if (playback && !playback.node) playback.player.volume = Number($("volume").value);
  if (playbackGain) playbackGain.gain.value = Number($("volume").value);
});
$("rate").addEventListener("input", () => { if (playback) playback.player.playbackRate = Number($("rate").value); });
function interruptAudio() {
  clearAudio();
  recording = false;
  turnPending = false;
  voicedFrames = 0;
  preRoll = [];
  sendVoice({type:"interrupt"});
  readyState();
}
function setSidebar(collapsed, persist = true) {
  document.body.classList.toggle("sidebar-collapsed", collapsed);
  $("sidebar-toggle").setAttribute("aria-expanded", String(!collapsed));
  $("sidebar-toggle").title = (collapsed ? "Expand" : "Collapse") + " sidebar ( [ )";
  if (persist) try { localStorage.setItem("nova.sidebar", collapsed ? "collapsed" : "open"); } catch {}
}
$("sidebar-toggle").addEventListener("click", () => setSidebar(!document.body.classList.contains("sidebar-collapsed")));
try { if (localStorage.getItem("nova.sidebar") === "collapsed") setSidebar(true, false); } catch {}
document.addEventListener("keydown", (event) => {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName) || document.activeElement?.isContentEditable;
  if (event.key === "[" && !typing && !event.metaKey && !event.ctrlKey && !document.querySelector("dialog[open]")) {
    event.preventDefault();
    setSidebar(!document.body.classList.contains("sidebar-collapsed"));
  }
});
$("interrupt").addEventListener("click", interruptAudio);
$("voice-expand").addEventListener("click", () => setTranscript($("voice-detail").hidden));
document.addEventListener("keydown", (event) => {
  if (event.defaultPrevented || document.querySelector("dialog[open]")) return;
  if (event.altKey && event.key.toLowerCase() === "v") {
    event.preventDefault();
    $("text").focus();
  }
  if (event.key === "Escape" && (playing || recording || turnPending)) interruptAudio();
});
document.addEventListener("visibilitychange", () => {
  document.body.toggleAttribute("data-page-hidden", document.hidden);
  if (document.hidden) {
    cancelAnimationFrame(waveFrame);
    waveFrame = 0;
  } else scheduleWave();
});
$("chat").addEventListener("submit", (event) => {
  event.preventDefault();
  const text = $("text").value.trim();
  if (text && sendText(text)) $("text").value = "";
});
$("clear-conversation").addEventListener("click", () => { $("response").replaceChildren(); turnSteps = null; currentAnswer = null; });
$("send").disabled = true;
setupVoice();
refresh().catch((error) => report(error.message));
