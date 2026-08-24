const $ = (sel, root = document) => root.querySelector(sel);
const app = $("#app");

const STYLES = [
  ["explainer", "Explainer"],
  ["listicle", "Listicle"],
  ["story", "Story"],
  ["documentary", "Documentary"],
  ["motivation", "Motivation"],
  ["news", "Briefing"],
];
const MOODS = ["ember", "navy", "teal", "violet", "amber", "steel", "forest", "magenta"];
const STEPS = [
  ["research", "Research"],
  ["script", "Script"],
  ["voice", "Voice"],
  ["visuals", "Visuals"],
  ["thumbnail", "Thumbnails"],
  ["render", "Render"],
  ["publish", "Publish"],
];

let voices = [];
let settings = {};
let yt = { connected: false };

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    method: opts.method || "GET",
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const text = await res.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text }; }
  if (!res.ok) {
    const detail = data?.detail;
    throw new Error(typeof detail === "string" ? detail : (detail ? JSON.stringify(detail) : res.statusText));
  }
  return data;
}

function route() {
  const hash = location.hash.replace(/^#/, "") || "/";
  const parts = hash.split("/").filter(Boolean);
  return { hash, parts, name: parts[0] || "home", id: parts[0] === "p" ? parts[1] : null };
}

function setNav() {
  const r = route();
  document.querySelectorAll("[data-nav]").forEach((el) => {
    const key = el.dataset.nav;
    const on = (key === "home" && (r.name === "home" || r.hash === "/")) || key === r.name;
    el.classList.toggle("active", on);
  });
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function fmtTime(sec) {
  if (!sec && sec !== 0) return "—";
  const s = Math.round(Number(sec));
  const m = Math.floor(s / 60);
  return `${m}:${String(s % 60).padStart(2, "0")}`;
}

function geminiUsage(p) {
  const u = p.gemini_usage || {};
  const writer = p.script?.engine;
  const bits = [];
  if (writer) bits.push("script by " + writer + (p.script?.model ? " (" + p.script.model + ")" : ""));
  if (u.scene_images) bits.push(u.scene_images + " Gemini stills");
  if (u.thumbnail) bits.push("Gemini thumbnail");
  if (!bits.length) {
    return (settings.has_groq ? "Groq writes the script. " : "") +
      (settings.has_gemini ? "Gemini paints each scene." : "Add keys in Settings.");
  }
  return bits.join(" · ") + ". ";
}

async function boot() {
  try {
    [settings, yt] = await Promise.all([
      api("/api/settings"),
      api("/api/youtube/status").catch(() => ({ connected: false })),
    ]);
    const v = await api("/api/voices");
    voices = v.voices || [];
  } catch (err) {
    app.innerHTML = `<p class="toast err">${esc(err.message)}</p>`;
    return;
  }
  render();
}

function render() {
  setNav();
  const r = route();
  if (r.name === "new") return renderNew();
  if (r.name === "autopilot") return renderAutopilot();
  if (r.name === "library") return renderLibrary();
  if (r.name === "channel") return renderChannel();
  if (r.name === "settings") return renderSettings();
  if (r.name === "p" && r.id) return renderStudio(r.id);
  return renderHome();
}

async function renderHome() {
  app.innerHTML = `
    <section class="hero">
      <div class="kicker">YouTube automation floor</div>
      <h1>Write it. Voice it.<br/>Cut it. Ship it.</h1>
      <p class="lede">ChannelForge is a local studio for faceless videos — research, script, voice, motion graphics, thumbnails, render, and YouTube upload in one room.</p>
      <form class="command" id="quick">
        <input name="topic" placeholder="What should we film?  e.g. Why time slows near a black hole" required />
        <button class="btn primary" type="submit">Auto-cut</button>
      </form>
      <div class="chips" id="ideas">
        ${["How black holes warp time", "The sunk cost trap", "Why cities feel louder at night", "A brief history of money", "What attention actually is"].map((t) => `<button class="chip" data-idea="${esc(t)}">${esc(t)}</button>`).join("")}
      </div>
    </section>
    <h2 class="section">On the bench</h2>
    <div id="recent" class="grid"><p class="empty">Loading…</p></div>
  `;
  $("#quick").onsubmit = async (e) => {
    e.preventDefault();
    const topic = e.target.topic.value.trim();
    if (!topic) return;
    await createAndRun({ topic, auto: true, format: settings.default_format || "long", style: settings.default_style || "explainer" });
  };
  $("#ideas").onclick = (e) => {
    const btn = e.target.closest("[data-idea]");
    if (!btn) return;
    $("#quick [name=topic]").value = btn.dataset.idea;
  };
  const { projects } = await api("/api/projects");
  $("#recent").innerHTML = projects.length ? projects.slice(0, 8).map(projectCard).join("") : `<p class="empty">No cuts yet. Start with a topic above.</p>`;
}

function projectCard(p) {
  const art = p.thumbnail?.selected_url || p.visuals?.scenes?.[0]?.url || "/assets/plates/plate_ember.jpg";
  return `<a class="card" href="#/p/${p.id}">
    <div class="thumb" style="background-image:url('${art}')"></div>
    <div class="body">
      <h3>${esc(p.title || p.topic)}</h3>
      <div class="meta">
        <span class="status ${esc(p.status)}">${esc(p.status)}</span>
        <span>${esc(p.format)}</span>
        <span>${esc(p.style)}</span>
      </div>
    </div>
  </a>`;
}

async function renderLibrary() {
  app.innerHTML = `<div class="toprow"><div><div class="kicker">Archive</div><h1>Library</h1></div><a class="btn primary" href="#/new">New cut</a></div><div id="lib" class="grid"></div>`;
  const { projects } = await api("/api/projects");
  $("#lib").innerHTML = projects.length ? projects.map(projectCard).join("") : `<p class="empty">Nothing on the shelf yet.</p>`;
}

function fieldSelect(name, options, value) {
  return `<select name="${name}">${options.map(([v, l]) => `<option value="${v}" ${v === value ? "selected" : ""}>${l}</option>`).join("")}</select>`;
}

async function renderNew() {
  app.innerHTML = `
    <div class="kicker">Slate</div>
    <div class="toprow"><h1>New cut</h1></div>
    <form class="panel" id="slate" style="max-width:760px">
      <label class="field"><span>Topic</span><input name="topic" required placeholder="The thing the video is actually about" /></label>
      <label class="field"><span>Notes / facts you want in (optional)</span><textarea name="notes" placeholder="Paste bullets, claims to avoid, or a rough outline."></textarea></label>
      <div class="form-grid">
        <label class="field"><span>Format</span>${fieldSelect("format", [["long", "16:9 long-form"], ["short", "9:16 Short"]], settings.default_format || "long")}</label>
        <label class="field"><span>Style</span>${fieldSelect("style", STYLES, settings.default_style || "explainer")}</label>
        <label class="field"><span>Target seconds</span><input type="number" name="target_seconds" min="20" max="600" value="${settings.default_format === "short" ? 45 : 150}" /></label>
        <label class="field"><span>Voice</span>${fieldSelect("voice", voices.map((v) => [v.id, v.label]), settings.default_voice || "local:en-us")}</label>
        <label class="field"><span>Visual mood</span>${fieldSelect("visual_mood", MOODS.map((m) => [m, m]), settings.default_mood || "ember")}</label>
      </div>
      <div class="row">
        <button class="btn" name="mode" value="draft" type="submit">Open in studio</button>
        <button class="btn primary" name="mode" value="auto" type="submit">Run full auto-cut</button>
      </div>
      <p class="toast" id="slate-msg"></p>
    </form>
  `;
  const form = $("#slate");
  let mode = "auto";
  form.querySelectorAll("button[name=mode]").forEach((b) => {
    b.onclick = () => { mode = b.value; };
  });
  form.onsubmit = async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(form).entries());
    data.target_seconds = Number(data.target_seconds);
    data.auto = mode === "auto";
    $("#slate-msg").textContent = data.auto ? "Opening the floor…" : "Creating slate…";
    await createAndRun(data);
  };
}

