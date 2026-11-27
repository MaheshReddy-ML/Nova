const $ = (id) => document.getElementById(id);
const el = (tag, value, className) => {
  const node = document.createElement(tag);
  if (value !== undefined) node.textContent = value;
  if (className) node.className = className;
  return node;
};
const formatState = (state) => state.replaceAll("_", " ");
const terminal = new Set(["completed", "failed", "cancelled"]);
const money = new Intl.NumberFormat("en-IN", {style: "currency", currency: "INR", maximumFractionDigits: 0});
const clock = new Intl.DateTimeFormat(undefined, {hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false});
const titles = {overview:"Overview", leads:"Customers", projects:"Projects", approvals:"Approvals", models:"Model observatory", memory:"Memory"};
const localHeaders = {"Content-Type":"application/json", "x-nova-owner":"1"};
let current;
let events = [];
let feed;
let refreshTimer;
let lastPage = "";

async function api(path, options) {
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.message || "The request could not be completed.");
  return result;
}
const post = (path, value) => api(path, {method:"POST", headers:localHeaders, body:JSON.stringify(value)});
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
  const anchor = el("a", label);
  anchor.href = href;
  anchor.target = "_blank";
  anchor.rel = "noopener noreferrer";
  return anchor;
}
function pill(state) {
  const badge = el("span", formatState(state), "pill");
  badge.dataset.state = state;
  return badge;
}
function renderList(id, data, emptyMessage) {
  $(id).replaceChildren(...(data.length ? data : [el("p", emptyMessage, "empty")]));
}
function renderEvents() {
  const entries = events.slice(-18).toReversed().map((event) => {
    const item = el("li");
    const time = el("time", clock.format(event.time * 1000));
    time.dateTime = new Date(event.time * 1000).toISOString();
    const message = el("span", event.message);
    if (event.task_id) {
      message.append(" · ", el("small", event.task_id, "tip"));
    }
    item.append(time, message);
    return item;
  });
  const empty = el("li", "Mission and provider events will appear here.", "text-muted");
  empty.classList.add("empty");
  $("events").replaceChildren(...(entries.length ? entries : [empty]));
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
    renderEvents();
    if (event.kind === "notification" && micEnabled && $("notifications").checked && !playing && !recording && !turnPending) {
      sendVoice({type:"announce", id:event.id});
    }
    if (event.kind === "voice") queueRefresh();
    if (["task","checkpoint","model","approval","system","memory","notification"].includes(event.kind)) queueRefresh();
  };
}
function queueRefresh() {
  if (!refreshTimer) refreshTimer = setTimeout(() => {
    refreshTimer = null;
    refresh().catch((error) => report(error.message));
  }, 300);
}
async function refresh() {
  current = await api("/api/state");
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
      row.append(action(name[0].toUpperCase() + name.slice(1), async () => {
        await post("/api/tasks/" + task.id + "/control", {action:name});
        await refresh();
      }));
    }
  }
  return row;
}
function artifacts(task) {
  const items = el("div", undefined, "links");
  const base = "/projects/" + task.id + "/";
  for (const [name, file] of [["Preview","index.html"],["Desktop","desktop.png"],["Mobile","mobile.png"],["Proposal","proposal.json"]]) {
    items.append(link(name, base + file));
  }
  return items;
}
async function inspectTask(id) {
  const {task, checkpoints, tool_calls, execution_seconds, audit_cache_hits, usage} = await api("/api/tasks/" + id);
  $("detail-title").textContent = task.title;
  const detail = $("detail-body");
  detail.replaceChildren(el("p", formatState(task.state) + " · " + tool_calls + " tool steps · " + execution_seconds + " s"),
      el("p", usage.reduce((count, row) => count + row.calls, 0) + " model calls · " + audit_cache_hits + " audit cache hits", "tip"));

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
      notes.append(item);
    }
    detail.append(el("h3", "Website evidence"), notes);
  }
  if (checkpoints.brief) {
    detail.append(el("p", checkpoints.brief.summary));
    for (const [title, lines] of [["Assumptions", checkpoints.brief.assumptions], ["Next steps", checkpoints.brief.next_steps]]) {
      if (lines.length) {
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
      el("p", draft.rate_basis, "tip"), artifacts(task));
  }
  if (task.error) detail.append(el("p", "Issue: " + formatState(task.error), "form-error"));
  $("details-dialog").showModal();
}
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
  $("open-mission").disabled = current.stopped;
  $("mission-count").textContent = tasks.length ? tasks.length + " recent" : "";
  renderList("tasks", tasks.map((task) => {
    const row = el("article", undefined, "task");
    const head = el("div", undefined, "task-head");
    head.append(action(task.title, () => inspectTask(task.id), "task-title"), pill(task.state));
    row.append(head, el("p", task.id + " · Priority " + task.priority + " · " + task.cursor + " checkpoints", "tip"), controls(task));
    return row;
  }), "No missions yet. Queue a website review or planning brief to start.");
  renderList("lead-list", leads.map((lead) => {
    const row = el("article", undefined, "record");
    const flags = el("ul");
    flags.append(...lead.evidence.findings.map((flag) => el("li", flag.observation)));
    row.append(el("h3", lead.name), el("p", lead.score + "/100 · " + formatState(lead.stage), "tip"),
      link("Public source", lead.url), flags, el("p", lead.evidence.scope, "tip"));
    if (lead.evidence.source_directory) row.append(link("Directory source", lead.evidence.source_directory));
    return row;
  }), "Completed website research will appear here.");
  renderList("project-list", tasks.filter((task) => task.state === "completed" && task.spec.workflow === "website").map((task) => {
    const row = el("article", undefined, "record");
    row.append(el("h3", task.title), el("p", "Chromium verification completed", "tip"), artifacts(task));
    return row;
  }), "Verified website concepts will appear here.");
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
  }), "No proposals are waiting for review.");
  const inventory = el("div", undefined, "record");
  inventory.append(el("h3", "Provider access"), el("p", current.catalogue_count === null ? "Catalogue check pending" : current.catalogue_count + " catalogue models"),
    el("p", money.format(current.spending_limit_inr) + " spending limit · NVIDIA Build trial", "tip"));
  renderList("routes", [inventory, ...Object.entries(routes).map(([capability, model]) => {
    const row = el("div", undefined, "record");
    row.append(el("h3", formatState(capability)), el("p", model || "Awaiting catalogue verification", "tip"));
    return row;
  })], "");
  renderList("usage", usage.map((group) => {
    const row = el("div", undefined, "record");
    row.append(el("h3", formatState(group.capability) + " · " + group.lane),
      el("p", group.calls + " calls · " + (group.mean_ms ?? "—") + " ms mean · " + group.errors + " errors"),
      el("p", "P50 " + (group.p50_ms ?? "—") + " ms · P95 " + (group.p95_ms ?? "—") + " ms", "tip"),
      el("p", group.lane === "speech" ? "Audio request metrics" :
        (group.reported_tokens ?? "—") + " reported tokens · " + (group.estimated_tokens ?? "—") + " estimated tokens", "tip"));
    return row;
  }), "NVIDIA request metrics will appear here.");
  $("voice-toggle").disabled = !voice.enabled;
  $("voice-mode").textContent = (voice.asr_streaming ? "NVIDIA live transcription. " : "NVIDIA transcribes after each utterance. ") +
    "With speakers, use Stop audio before speaking over playback.";
  const select = $("voice-choice");
  const last = select.value;
  const available = voice.voices.filter((name) => name.toUpperCase().includes("." + voice.language.toUpperCase() + "."));
  if (available.join("|") !== select.dataset.options) {
    select.replaceChildren(new Option("Configured Magpie voice", ""), ...available.map((name) => new Option(name.split(".").slice(2).join(" · "), name)));
    select.value = available.includes(last) ? last : "";
    select.dataset.options = available.join("|");
  }
}
function routePage() {
  const page = location.hash.substring(1);
  const selected = Object.hasOwn(titles, page) ? page : "overview";
  for (const section of document.querySelectorAll(".view")) section.hidden = section.id !== selected;
  for (const anchor of document.querySelectorAll(".sidebar nav a")) {
    if (anchor.hash === "#" + selected) anchor.setAttribute("aria-current", "page");
    else anchor.removeAttribute("aria-current");
  }
  $("breadcrumb").textContent = titles[selected];
  if (lastPage !== selected && selected === "memory") searchMemory().catch((error) => report(error.message));
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
    if ($("directory-url").value.trim()) payload.directory_url = $("directory-url").value.trim();
    payload.candidates = $("candidates").value.split("\n").filter((line) => line.trim()).map((line) => {
      const [name, url] = line.split("|");
      return {name:name.trim(), url:url?.trim() || ""};
    });
  }
  try {
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
let openingMic = false;
let media;
let audioContext;
let micNode;
let playback;
let playbackGain;
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

function voiceStatus(state, label) {
  $("voice-state").dataset.state = state;
  $("voice-state").textContent = label;
}
function readyState() {
  if (playing) voiceStatus("speaking","Speaking");
  else if (recording) voiceStatus("listening","Listening");
  else if (turnPending) voiceStatus("processing","Processing");
  else voiceStatus("ready", micEnabled ? "Listening" : "Ready");
}
function clearAudio() {
  clearTimeout(audioClock);
  for (const source of pcmSources) source.stop();
  pcmSources.clear();
  scheduledUntil = 0;
  if (playback) {
    playback.player.pause();
    URL.revokeObjectURL(playback.url);
    playback = null;
  }
  audioQueue = [];
  playing = false;
}
function updateTiming() {
  const timing = [];
  if (latestTiming?.first_text_ms !== null && latestTiming?.first_text_ms !== undefined) timing.push("First text " + latestTiming.first_text_ms + " ms");
  if (firstAudioMs !== undefined) timing.push("First audio " + firstAudioMs + " ms");
  if (latestTiming?.turn_ms !== undefined) timing.push("Turn " + latestTiming.turn_ms + " ms");
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
  playback = {player, url};
  player.volume = Number($("volume").value);
  player.playbackRate = Number($("rate").value);
  playing = true;
  readyState();
  const finished = () => {
    if (playback?.player !== player) return;
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
  if (pcmSources.size >= 160 || scheduledUntil > currentTime + 18) return;
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
function setupVoice() {
  const ws = new WebSocket((location.protocol === "https:" ? "wss://" : "ws://") + location.host + "/voice");
  socket = ws;
  ws.onopen = () => {
    if (socket !== ws) return;
    $("send").disabled = false;
    generation = -1;
    sendVoice({type:"voice", enabled:micEnabled, voice:$("voice-choice").value});
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
    if (packet.type === "clear") {
      generation = packet.generation;
      clearAudio();
      currentAnswer = null;
      turnPending = false;
      readyState();
    } else if (packet.type === "processing") {
      turnPending = true;
      readyState();
    } else if (packet.type === "transcript") {
      $("response").replaceChildren(el("strong", "You said: " + packet.text));
    } else if (packet.type === "partial") {
      $("response").replaceChildren(el("strong", "Listening: " + packet.text));
    } else if (packet.type === "delta") {
      if (!currentAnswer) {
        currentAnswer = el("p", "");
        $("response").append(currentAnswer);
      }
      currentAnswer.append(packet.text);
    } else if (packet.type === "pcm") {
      playPCM(packet.data);
    } else if (packet.type === "audio") {
      if (micEnabled && audioQueue.length < 4) {
        audioQueue.push(packet.data);
        playNext();
      }
    } else if (packet.type === "error" || packet.type === "voice_error") {
      $("response").append(el("p", packet.message, "form-error"));
    } else if (packet.type === "done") {
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
  if (!micEnabled || socket?.readyState !== WebSocket.OPEN) return;
  if (playing && !$("headphones").checked) return;
  if (socket.bufferedAmount > 32000) {
    if (recording) {
      recording = false;
      sendVoice({type:"interrupt"});
      voiceStatus("ready","Network busy");
    }
    return;
  }
  const pcm = new Int16Array(data);
  const rms = Math.sqrt(pcm.reduce((sum, sample) => sum + sample * sample, 0) / pcm.length);
  const voiced = rms > 560;
  if (!recording) {
    preRoll.push(data);
    if (preRoll.length > 8) preRoll.shift();
    voicedFrames = voiced ? voicedFrames + 1 : 0;
    if (voicedFrames < 3) return;
    clearAudio();
    $("response").replaceChildren();
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
  if (context) await context.close();
  sendVoice({type:"voice", enabled:false});
  $("voice-toggle").textContent = "Enable microphone";
  $("voice-toggle").setAttribute("aria-pressed","false");
  readyState();
}
$("voice-toggle").addEventListener("click", async () => {
  if (micEnabled) { await closeMic(); return; }
  if (openingMic) return;
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
    playbackGain.gain.value = Number($("volume").value);
    playbackGain.connect(audioContext.destination);
    media = await navigator.mediaDevices.getUserMedia({audio:{channelCount:1, echoCancellation:true, noiseSuppression:true, autoGainControl:true}});
    await audioContext.audioWorklet.addModule("/static/mic.js");
    micNode = new AudioWorkletNode(audioContext, "nova-mic", {numberOfOutputs:0});
    audioContext.createMediaStreamSource(media).connect(micNode);
    micNode.port.onmessage = captureFrame;
    micEnabled = true;
    sendVoice({type:"voice", enabled:true, voice:$("voice-choice").value});
    $("voice-toggle").textContent = "Disable microphone";
    $("voice-toggle").setAttribute("aria-pressed","true");
    readyState();
  } catch (error) {
    await closeMic();
    report("Microphone unavailable. " + error.name + ".");
  } finally {
    openingMic = false;
    $("voice-toggle").disabled = false;
  }
});
$("voice-choice").addEventListener("change", () => sendVoice({type:"voice", enabled:micEnabled, voice:$("voice-choice").value}));
$("volume").addEventListener("input", () => {
  if (playback) playback.player.volume = Number($("volume").value);
  if (playbackGain) playbackGain.gain.value = Number($("volume").value);
});
$("rate").addEventListener("input", () => { if (playback) playback.player.playbackRate = Number($("rate").value); });
$("interrupt").addEventListener("click", () => {
  clearAudio();
  recording = false;
  turnPending = false;
  voicedFrames = 0;
  preRoll = [];
  sendVoice({type:"interrupt"});
  readyState();
});
$("chat").addEventListener("submit", (event) => {
  event.preventDefault();
  const text = $("text").value.trim();
  if (!text) return;
  clearAudio();
  recording = false;
  voicedFrames = 0;
  preRoll = [];
  utteranceEnd = firstAudioMs = latestTiming = undefined;
  if (sendVoice({type:"text", text})) {
    $("response").replaceChildren(el("strong", "You: " + text));
    $("text").value = "";
  } else report("The conversation connection is reconnecting.");
});
$("send").disabled = true;
setupVoice();
refresh().catch((error) => report(error.message));
