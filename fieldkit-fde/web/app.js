"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const state = { projects: [], track: "enterprise", query: "", selected: null, detail: null, mode: "loading", busy: false, request: 0 };
  const tracks = { enterprise: "Enterprise AI", operations: "Operational systems", reliability: "Deployment reliability" };
  const tabs = Array.from(document.querySelectorAll("[data-track]"));
  const element = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
  };
  const pretty = (value) => JSON.stringify(value, null, 2);
  const titleCase = (value) => String(value).replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
  const displayValue = (value) => {
    if (value === null || value === undefined) return "—";
    if (typeof value === "number") return Number.isInteger(value) ? value.toLocaleString("en-US") : String(Number(value.toFixed(5)));
    if (typeof value === "object") return JSON.stringify(value);
    return String(value);
  };

  async function requestJSON(url, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), options.method === "POST" ? 30000 : 7000);
    try {
      const response = await fetch(url, { ...options, signal: controller.signal, headers: { Accept: "application/json", ...options.headers } });
      const contentType = response.headers.get("content-type") || "";
      if (!contentType.includes("application/json")) throw new Error(response.ok ? "The server returned an unexpected response." : `Request failed (${response.status}).`);
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.error === "string" ? data.error : typeof data.message === "string" ? data.message : `Request failed (${response.status}).`);
      return data;
    } catch (error) {
      if (error.name === "AbortError") throw new Error("The request timed out. The server may be unavailable; try again.");
      throw error;
    } finally {
      clearTimeout(timeout);
    }
  }

  function setMode(mode) {
    state.mode = mode;
    $("mode-pill").className = `mode-pill ${mode === "live" ? "" : mode}`;
    $("mode-label").textContent = mode === "live" ? "Local execution connected" : mode === "static" ? "Recorded fixture replay" : "Collection unavailable";
    if (mode === "static") {
      $("mode-banner").textContent = "Recorded fixture replay — run locally to execute edited inputs. These are outputs captured from the included synthetic samples; this page does not run the Python engines.";
      $("mode-banner").hidden = false;
    }
  }

  function filteredProjects() {
    const query = state.query.trim().toLowerCase();
    return state.projects.filter((project) => query ? [project.name, project.tagline, project.description, project.customer, ...(project.skills || [])].join(" ").toLowerCase().includes(query) : project.track === state.track);
  }

  function renderCards() {
    const list = $("project-list");
    list.replaceChildren();
    const projects = filteredProjects();
    list.setAttribute("aria-labelledby", `track-${state.track}`);
    $("search-context").hidden = !state.query;
    $("search-context").textContent = `${projects.length} result${projects.length === 1 ? "" : "s"} across all three tracks. Clear the search to return to ${tracks[state.track]}.`;
    if (!projects.length) {
      list.append(element("p", "empty-state", "No projects match this search. Try a workflow, skill, or project name."));
      return;
    }
    projects.forEach((project) => {
      const card = element("button", "project-card");
      card.type = "button";
      card.setAttribute("aria-pressed", String(state.selected === project.id));
      card.setAttribute("aria-controls", "project-detail");
      card.setAttribute("aria-label", `${project.name}: ${project.tagline}${project.flagship ? ". Flagship project" : ""}`);
      const top = element("div", "card-topline");
      top.append(element("span", "card-index", `KIT ${String(state.projects.indexOf(project) + 1).padStart(2, "0")}`));
      if (project.flagship) top.append(element("span", "card-flagship", "✳ FLAGSHIP"));
      const title = element("div", "card-title-row");
      title.append(element("h3", null, project.name), element("span", "card-arrow", "↗"));
      title.lastChild.setAttribute("aria-hidden", "true");
      const skills = element("div", "card-skills");
      (project.skills || []).slice(0, 3).forEach((skill) => skills.append(element("span", null, skill)));
      card.append(top, title, element("p", "card-tagline", project.tagline), skills);
      card.addEventListener("click", () => selectProject(project.id));
      list.append(card);
    });
  }

  function clearResult() {
    $("result-panel").hidden = true;
    $("run-error").hidden = true;
    $("run-status").textContent = state.mode === "static" ? "Captured sample evidence available." : "Ready to run.";
  }

  function fillDetail(data) {
    const project = data.project;
    state.detail = data;
    $("detail-placeholder").hidden = true;
    $("detail-content").hidden = false;
    $("detail-track").textContent = `${tracks[project.track] || project.track} / ${project.id}`;
    $("detail-badge").hidden = !project.flagship;
    $("detail-title").textContent = project.name;
    $("detail-description").textContent = project.description;
    $("detail-customer").textContent = project.customer;
    $("detail-skills").replaceChildren(...(project.skills || []).map((skill) => element("span", null, skill)));
    $("project-note-link").href = `https://github.com/aayush0124/Automation/tree/portfolio/fieldkit-fde/fieldkit-fde/docs/projects/${encodeURIComponent(project.id)}.md`;
    $("payload-editor").value = pretty(data.sample);
    $("payload-editor").readOnly = state.mode === "static";
    $("reset-sample").disabled = state.mode === "static";
    $("input-mode").textContent = state.mode === "static" ? "READ-ONLY CAPTURED FIXTURE" : "EDITABLE JSON FIXTURE";
    $("input-help").textContent = state.mode === "static" ? "Read-only recorded fixture. Run the lab locally to edit inputs and compute new outputs; the source and setup instructions are linked below." : "Change the fixture to test another outcome. This workflow uses synthetic data and has no external side effects.";
    $("run-workflow").className = `run-button${state.mode === "static" ? " static-button" : ""}`;
    $("run-workflow").replaceChildren(document.createTextNode(state.mode === "static" ? "View captured evidence " : "Run workflow "), element("span", null, "↗"));
    $("run-workflow").lastChild.setAttribute("aria-hidden", "true");
    $("run-workflow").disabled = false;
    clearResult();
    if (state.mode === "static" && data.result) renderResult({ result: data.result, ...(data.elapsed_ms !== undefined ? { elapsed_ms: data.elapsed_ms } : {}), ...(data.input_sha256 ? { input_sha256: data.input_sha256 } : {}) }, true);
  }

  async function selectProject(id) {
    const token = ++state.request;
    state.selected = id;
    state.detail = null;
    state.busy = false;
    renderCards();
    $("project-detail").setAttribute("aria-busy", "true");
    $("run-workflow").disabled = true;
    $("detail-content").hidden = true;
    $("detail-placeholder").hidden = false;
    $("detail-placeholder").replaceChildren(element("span", "placeholder-mark", "↗"), element("h3", null, "Opening field kit…"), element("p", null, "Loading the scenario and project brief."));
    try {
      const url = state.mode === "static" ? `./examples/${encodeURIComponent(id)}.json` : `./api/projects/${encodeURIComponent(id)}`;
      const data = await requestJSON(url);
      if (token !== state.request) return;
      if (!data.project || !data.sample || typeof data.sample !== "object" || Array.isArray(data.sample)) throw new Error("This project has an invalid fixture format.");
      fillDetail(data);
    } catch (error) {
      if (token !== state.request) return;
      $("detail-placeholder").replaceChildren(element("h3", null, "This kit could not be opened"), element("p", null, error.message));
      const retry = element("button", "run-button", "Retry project");
      retry.type = "button";
      retry.addEventListener("click", () => selectProject(id));
      $("detail-placeholder").append(retry);
    } finally {
      if (token === state.request) $("project-detail").setAttribute("aria-busy", "false");
    }
  }

  function renderResult(envelope, recorded = false) {
    const result = envelope.result;
    if (!result || typeof result !== "object") throw new Error("The workflow returned an invalid result.");
    $("result-panel").hidden = false;
    $("result-mode").textContent = recorded ? "RECORDED FIXTURE OUTPUT" : "COMPUTED OUTPUT";
    $("result-summary").textContent = result.summary || "Workflow complete. Inspect the evidence below.";
    $("result-metrics").replaceChildren();
    if (result.metrics && typeof result.metrics === "object") {
      Object.entries(result.metrics).slice(0, 12).forEach(([key, value]) => {
        const metric = element("div", "metric");
        const formatted = displayValue(value);
        metric.append(element("dt", null, titleCase(key)), element("dd", formatted.length > 12 ? "long-value" : null, formatted));
        $("result-metrics").append(metric);
      });
    }
    const warnings = Array.isArray(result.warnings) ? result.warnings : [];
    $("result-warnings").hidden = !warnings.length;
    $("warnings-list").replaceChildren(...warnings.map((warning) => element("li", null, displayValue(warning))));
    const records = Array.isArray(result.records) ? result.records : [];
    $("record-section").hidden = !records.length;
    $("record-count").textContent = `${records.length} record${records.length === 1 ? "" : "s"}`;
    $("records-table").replaceChildren();
    if (records.length) {
      const visible = records.slice(0, 100).map((record) => record && typeof record === "object" && !Array.isArray(record) ? record : { value: record });
      const allKeys = [...new Set(visible.flatMap(Object.keys))];
      const keys = allKeys.slice(0, 8);
      const table = element("table");
      const head = element("thead");
      const headRow = element("tr");
      keys.forEach((key) => { const th = element("th", null, titleCase(key)); th.scope = "col"; headRow.append(th); });
      head.append(headRow);
      const body = element("tbody");
      visible.forEach((record) => { const tr = element("tr"); keys.forEach((key) => tr.append(element("td", null, displayValue(record[key])))); body.append(tr); });
      table.append(head, body);
      $("records-table").append(table);
      const limited = records.length > 100 || allKeys.length > 8;
      $("record-limit").hidden = !limited;
      $("record-limit").textContent = `Table shows up to 100 records and 8 fields. The full evidence below contains the complete result.`;
    }
    $("full-evidence").textContent = pretty(envelope);
    $("run-metadata").replaceChildren();
    const metadata = recorded ? [["Evidence type", "Recorded sample run"]] : [["Evidence type", "Executed locally"], ["Run ID", envelope.run_id || "Not supplied"]];
    if (envelope.elapsed_ms !== undefined) metadata.push([recorded ? "Recorded elapsed time" : "Engine elapsed time", `${displayValue(envelope.elapsed_ms)} ms`]);
    if (envelope.input_sha256) metadata.push(["Input SHA-256", envelope.input_sha256]);
    metadata.forEach(([key, value]) => { const row = element("div", key.includes("SHA") ? "hash" : null); row.append(element("dt", null, key), element("dd", null, value)); $("run-metadata").append(row); });
  }

  async function runWorkflow() {
    if (state.busy || !state.detail) return;
    if (state.mode === "static") {
      if (!state.detail.result) { $("run-error").textContent = "No captured evidence is available for this fixture. Run the lab locally to compute it."; $("run-error").hidden = false; return; }
      renderResult({ result: state.detail.result, ...(state.detail.elapsed_ms !== undefined ? { elapsed_ms: state.detail.elapsed_ms } : {}), ...(state.detail.input_sha256 ? { input_sha256: state.detail.input_sha256 } : {}) }, true);
      $("run-status").textContent = "Showing recorded evidence. No workflow was executed.";
      $("result-panel").scrollIntoView({ behavior: "smooth", block: "nearest" });
      return;
    }
    $("run-error").hidden = true;
    let payload;
    try {
      payload = JSON.parse($("payload-editor").value);
      if (!payload || typeof payload !== "object" || Array.isArray(payload)) throw new Error("Use a JSON object as the workflow input.");
    } catch (error) {
      $("run-error").textContent = `Check the input: ${error.message}`;
      $("run-error").hidden = false;
      $("payload-editor").focus();
      return;
    }
    state.busy = true;
    const projectId = state.selected;
    const token = state.request;
    $("run-workflow").disabled = true;
    $("payload-editor").readOnly = true;
    $("reset-sample").disabled = true;
    $("run-status").textContent = "Executing workflow…";
    $("result-panel").hidden = true;
    try {
      const envelope = await requestJSON(`./api/run/${encodeURIComponent(projectId)}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      if (token !== state.request) return;
      renderResult(envelope);
      $("run-status").textContent = "Complete. Evidence captured below.";
    } catch (error) {
      if (token !== state.request) return;
      $("run-error").textContent = error.message;
      $("run-error").hidden = false;
      $("run-status").textContent = "The workflow did not complete. Review the error.";
    } finally {
      if (token === state.request) {
        state.busy = false;
        $("run-workflow").disabled = false;
        $("payload-editor").readOnly = false;
        $("reset-sample").disabled = false;
      }
    }
  }

  function switchTrack(track) {
    state.track = track;
    state.query = "";
    $("project-search").value = "";
    tabs.forEach((tab) => { const active = tab.dataset.track === track; tab.setAttribute("aria-selected", String(active)); tab.tabIndex = active ? 0 : -1; });
    renderCards();
    const available = filteredProjects();
    if (available.length && !available.some((project) => project.id === state.selected)) selectProject(available[0].id);
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => switchTrack(tab.dataset.track));
    tab.addEventListener("keydown", (event) => {
      let next;
      if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
      if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
      if (event.key === "Home") next = 0;
      if (event.key === "End") next = tabs.length - 1;
      if (next !== undefined) { event.preventDefault(); tabs[next].focus(); switchTrack(tabs[next].dataset.track); }
    });
  });
  $("project-search").addEventListener("input", (event) => { state.query = event.target.value; renderCards(); });
  $("reset-sample").addEventListener("click", () => { if (state.detail && state.mode === "live") { $("payload-editor").value = pretty(state.detail.sample); clearResult(); } });
  $("run-workflow").addEventListener("click", runWorkflow);
  $("payload-editor").addEventListener("input", () => { if (!state.busy) { $("run-status").textContent = "Input changed. Run again to recompute."; $("result-panel").hidden = true; } });
  document.addEventListener("keydown", (event) => {
    if (event.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName) && !event.ctrlKey && !event.metaKey && !event.altKey) { event.preventDefault(); $("project-search").focus(); }
  });

  async function initialize() {
    let catalog;
    try {
      catalog = await requestJSON("./api/projects");
      if (!Array.isArray(catalog.projects)) throw new Error("Invalid live catalog.");
      setMode("live");
    } catch (_) {
      try {
        catalog = await requestJSON("./catalog.json");
        if (!Array.isArray(catalog.projects)) throw new Error("Invalid recorded catalog.");
        setMode("static");
      } catch (error) {
        setMode("error");
        $("project-list").replaceChildren(element("p", "empty-state", `The project catalog is unavailable. Start the local server or check the published fixture files. ${error.message}`));
        return;
      }
    }
    state.projects = catalog.projects.filter((project) => project && typeof project.id === "string" && /^[a-z0-9-]+$/.test(project.id) && tracks[project.track]);
    $("project-count").textContent = String(state.projects.length).padStart(2, "0");
    $("project-search").placeholder = `Search all ${state.projects.length} projects`;
    renderCards();
    const initial = filteredProjects()[0] || state.projects[0];
    if (initial) { if (initial.track !== state.track) switchTrack(initial.track); else selectProject(initial.id); }
  }
  initialize();
})();