async function createAndRun(payload) {
  const res = await api("/api/projects", { method: "POST", body: payload });
  location.hash = `#/p/${res.project.id}`;
}

async function renderStudio(id) {
  app.innerHTML = `<p class="empty">Loading slate…</p>`;
  let pack;
  try { pack = await api(`/api/projects/${id}`); }
  catch (err) { app.innerHTML = `<p class="toast err">${esc(err.message)}</p>`; return; }
  let project = pack.project;
  let step = firstOpenStep(project);

  const paint = () => {
    const thumb = project.thumbnail?.selected_url;
    const video = project.render?.url;
    const voice = project.voiceover?.url;
    app.innerHTML = `
      <div class="studio">
        <div>
          <div class="toprow">
            <div>
              <div class="kicker">${esc(project.format)} · ${esc(project.style)}</div>
              <h1>${esc(project.title || project.topic)}</h1>
              <div class="meta" style="margin-top:8px">
                <span class="status ${esc(project.status)}">${esc(project.status)}</span>
                <span>${esc(project.topic)}</span>
                <span>${project.script ? project.script.word_count + " words" : "no script yet"}</span>
                <span>${fmtTime(project.voiceover?.duration || project.script?.estimated_seconds)}</span>
              </div>
            </div>
            <div class="row">
              <button class="btn primary" id="auto">Full auto-cut</button>
              <button class="btn ghost" id="del">Delete</button>
            </div>
          </div>
          <div class="steps">
            ${STEPS.map(([k, l]) => `<button data-step="${k}" class="${k === step ? "on" : ""}">${l}</button>`).join("")}
          </div>
          <div class="panel" id="step-panel">${stepHtml(project, step)}</div>
          <div class="progress"><i id="bar"></i></div>
          <p class="toast" id="msg"></p>
        </div>
        <aside class="panel preview">
          <div class="lbl">Preview</div>
          ${video ? `<video controls src="${video}"></video>` : thumb ? `<img src="${thumb}" alt="Thumbnail" />` : `<img src="/assets/plates/plate_${esc(project.visual_mood || "ember")}.jpg" alt="" />`}
          ${voice ? `<audio controls src="${voice}"></audio>` : ""}
          ${project.youtube?.url ? `<p class="toast"><a href="${esc(project.youtube.url)}" target="_blank" rel="noreferrer">Open on YouTube</a></p>` : ""}
          <div class="notice" style="margin-top:14px">
            ${geminiUsage(project)}
            Neural voices (Edge / OpenAI) when the network allows; otherwise local voice.
          </div>
        </aside>
      </div>
    `;
    bindStudio();
  };

  function bindStudio() {
    app.querySelectorAll("[data-step]").forEach((b) => b.onclick = () => { step = b.dataset.step; paint(); });
    $("#auto").onclick = () => run("auto");
    $("#del").onclick = async () => {
      if (!confirm("Delete this cut?")) return;
      await api(`/api/projects/${id}`, { method: "DELETE" });
      location.hash = "#/library";
    };
    const runBtn = $("#run-step");
    if (runBtn) runBtn.onclick = async () => {
      const notes = $("[name=notes]");
      if (notes) {
        const res = await api(`/api/projects/${id}`, { method: "PATCH", body: { notes: notes.value } });
        project = res.project;
      }
      run(step);
    };
    const saveScript = $("#save-script");
    if (saveScript) saveScript.onclick = async () => {
      const title = $("[name=title]").value;
      const full_text = $("[name=full_text]").value;
      const description = $("[name=description]").value;
      $("#msg").textContent = "Saving script…";
      const res = await api(`/api/projects/${id}/script`, { method: "PUT", body: { title, full_text, description } });
      project = res.project;
      $("#msg").textContent = "Script locked. Voice and picture will rebuild from this text.";
      paint();
    };
    const voiceSel = $("[name=voice]");
    if (voiceSel) voiceSel.onchange = async () => {
      const res = await api(`/api/projects/${id}`, { method: "PATCH", body: { voice: voiceSel.value } });
      project = res.project;
    };
    const moodSel = $("[name=visual_mood]");
    if (moodSel) moodSel.onchange = async () => {
      const res = await api(`/api/projects/${id}`, { method: "PATCH", body: { visual_mood: moodSel.value } });
      project = res.project;
    };
    app.querySelectorAll("[data-thumb]").forEach((b) => {
      b.onclick = async () => {
        const res = await api(`/api/projects/${id}`, { method: "PATCH", body: { thumbnail: { selected: b.dataset.thumb } } });
        project = res.project;
        paint();
      };
    });
    const pub = $("#publish");
    if (pub) pub.onclick = () => {
      const privacy = $("[name=privacy]")?.value || "private";
      run("publish", { privacy });
    };
  }

  async function run(kind, payload = {}) {
    $("#msg").textContent = kind === "auto" ? "Running the full floor…" : `Running ${kind}…`;
    $("#bar").style.width = "6%";
    const path = kind === "auto" ? `/api/projects/${id}/auto` : `/api/projects/${id}/${kind}`;
    try {
      const { job } = await api(path, { method: "POST", body: payload });
      await watchJob(job.id, (pack) => {
        project = pack.project || project;
        const pct = Math.round((pack.job.progress || 0) * 100);
        $("#bar").style.width = `${Math.max(6, pct)}%`;
        $("#msg").textContent = pack.job.message || pack.job.step || "";
        if (pack.job.status === "error") $("#msg").classList.add("err");
      });
      const fresh = await api(`/api/projects/${id}`);
      project = fresh.project;
      $("#bar").style.width = "100%";
      $("#msg").textContent = "Done.";
      paint();
    } catch (err) {
      $("#msg").classList.add("err");
      $("#msg").textContent = err.message;
    }
  }

  paint();
  if (pack.job && (pack.job.status === "queued" || pack.job.status === "running")) {
    watchJob(pack.job.id, (tick) => {
      project = tick.project || project;
      if ($("#bar")) $("#bar").style.width = `${Math.round((tick.job.progress || 0) * 100)}%`;
      if ($("#msg")) $("#msg").textContent = tick.job.message || "";
      if (tick.job.status === "done" || tick.job.status === "error") {
        api(`/api/projects/${id}`).then((fresh) => { project = fresh.project; paint(); });
      }
    });
  }
}

