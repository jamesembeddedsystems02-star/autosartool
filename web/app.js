"use strict";

// --------------------------------------------------------------------------
// State
// --------------------------------------------------------------------------
const state = {
  project: null,
  selected: null, // { cat: <key>, index: <int> }
};

const PRIMITIVES = ["boolean", "uint8", "uint16", "uint32", "uint64",
  "sint8", "sint16", "sint32", "sint64", "float", "double", "string"];
const FUNCTIONAL_CLUSTERS = ["EM", "SM", "CM", "DM", "PER", "TS", "NM", "CRYPTO", "IAM", "LOG", "UCM"];

// Category descriptors: how each list in the project is presented and created.
const CATEGORIES = [
  {
    key: "service_interfaces", label: "Service Interfaces", singular: "Interface",
    make: () => ({ name: newName("service_interfaces", "Interface"), namespace: "ara", methods: [], events: [], fields: [] }),
  },
  {
    key: "applications", label: "Application Components", singular: "Application",
    make: () => ({ name: newName("applications", "App"), description: "", ports: [] }),
  },
  {
    key: "executables", label: "Executables", singular: "Executable",
    make: () => ({ name: newName("executables", "Exe"), root_component: firstName("applications"), version: "1.0.0" }),
  },
  {
    key: "processes", label: "Processes", singular: "Process",
    make: () => ({ name: newName("processes", "Proc"), executable: firstName("executables"),
      scheduling_policy: "SCHED_FIFO", priority: 50, core_affinity: [], startup_states: ["Running"] }),
  },
  {
    key: "machines", label: "Machines", singular: "Machine",
    make: () => ({ name: newName("machines", "Machine"), machine_states: ["Startup", "Running", "Shutdown"],
      functional_clusters: ["EM", "SM", "CM"] }),
  },
  {
    key: "service_instances", label: "Service Instances", singular: "Instance",
    make: () => ({ name: newName("service_instances", "Instance"), service_interface: firstName("service_interfaces"),
      instance_id: 1, binding: "SOMEIP", role: "PROVIDED", service_id: 4660, udp_port: 30509, tcp_port: null }),
  },
  {
    key: "bsw_modules", label: "BSW / Platform Modules", singular: "Module",
    make: () => ({ name: newName("bsw_modules", "Module"), vendor: "OpenAUTOSAR", description: "", containers: [] }),
  },
];

function catByKey(key) { return CATEGORIES.find((c) => c.key === key); }
function list(key) { return state.project ? state.project[key] || [] : []; }
function firstName(key) { const l = list(key); return l.length ? l[0].name : ""; }
function newName(key, base) {
  const existing = new Set(list(key).map((x) => x.name));
  let i = 1; while (existing.has(base + i)) i++; return base + i;
}

// --------------------------------------------------------------------------
// API
// --------------------------------------------------------------------------
async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body !== undefined) { opts.headers["Content-Type"] = "application/json"; opts.body = JSON.stringify(body); }
  const res = await fetch(path, opts);
  const ctype = res.headers.get("Content-Type") || "";
  return ctype.includes("application/json") ? res.json() : res.text();
}

async function loadProject() { state.project = await api("GET", "/api/project"); renderAll(); }
async function saveProject() {
  const r = await api("PUT", "/api/project", state.project);
  if (r.ok) status("Saved", "ok"); else status("Save failed: " + (r.error || "?"), "err");
}
async function loadExample() { state.project = await api("POST", "/api/example"); state.selected = null; renderAll(); status("Loaded ADAS example", "ok"); }

// --------------------------------------------------------------------------
// Status bar
// --------------------------------------------------------------------------
function status(msg, cls) {
  const el = document.getElementById("status-msg");
  el.textContent = msg; el.className = cls || "";
  if (cls === "ok") setTimeout(() => { if (el.textContent === msg) el.textContent = ""; }, 3000);
}
function renderStatusProject() {
  document.getElementById("status-project").textContent =
    state.project ? `${state.project.name} · ${state.project.package} · ${state.project.autosar_release}` : "No project";
}