function firstOpenStep(p) {
  if (!p.research) return "research";
  if (!p.script) return "script";
  if (!p.voiceover) return "voice";
  if (!p.visuals) return "visuals";
  if (!p.thumbnail) return "thumbnail";
  if (!p.render) return "render";
  return "publish";
}

function stepHtml(p, step) {
  if (step === "research") {
    const r = p.research;
    return `
      <div class="lbl">Briefing</div>
      ${r ? `<p>${esc(r.summary || "")}</p><div class="meta"><span>${esc(r.source)}</span>${r.url ? `<a href="${esc(r.url)}" target="_blank" rel="noreferrer">source</a>` : ""}</div>
        <ul>${(r.facts || []).slice(0, 8).map((f) => `<li>${esc(f)}</li>`).join("")}</ul>` : `<p class="empty">No briefing yet. Pull research from Wikipedia when the network allows, otherwise the writer works from your notes.</p>`}
      <label class="field"><span>Director notes</span><textarea name="notes">${esc(p.notes || "")}</textarea></label>
      <button class="btn primary" id="run-step">Research</button>
    `;
  }
  if (step === "script") {
    const s = p.script || {};
    return `
      <label class="field"><span>Title</span><input name="title" value="${esc(s.title || p.title || "")}" /></label>
      <label class="field"><span>Narration</span><textarea class="script-box" name="full_text">${esc(s.full_text || "")}</textarea></label>
      <label class="field"><span>YouTube description</span><textarea name="description">${esc(s.description || "")}</textarea></label>
      <p class="notice">${s.engine ? `Writer: ${esc(s.engine)}${s.model ? " · " + esc(s.model) : ""}` : "No script yet."}${s.llm_error ? " · Gemini fallback: " + esc(s.llm_error) : ""}</p>
      <div class="row">
        <button class="btn" id="save-script" type="button">Save edits</button>
        <button class="btn primary" id="run-step" type="button">Rewrite script</button>
      </div>
    `;
  }
  if (step === "voice") {
    return `
      <label class="field"><span>Voice</span>${fieldSelect("voice", voices.map((v) => [v.id, `${v.label}`]), p.voice)}</label>
      <p class="notice">${p.voiceover ? `Recorded with ${esc(p.voiceover.engine)} · ${fmtTime(p.voiceover.duration)}` : "No voice yet."}</p>
      <button class="btn primary" id="run-step">Record voice</button>
    `;
  }
  if (step === "visuals") {
    const scenes = p.visuals?.scenes || [];
    return `
      <label class="field"><span>Mood</span>${fieldSelect("visual_mood", MOODS.map((m) => [m, m]), p.visual_mood)}</label>
      <p class="notice">${p.visuals ? `${p.visuals.gemini_images || 0} AI stills · ${p.visuals.motion_clips || 0} motion clips (best of I2V/T2V)${p.visuals.gemini_error ? " · " + esc(p.visuals.gemini_error) : ""}` : "WaveSpeed paints stills, shoots motion, and we keep the best clip per scene."}</p>
      <div class="scene-strip">${scenes.map((s) => `<img src="${s.url}" alt="${esc(s.on_screen || "")}" title="${esc(s.source || "")}" />`).join("")}</div>
      <button class="btn primary" id="run-step" style="margin-top:14px">Design frames</button>
    `;
  }
  if (step === "thumbnail") {
    const t = p.thumbnail;
    return `
      <div class="thumbs">
        ${(t?.variants || []).map((name, i) => `<button data-thumb="${name}" class="${t.selected === name ? "on" : ""}"><img src="${t.urls[i]}" alt="${name}" /></button>`).join("")}
      </div>
      <button class="btn primary" id="run-step" style="margin-top:14px">New thumbnails</button>
    `;
  }
  if (step === "render") {
    return `
      <p class="notice">${p.render ? `Master is ${fmtTime(p.render.duration)} · ${(p.render.size_bytes / 1e6).toFixed(1)} MB` : "Assemble picture, captions, voice, and a low bed of score."}</p>
      <button class="btn primary" id="run-step">Render master</button>
      ${p.render?.url ? `<p class="toast"><a href="${p.render.url}" download>Download MP4</a></p>` : ""}
    `;
  }
  return `
    <p class="notice">${yt.connected ? `Connected${yt.channel?.title ? " as " + esc(yt.channel.title) : ""}.` : "Connect YouTube in Channel to upload. You can still download the MP4 and post it yourself."}</p>
    <label class="field"><span>Privacy</span>${fieldSelect("privacy", [["private", "Private"], ["unlisted", "Unlisted"], ["public", "Public"]], settings.default_privacy || "private")}</label>
    <button class="btn primary" id="publish" ${yt.connected && p.render ? "" : "disabled"}>${yt.connected ? "Upload to YouTube" : "Connect channel first"}</button>
  `;
}

async function watchJob(id, onTick) {
  for (let i = 0; i < 900; i++) {
    const pack = await api(`/api/jobs/${id}`);
    onTick(pack);
    if (pack.job.status === "done" || pack.job.status === "error") {
      if (pack.job.status === "error") throw new Error(pack.job.error || pack.job.message || "Job failed");
      return pack;
    }
    await new Promise((r) => setTimeout(r, 900));
  }
  throw new Error("Timed out waiting for the studio job");
}

async function renderAutopilot() {
  app.innerHTML = `<div class="kicker">Hands-off</div><div class="toprow"><h1>Autopilot</h1></div><p class="empty">Loading schedule…</p>`;
  let pack;
  try {
    pack = await api("/api/autopilot");
  } catch (err) {
    app.innerHTML = `<div class="kicker">Hands-off</div><div class="toprow"><h1>Autopilot</h1></div><p class="toast err">${esc(err.message)}</p><p class="notice">If this is a missing table, restart <code>py -3 run.py</code>.</p>`;
    return;
  }
  const on = !!pack.enabled;
  app.innerHTML = `
    <div class="kicker">Hands-off</div>
    <div class="toprow">
      <div>
        <h1>Autopilot</h1>
        <p class="lede">Reads what is famous right now, writes a video with no prompt from you, then schedules it. Leave the Command Prompt running.</p>
      </div>
      <div class="row">
        <button class="btn ${on ? "" : "primary"}" id="toggle" type="button">${on ? "Pause" : "Start autopilot"}</button>
        <button class="btn primary" id="now" type="button">Make one now</button>
      </div>
    </div>
    <div class="studio">
      <form class="panel" id="ap">
        <div class="form-grid">
          <label class="field"><span>Every (hours)</span><input type="number" name="autopilot_interval_hours" min="1" max="48" value="${esc(pack.interval_hours)}" /></label>
          <label class="field"><span>Max per day</span><input type="number" name="autopilot_daily_cap" min="1" max="12" value="${esc(pack.daily_cap)}" /></label>
          <label class="field"><span>Format</span>${fieldSelect("autopilot_format", [["short", "Short 9:16"], ["long", "Long 16:9"]], pack.format)}</label>
          <label class="field"><span>Style</span>${fieldSelect("autopilot_style", STYLES, pack.style)}</label>
          <label class="field"><span>Region</span>${fieldSelect("autopilot_region", [["IN", "India"], ["US", "United States"], ["GB", "UK"]], pack.region)}</label>
          <label class="field"><span>When ready</span>${fieldSelect("autopilot_publish", [["schedule", "Schedule on YouTube"], ["private", "Upload private now"], ["unlisted", "Upload unlisted now"], ["public", "Upload public now"], ["none", "Only render, do not upload"]], pack.publish)}</label>
        </div>
        <button class="btn" type="submit">Save schedule</button>
        <p class="notice" style="margin-top:14px">Today ${esc(pack.today)} / ${esc(pack.daily_cap)}. Next slot ${esc(String(pack.next_slot || "").replace("T", " ").slice(0, 16))} IST. YouTube ${pack.youtube ? "connected" : "not connected — videos will still be made"}.</p>
        <p class="toast" id="msg">${pack.busy ? "A video is being made now…" : ""}</p>
      </form>
      <aside class="panel">
        <div class="lbl">Famous right now</div>
        <ul id="trend-list"><li class="empty">Checking feeds…</li></ul>
      </aside>
    </div>
    <h2 class="section">Queue</h2>
    <div class="grid" id="ap-queue">
      ${(pack.runs || []).map((r) => `
        <a class="card" href="${r.project_id ? "#/p/" + r.project_id : "#/autopilot"}">
          <div class="body">
            <h3>${esc(r.topic || "…")}</h3>
            <div class="meta">
              <span class="status ${esc(r.status)}">${esc(r.status)}</span>
              <span>${esc(r.source || "")}</span>
              <span>${esc(String(r.scheduled_for || "").replace("T", " ").slice(0, 16))}</span>
            </div>
            <p class="toast">${esc(r.message || r.error || "")}</p>
          </div>
        </a>`).join("") || "<p class='empty'>Nothing queued yet. Click Make one now.</p>"}
    </div>
  `;
  $("#ap").onsubmit = async (e) => {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(e.target).entries());
    body.autopilot_interval_hours = Number(body.autopilot_interval_hours);
    body.autopilot_daily_cap = Number(body.autopilot_daily_cap);
    body.autopilot_enabled = on;
    try {
      await api("/api/autopilot", { method: "PUT", body });
      $("#msg").textContent = "Schedule saved.";
    } catch (err) {
      $("#msg").textContent = err.message;
      $("#msg").classList.add("err");
    }
  };
  $("#toggle").onclick = async () => {
    try {
      await api("/api/autopilot", { method: "PUT", body: { autopilot_enabled: !on } });
      renderAutopilot();
    } catch (err) {
      $("#msg").textContent = err.message;
    }
  };
  $("#now").onclick = async () => {
    $("#msg").textContent = "Picking a famous topic and starting a cut…";
    try {
      await api("/api/autopilot/run-now", { method: "POST" });
      $("#msg").textContent = "Started. Refreshing the queue…";
      setTimeout(renderAutopilot, 2000);
    } catch (err) {
      $("#msg").textContent = err.message;
      $("#msg").classList.add("err");
    }
  };
  try {
    const t = await api("/api/trends");
    const items = t.trends || [];
    $("#trend-list").innerHTML = items.slice(0, 10).map((item) =>
      `<li><strong>${esc(item.title)}</strong> <span class="meta">${esc(item.source || "")}</span></li>`
    ).join("") || "<li class='empty'>No feed yet. Check the network.</li>";
  } catch {
    $("#trend-list").innerHTML = "<li class='empty'>Could not load trends. You can still click Make one now.</li>";
  }
}