// --------------------------------------------------------------------------
// Sidebar
// --------------------------------------------------------------------------
function renderSidebar() {
  const nav = document.getElementById("sidebar");
  nav.innerHTML = "";
  for (const cat of CATEGORIES) {
    const items = list(cat.key);
    const wrap = document.createElement("div");
    wrap.className = "cat";
    const head = document.createElement("div");
    head.className = "cat-head";
    head.innerHTML = `<span>${cat.label} <span class="count">${items.length}</span></span>`;
    const add = document.createElement("button");
    add.className = "cat-add"; add.textContent = "+"; add.title = "Add " + cat.singular;
    add.onclick = (e) => { e.stopPropagation(); addItem(cat.key); };
    head.appendChild(add);
    wrap.appendChild(head);
    items.forEach((item, idx) => {
      const row = document.createElement("div");
      row.className = "item" + (state.selected && state.selected.cat === cat.key && state.selected.index === idx ? " active" : "");
      const label = document.createElement("span");
      label.textContent = item.name || "(unnamed)";
      row.appendChild(label);
      const del = document.createElement("button");
      del.className = "del"; del.textContent = "✕"; del.title = "Delete";
      del.onclick = (e) => { e.stopPropagation(); deleteItem(cat.key, idx); };
      row.appendChild(del);
      row.onclick = () => { state.selected = { cat: cat.key, index: idx }; renderAll(); };
      wrap.appendChild(row);
    });
    nav.appendChild(wrap);
  }
}

function addItem(key) {
  const cat = catByKey(key);
  state.project[key].push(cat.make());
  state.selected = { cat: key, index: state.project[key].length - 1 };
  renderAll();
}
function deleteItem(key, idx) {
  state.project[key].splice(idx, 1);
  if (state.selected && state.selected.cat === key && state.selected.index === idx) state.selected = null;
  renderAll();
}

// --------------------------------------------------------------------------
// Editor dispatch
// --------------------------------------------------------------------------
function renderEditor() {
  const host = document.getElementById("editor");
  if (!state.selected) {
    host.innerHTML = `<div class="empty-state"><h2>Select an element</h2>
      <p>Pick a category on the left, or load the example project to explore a complete ADAS configuration.</p>
      <div class="form" style="text-align:left"></div></div>`;
    renderProjectSettings(host.querySelector(".form"));
    return;
  }
  const { cat, index } = state.selected;
  const item = list(cat)[index];
  if (!item) { state.selected = null; return renderEditor(); }
  host.innerHTML = "";
  const editors = {
    service_interfaces: editInterface, applications: editApplication, executables: editExecutable,
    processes: editProcess, machines: editMachine, service_instances: editInstance, bsw_modules: editModule,
  };
  editors[cat](host, item);
}

// -- small DOM builders ----------------------------------------------------
function h(tag, attrs = {}, children = []) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") el.className = v;
    else if (k === "html") el.innerHTML = v;
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) el.setAttribute(k, v);
  }
  (Array.isArray(children) ? children : [children]).forEach((c) => {
    if (c == null) return;
    el.appendChild(typeof c === "string" ? document.createTextNode(c) : c);
  });
  return el;
}
function header(host, kind, name) {
  host.appendChild(h("div", { class: "kind" }, kind));
  host.appendChild(h("h1", {}, name || "(unnamed)"));
}
function textField(label, value, onchange, opts = {}) {
  const input = h("input", { type: opts.type || "text", value: value == null ? "" : value });
  input.addEventListener("input", () => onchange(input.value));
  return h("div", { class: "field" }, [h("label", {}, label), input]);
}
function numField(label, value, onchange) {
  const input = h("input", { type: "number", value: value == null ? "" : value });
  input.addEventListener("input", () => onchange(input.value === "" ? null : Number(input.value)));
  return h("div", { class: "field" }, [h("label", {}, label), input]);
}
function selectField(label, value, options, onchange) {
  const sel = h("select", {});
  options.forEach((o) => {
    const opt = h("option", { value: o }, o);
    if (o === value) opt.selected = true;
    sel.appendChild(opt);
  });
  sel.addEventListener("change", () => onchange(sel.value));
  return h("div", { class: "field" }, [h("label", {}, label), sel]);
}
function checkField(label, value, onchange) {
  const input = h("input", { type: "checkbox" });
  input.checked = !!value;
  input.addEventListener("change", () => onchange(input.checked));
  return h("div", { class: "field check" }, [input, h("label", { style: "margin:0" }, label)]);
}
function subhead(title, addLabel, onadd) {
  const btn = onadd ? h("button", { class: "btn", onclick: onadd }, "+ " + addLabel) : null;
  return h("div", { class: "subhead" }, [h("h3", {}, title), btn]);
}
function reflectSidebar() { renderSidebar(); renderStatusProject(); }