async function renderChannel() {
  yt = await api("/api/youtube/status");
  app.innerHTML = `
    <div class="kicker">Distribution</div>
    <div class="toprow"><h1>Channel</h1></div>
    <div class="panel" style="max-width:680px">
      ${yt.connected && yt.channel ? `
        <p>Signed in as <strong>${esc(yt.channel.title)}</strong></p>
        <div class="meta"><span>${esc(yt.channel.subscribers || "hidden")} subscribers</span><span>${esc(yt.channel.videos || "0")} videos</span></div>
        <button class="btn" id="disc">Disconnect</button>
      ` : `
        <p>Connect a Google Cloud OAuth client with the YouTube Data API v3 enabled. Add the client ID and secret in Settings, then set Public base URL to this studio's URL (including the preview host).</p>
        <p class="notice">Authorized redirect URI must be exactly: <code>YOUR_BASE_URL/api/youtube/callback</code></p>
        <div class="row" style="margin-top:14px">
          <button class="btn primary" id="connect">Connect YouTube</button>
        </div>
      `}
      <p class="toast" id="msg"></p>
    </div>
  `;
  const c = $("#connect");
  if (c) c.onclick = async () => {
    try {
      const { url } = await api("/api/youtube/auth-url");
      window.open(url, "_blank", "noopener");
      $("#msg").textContent = "Finish Google sign-in in the new tab, then refresh this page.";
    } catch (err) { $("#msg").textContent = err.message; $("#msg").classList.add("err"); }
  };
  const d = $("#disc");
  if (d) d.onclick = async () => { await api("/api/youtube/disconnect", { method: "POST" }); renderChannel(); };
}