// --------------------------------------------------------------------------
// Project settings (shown on empty selection)
// --------------------------------------------------------------------------
function renderProjectSettings(host) {
  if (!state.project) return;
  host.appendChild(h("h3", { style: "margin-top:0" }, "Project Settings"));
  host.appendChild(textField("Project name", state.project.name, (v) => { state.project.name = v; renderStatusProject(); }));
  host.appendChild(textField("Package short-name", state.project.package, (v) => { state.project.package = v; renderStatusProject(); }));
  host.appendChild(selectField("AUTOSAR release", state.project.autosar_release,
    ["R20-11", "R21-11", "R22-11", "R23-11"], (v) => { state.project.autosar_release = v; renderStatusProject(); }));
}

// --------------------------------------------------------------------------
// Service Interface editor
// --------------------------------------------------------------------------
function editInterface(host, si) {
  header(host, "Service Interface", si.name);
  const form = h("div", { class: "form" });
  form.appendChild(textField("Short-name", si.name, (v) => { si.name = v; reflectSidebar(); }));
  form.appendChild(textField("Namespace", si.namespace, (v) => { si.namespace = v; }));

  // Methods
  form.appendChild(subhead("Methods", "Method", () => { si.methods.push({ name: "Method" + (si.methods.length + 1), fire_and_forget: false, arguments: [] }); renderEditor(); }));
  si.methods.forEach((m, mi) => {
    const box = h("div", { style: "border:1px solid var(--border);border-radius:6px;padding:10px;margin-bottom:10px" });
    box.appendChild(h("div", { class: "row" }, [
      textField("Name", m.name, (v) => { m.name = v; }),
      checkFieldInline("Fire & forget", m.fire_and_forget, (v) => { m.fire_and_forget = v; }),
      delBtn(() => { si.methods.splice(mi, 1); renderEditor(); }),
    ]));
    box.appendChild(argTable(m));
    form.appendChild(box);
  });

  // Events
  form.appendChild(subhead("Events", "Event", () => { si.events.push({ name: "Event" + (si.events.length + 1), type: "uint32" }); renderEditor(); }));
  form.appendChild(simpleTable(si.events, [
    { label: "Name", key: "name", type: "text" },
    { label: "Type", key: "type", type: "select", options: () => typeOptions() },
  ], () => renderEditor()));

  // Fields
  form.appendChild(subhead("Fields", "Field", () => { si.fields.push({ name: "Field" + (si.fields.length + 1), type: "uint8", has_getter: true, has_setter: true, has_notifier: true }); renderEditor(); }));
  form.appendChild(simpleTable(si.fields, [
    { label: "Name", key: "name", type: "text" },
    { label: "Type", key: "type", type: "select", options: () => typeOptions() },
    { label: "Get", key: "has_getter", type: "check" },
    { label: "Set", key: "has_setter", type: "check" },
    { label: "Notify", key: "has_notifier", type: "check" },
  ], () => renderEditor()));

  host.appendChild(form);
}

function typeOptions() {
  return PRIMITIVES.concat(list("service_interfaces").map((s) => s.name));
}
function checkFieldInline(label, value, onchange) {
  const input = h("input", { type: "checkbox" });
  input.checked = !!value;
  input.addEventListener("change", () => onchange(input.checked));
  return h("div", { class: "field", style: "flex:0 0 auto" }, [h("label", {}, label), h("div", { class: "check" }, [input])]);
}
function delBtn(onclick) {
  return h("div", { class: "field", style: "flex:0 0 auto;display:flex;align-items:flex-end" },
    [h("button", { class: "btn", onclick, title: "Delete" }, "Delete")]);
}
function argTable(m) {
  const table = h("table", { class: "grid" });
  table.appendChild(h("thead", {}, h("tr", {}, [
    th("Argument"), th("Type"), th("Direction"), th(""),
  ])));
  const tbody = h("tbody");
  m.arguments.forEach((a, ai) => {
    tbody.appendChild(h("tr", {}, [
      td(inputCell(a.name, (v) => a.name = v)),
      td(selectCell(a.type, typeOptions(), (v) => a.type = v)),
      td(selectCell(a.direction, ["IN", "OUT", "INOUT"], (v) => a.direction = v)),
      td(h("button", { class: "rowdel", onclick: () => { m.arguments.splice(ai, 1); renderEditor(); } }, "✕")),
    ]));
  });
  table.appendChild(tbody);
  const add = h("button", { class: "btn add-row", onclick: () => { m.arguments.push({ name: "arg" + (m.arguments.length + 1), type: "uint32", direction: "IN" }); renderEditor(); } }, "+ Argument");
  return h("div", {}, [table, add]);
}

// A generic editable table for arrays of flat objects.
function simpleTable(arr, cols, refresh) {
  const table = h("table", { class: "grid" });
  table.appendChild(h("thead", {}, h("tr", {}, cols.map((c) => th(c.label)).concat(th("")))));
  const tbody = h("tbody");
  arr.forEach((obj, i) => {
    const cells = cols.map((c) => {
      if (c.type === "text") return td(inputCell(obj[c.key], (v) => obj[c.key] = v, refresh));
      if (c.type === "number") return td(inputCell(obj[c.key], (v) => obj[c.key] = v === "" ? null : Number(v), null, "number"));
      if (c.type === "select") return td(selectCell(obj[c.key], c.options(), (v) => obj[c.key] = v));
      if (c.type === "check") return td(checkCell(obj[c.key], (v) => obj[c.key] = v));
      return td("");
    });
    cells.push(td(h("button", { class: "rowdel", onclick: () => { arr.splice(i, 1); refresh(); } }, "✕")));
    tbody.appendChild(h("tr", {}, cells));
  });
  table.appendChild(tbody);
  return table;
}
function th(t) { return h("th", {}, t); }
function td(child) { return h("td", {}, child); }
function inputCell(value, onchange, refresh, type) {
  const input = h("input", { type: type || "text", value: value == null ? "" : value });
  input.addEventListener("input", () => { onchange(input.value); if (refresh) reflectSidebar(); });
  return input;
}
function selectCell(value, options, onchange) {
  const sel = h("select", {});
  options.forEach((o) => { const opt = h("option", { value: o }, o); if (o === value) opt.selected = true; sel.appendChild(opt); });
  sel.addEventListener("change", () => onchange(sel.value));
  return sel;
}
function checkCell(value, onchange) {
  const input = h("input", { type: "checkbox" });
  input.checked = !!value;
  input.addEventListener("change", () => onchange(input.checked));
  return input;
}

// --------------------------------------------------------------------------
// Application editor
// --------------------------------------------------------------------------
function editApplication(host, app) {
  header(host, "Adaptive Application SW Component", app.name);
  const form = h("div", { class: "form" });
  form.appendChild(textField("Short-name", app.name, (v) => { app.name = v; reflectSidebar(); }));
  form.appendChild(textField("Description", app.description, (v) => { app.description = v; }));
  form.appendChild(subhead("Ports", "Port", () => {
    app.ports.push({ name: "Port" + (app.ports.length + 1), direction: "PROVIDED", interface: firstName("service_interfaces") });
    renderEditor();
  }));
  form.appendChild(simpleTable(app.ports, [
    { label: "Name", key: "name", type: "text" },
    { label: "Direction", key: "direction", type: "select", options: () => ["PROVIDED", "REQUIRED"] },
    { label: "Interface", key: "interface", type: "select", options: () => list("service_interfaces").map((s) => s.name) },
  ], () => renderEditor()));
  host.appendChild(form);
}

// --------------------------------------------------------------------------
// Executable / Process / Machine / Instance editors
// --------------------------------------------------------------------------
function editExecutable(host, ex) {
  header(host, "Executable", ex.name);
  const form = h("div", { class: "form" });
  form.appendChild(textField("Short-name", ex.name, (v) => { ex.name = v; reflectSidebar(); }));
  form.appendChild(selectField("Root component", ex.root_component, list("applications").map((a) => a.name), (v) => ex.root_component = v));
  form.appendChild(textField("Version", ex.version, (v) => ex.version = v));
  host.appendChild(form);
}

function editProcess(host, proc) {
  header(host, "Process", proc.name);
  const form = h("div", { class: "form" });
  form.appendChild(textField("Short-name", proc.name, (v) => { proc.name = v; reflectSidebar(); }));
  form.appendChild(selectField("Executable", proc.executable, list("executables").map((e) => e.name), (v) => proc.executable = v));
  form.appendChild(h("div", { class: "row" }, [
    selectField("Scheduling policy", proc.scheduling_policy, ["SCHED_FIFO", "SCHED_RR", "SCHED_OTHER"], (v) => proc.scheduling_policy = v),
    numField("Priority", proc.priority, (v) => proc.priority = v == null ? 0 : v),
  ]));
  form.appendChild(textField("Core affinity (comma-separated)", (proc.core_affinity || []).join(","),
    (v) => proc.core_affinity = v.split(",").map((s) => s.trim()).filter((s) => s !== "").map(Number)));
  form.appendChild(textField("Startup states (comma-separated)", (proc.startup_states || []).join(","),
    (v) => proc.startup_states = v.split(",").map((s) => s.trim()).filter((s) => s !== "")));
  host.appendChild(form);
}