async function renderSettings() {
  settings = await api("/api/settings");
  const val = (k) => settings[k] || "";
  app.innerHTML = `
    <div class="kicker">Booth</div>
    <div class="toprow"><h1>Settings</h1></div>
    <form class="panel" id="set" style="max-width:720px">
      <label class="field"><span>Channel name</span><input name="channel_name" value="${esc(val("channel_name"))}" /></label>
      <div class="form-grid">
        <label class="field"><span>Default format</span>${fieldSelect("default_format", [["long", "Long"], ["short", "Short"]], val("default_format"))}</label>
        <label class="field"><span>Default style</span>${fieldSelect("default_style", STYLES, val("default_style"))}</label>
        <label class="field"><span>Default voice</span>${fieldSelect("default_voice", voices.map((v) => [v.id, v.label]), val("default_voice"))}</label>
        <label class="field"><span>Default privacy</span>${fieldSelect("default_privacy", [["private", "Private"], ["unlisted", "Unlisted"], ["public", "Public"]], val("default_privacy"))}</label>
      </div>
      <h2 class="section">Groq key (gsk_) — writing + optional voice</h2>
      <div class="notice">
        ${settings.has_groq ? "Groq is connected." : "From console.groq.com. Starts with gsk_."}
        <ul>
          ${(settings.groq_does || ["Writes the script fast", "Plans a picture prompt per scene", "Optional PlayAI voice"]).map((item) => `<li>${esc(item)}</li>`).join("")}
        </ul>
        Groq cannot generate pictures.
      </div>
      <label class="field"><span>Groq API key</span><input name="groq_api_key" type="password" value="${esc(val("groq_api_key"))}" placeholder="gsk_…" /></label>
      <h2 class="section">WaveSpeed key (wsk_live_) — pictures</h2>
      <div class="notice">
        ${settings.has_wavespeed ? "WaveSpeed is connected." : "From wavespeed.ai. Starts with wsk_live_."}
        <ul>
          ${(settings.wavespeed_does || ["Paints scene stills", "Paints the thumbnail"]).map((item) => `<li>${esc(item)}</li>`).join("")}
        </ul>
      </div>
      <label class="field"><span>WaveSpeed API key</span><input name="wavespeed_api_key" type="password" value="${esc(val("wavespeed_api_key"))}" placeholder="wsk_live_…" /></label>
      <h2 class="section">Gemini key — backup pictures</h2>
      <div class="notice">
        ${settings.has_gemini ? "Gemini is connected." : "From Google AI Studio. AIza or AQ. keys."}
        <ul>
          ${(settings.gemini_does || ["Paints scene stills", "Thumbnail photo", "Backup writer"]).map((item) => `<li>${esc(item)}</li>`).join("")}
        </ul>
      </div>
      <label class="field"><span>Gemini API key</span><input name="gemini_api_key" type="password" value="${esc(val("gemini_api_key"))}" placeholder="AQ.… or AIza…" /></label>
      <label class="field"><span>OpenAI API key (optional)</span><input name="openai_api_key" type="password" value="${esc(val("openai_api_key"))}" placeholder="sk-…" /></label>
      <label class="field"><span>Anthropic API key (optional)</span><input name="anthropic_api_key" type="password" value="${esc(val("anthropic_api_key"))}" /></label>
      <h2 class="section">YouTube OAuth</h2>
      <label class="field"><span>Public base URL</span><input name="public_base_url" value="${esc(val("public_base_url"))}" placeholder="https://your-host" /></label>
      <label class="field"><span>Google client ID</span><input name="google_client_id" value="${esc(val("google_client_id"))}" /></label>
      <label class="field"><span>Google client secret</span><input name="google_client_secret" type="password" value="${esc(val("google_client_secret"))}" /></label>
      <button class="btn primary" type="submit">Save settings</button>
      <p class="toast" id="msg"></p>
    </form>
  `;
  $("#set").onsubmit = async (e) => {
    e.preventDefault();
    const body = Object.fromEntries(new FormData(e.target).entries());
    settings = await api("/api/settings", { method: "PUT", body });
    $("#msg").textContent = "Saved.";
  };
}

window.addEventListener("hashchange", render);
boot();