function editMachine(host, m) {
  header(host, "Machine (ECU)", m.name);
  const form = h("div", { class: "form" });
  form.appendChild(textField("Short-name", m.name, (v) => { m.name = v; reflectSidebar(); }));
  form.appendChild(textField("Machine states (comma-separated)", (m.machine_states || []).join(","),
    (v) => m.machine_states = v.split(",").map((s) => s.trim()).filter((s) => s !== "")));
  form.appendChild(h("div", { class: "field" }, [h("label", {}, "Functional clusters")]));
  const grid = h("div", { style: "display:grid;grid-template-columns:repeat(4,1fr);gap:6px" });
  FUNCTIONAL_CLUSTERS.forEach((fc) => {
    const input = h("input", { type: "checkbox" });
    input.checked = (m.functional_clusters || []).includes(fc);
    input.addEventListener("change", () => {
      const set = new Set(m.functional_clusters);
      if (input.checked) set.add(fc); else set.delete(fc);
      m.functional_clusters = FUNCTIONAL_CLUSTERS.filter((x) => set.has(x));
    });
    grid.appendChild(h("label", { class: "check" }, [input, fc]));
  });
  form.appendChild(grid);
  host.appendChild(form);
}

function editInstance(host, si) {
  header(host, "Service Instance", si.name);
  const form = h("div", { class: "form" });
  form.appendChild(textField("Short-name", si.name, (v) => { si.name = v; reflectSidebar(); }));
  form.appendChild(selectField("Service interface", si.service_interface, list("service_interfaces").map((s) => s.name), (v) => si.service_interface = v));
  form.appendChild(h("div", { class: "row" }, [
    selectField("Binding", si.binding, ["SOMEIP", "DDS", "IPC"], (v) => { si.binding = v; renderEditor(); }),
    selectField("Role", si.role, ["PROVIDED", "REQUIRED"], (v) => si.role = v),
    numField("Instance ID", si.instance_id, (v) => si.instance_id = v == null ? 0 : v),
  ]));
  if (si.binding === "SOMEIP") {
    form.appendChild(h("div", { class: "row" }, [
      numField("Service ID", si.service_id, (v) => si.service_id = v),
      numField("UDP port", si.udp_port, (v) => si.udp_port = v),
      numField("TCP port", si.tcp_port, (v) => si.tcp_port = v),
    ]));
  }
  host.appendChild(form);
}

// --------------------------------------------------------------------------
// BSW module editor (containers + parameters, recursive)
// --------------------------------------------------------------------------
function editModule(host, mod) {
  header(host, "BSW / Platform Module", mod.name);
  const form = h("div", { class: "form" });
  form.appendChild(h("div", { class: "row" }, [
    textField("Short-name", mod.name, (v) => { mod.name = v; reflectSidebar(); }),
    textField("Vendor", mod.vendor, (v) => mod.vendor = v),
  ]));
  form.appendChild(textField("Description", mod.description, (v) => mod.description = v));

  // Template loader
  const tmplBtn = h("button", { class: "btn", onclick: async () => {
    const tmpl = await api("POST", "/api/bsw-template", { name: mod.name });
    if (tmpl && tmpl.containers) { mod.containers = tmpl.containers; mod.vendor = tmpl.vendor || mod.vendor; mod.description = tmpl.description || mod.description; renderEditor(); status("Loaded template for " + mod.name, "ok"); }
  } }, "Load template by name");
  form.appendChild(h("div", { class: "field" }, [tmplBtn]));

  form.appendChild(subhead("Containers", "Container", () => { mod.containers.push({ name: "Container" + (mod.containers.length + 1), parameters: [], sub_containers: [] }); renderEditor(); }));
  mod.containers.forEach((c, ci) => form.appendChild(renderContainer(c, () => { mod.containers.splice(ci, 1); renderEditor(); })));
  host.appendChild(form);
}

function renderContainer(container, onDelete) {
  const box = h("div", { style: "border:1px solid var(--border);border-radius:6px;padding:12px;margin-bottom:12px" });
  box.appendChild(h("div", { class: "row" }, [
    textField("Container name", container.name, (v) => container.name = v),
    delBtn(onDelete),
  ]));
  // Parameters
  box.appendChild(subhead("Parameters", "Parameter", () => { container.parameters.push({ name: "Param" + (container.parameters.length + 1), type: "INTEGER", value: 0 }); renderEditor(); }));
  box.appendChild(simpleTable(container.parameters, [
    { label: "Name", key: "name", type: "text" },
    { label: "Type", key: "type", type: "select", options: () => ["INTEGER", "FLOAT", "BOOLEAN", "STRING", "ENUM", "REFERENCE"] },
    { label: "Value", key: "value", type: "text" },
  ], () => renderEditor()));
  // Sub-containers (recursive)
  box.appendChild(subhead("Sub-containers", "Sub-container", () => { container.sub_containers.push({ name: "Sub" + (container.sub_containers.length + 1), parameters: [], sub_containers: [] }); renderEditor(); }));
  container.sub_containers.forEach((sc, si) => box.appendChild(renderContainer(sc, () => { container.sub_containers.splice(si, 1); renderEditor(); })));
  return box;
}

// --------------------------------------------------------------------------
// Output panel: validation / generation / arxml
// --------------------------------------------------------------------------
function openOutput(title) {
  document.getElementById("output-title").textContent = title;
  document.getElementById("output").hidden = false;
  return document.getElementById("output-body");
}
function closeOutput() { document.getElementById("output").hidden = true; }

async function runValidate() {
  await saveProject();
  const report = await api("POST", "/api/validate");
  const body = openOutput("Validation");
  body.innerHTML = "";
  const summary = h("div", { style: "margin-bottom:12px" },
    `${report.error_count} error(s), ${report.warning_count} warning(s) — ${report.ok ? "OK" : "FAILED"}`);
  body.appendChild(summary);
  if (report.findings.length === 0) body.appendChild(h("div", {}, "No findings. 🎉"));
  report.findings.forEach((f) => {
    body.appendChild(h("div", { class: "finding " + f.severity }, [
      h("div", {}, [h("span", { class: "rule" }, f.rule + " "), h("span", { class: "el" }, f.element)]),
      h("div", {}, f.message),
    ]));
  });
  status(report.ok ? "Validation passed" : "Validation failed", report.ok ? "ok" : "err");
}

async function runGenerate() {
  await saveProject();
  const res = await api("POST", "/api/generate");
  const body = openOutput("Code Generation");
  body.innerHTML = "";
  if (!res.ok) {
    body.appendChild(h("div", { style: "color:var(--red);margin-bottom:10px" }, "Validation failed — fix errors before generating:"));
    (res.report.findings || []).filter((f) => f.severity === "ERROR").forEach((f) => {
      body.appendChild(h("div", { class: "finding ERROR" }, [h("div", { class: "rule" }, f.rule + " " + f.element), h("div", {}, f.message)]));
    });
    status("Generation blocked by validation", "err");
    return;
  }
  const files = res.files;
  const names = Object.keys(files).sort();
  const tabs = h("div", { style: "margin-bottom:10px" });
  const pre = h("pre");
  const view = h("div", {}, [h("code", {}, "")]);
  view.firstChild.appendChild(pre);
  names.forEach((name, i) => {
    const tab = h("button", { class: "file-tab" + (i === 0 ? " active" : ""), onclick: () => {
      tabs.querySelectorAll(".file-tab").forEach((t) => t.classList.remove("active"));
      tab.classList.add("active"); pre.textContent = files[name];
    } }, name);
    tabs.appendChild(tab);
  });
  if (names.length) pre.textContent = files[names[0]];
  body.appendChild(h("div", { style: "margin-bottom:8px" }, `Generated ${names.length} file(s):`));
  body.appendChild(tabs);
  body.appendChild(view);
  status(`Generated ${names.length} files`, "ok");
}

async function showArxml() {
  await saveProject();
  const xml = await api("GET", "/api/arxml");
  const body = openOutput("ARXML Export");
  body.innerHTML = "";
  body.appendChild(h("pre", {}, xml));
  status("Exported ARXML", "ok");
}

// --------------------------------------------------------------------------
// Wire-up
// --------------------------------------------------------------------------
function renderAll() { renderSidebar(); renderEditor(); renderStatusProject(); }

function init() {
  document.getElementById("btn-example").onclick = loadExample;
  document.getElementById("btn-save").onclick = saveProject;
  document.getElementById("btn-validate").onclick = runValidate;
  document.getElementById("btn-generate").onclick = runGenerate;
  document.getElementById("btn-arxml").onclick = showArxml;
  document.getElementById("output-close").onclick = closeOutput;
  loadProject();
}
document.addEventListener("DOMContentLoaded", init);
