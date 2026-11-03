"use strict";

// Strings from the server are rendered with textContent only.

const JOB_ID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const POLL_INTERVAL_MS = 1000;
const LLM_STATUS_TEXT = {
  connected: "LLM 서버에 연결되었습니다.",
  unreachable:
    "LLM 서버에 연결할 수 없거나 응답이 올바르지 않습니다. " +
    "서버 실행 상태, 주소, 인증 설정을 확인하세요.",
  model_missing:
    "LLM 서버에 설정한 모델이 없습니다. NURILAB_LLM_MODEL과 서버에 올린 모델을 확인하세요.",
  timeout: "LLM 서버 응답 시간이 초과되었습니다. 서버 상태를 확인하세요.",
};
const JOB_STATUS_TEXT = {
  queued: "대기 중",
  running: "분석 중",
  completed: "완료",
  failed: "실패",
};

const state = {
  rules: null,
  // Kept files as { file, path }; path is the upload path sent to the server.
  selected: [],
  // What the selection line names; total counts files outside excluded folders.
  choice: { kind: "", name: "", total: 0 },
  // Bumped on every new selection so a slow folder drop cannot overwrite a later one.
  selectionVersion: 0,
  // True while the upload request is in flight; selection is locked meanwhile.
  uploading: false,
  llmConnected: false,
  // Bumped on every LLM check so a slow earlier answer cannot overwrite a later one.
  llmCheckVersion: 0,
  busy: false,
};

function byId(id) {
  return document.getElementById(id);
}

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) {
    node.className = className;
  }
  if (text !== undefined && text !== null) {
    node.textContent = String(text);
  }
  return node;
}

async function requestJson(url, options) {
  const response = await fetch(url, options);
  let body = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  return { ok: response.ok, status: response.status, body };
}

function errorText(result) {
  if (result.body && typeof result.body.message === "string") {
    return result.body.message;
  }
  return `요청에 실패했습니다 (HTTP ${result.status}).`;
}

function showMessage(text, isError) {
  const message = byId("message");
  message.textContent = text;
  message.classList.toggle("error", Boolean(isError));
}

function apiPath(jobId, suffix) {
  if (!JOB_ID_PATTERN.test(jobId)) {
    throw new Error("invalid job id");
  }
  return `/api/analyses/${jobId}${suffix}`;
}

// The only place that sets an href: a checked job id and a fixed path.
function reportLink(jobId, kind, label) {
  const link = element("a", "button-link", label);
  link.href = apiPath(jobId, `/report.${kind}`);
  link.setAttribute("download", "");
  return link;
}

function uploadPath(file) {
  return file.webkitRelativePath || file.name;
}

function fileSuffix(name) {
  const dot = name.lastIndexOf(".");
  return dot > 0 && dot < name.length - 1 ? name.slice(dot) : "";
}

// Same rule as the server: only parts below the top folder count, since the
// top folder itself is the analysis root.
function underExcludedDir(path) {
  return path
    .split("/")
    .slice(1)
    .some((part) => state.rules.excluded_dirs.includes(part));
}

// Keep .py files that are not under an excluded folder.
function keepFile(path) {
  const parts = path.split("/");
  return (
    state.rules.extensions.includes(fileSuffix(parts[parts.length - 1])) &&
    !underExcludedDir(path)
  );
}

function selectionProblem() {
  if (state.selected.length === 0) {
    return "분석할 .py 파일이 없습니다.";
  }
  if (state.selected.length > state.rules.max_python_files) {
    return `.py 파일은 최대 ${state.rules.max_python_files}개까지 올릴 수 있습니다.`;
  }
  if (selectedBytes() > state.rules.max_upload_bytes) {
    const limitMiB = Math.floor(state.rules.max_upload_bytes / (1024 * 1024));
    return `업로드 크기는 최대 ${limitMiB} MiB입니다.`;
  }
  return null;
}

function updateRunButton() {
  const llmReady = !byId("llm-toggle").checked || state.llmConnected;
  const ready = state.rules !== null && selectionProblem() === null;
  byId("run-button").disabled = state.busy || !ready || !llmReady;
}

function selectedBytes() {
  return state.selected.reduce((sum, item) => sum + item.file.size, 0);
}

// Buttons and drops both end here. kind is "파일" or "폴더", name the
// chosen file or top folder; an empty name means nothing is chosen.
function applySelection(items, kind, name) {
  state.selected = state.rules ? items.filter((item) => keepFile(item.path)) : [];
  // Drops never read excluded folders, so the button path leaves them out too.
  const total = state.rules
    ? items.filter((item) => !underExcludedDir(item.path)).length
    : items.length;
  state.choice = { kind, name, total };
  showMessage("", false);
  showSelectionNotice(name ? selectionProblem() : null, true);
  updateRunButton();
}

// Every notice about an upload that cannot go through (selection limits,
// drop errors, rejected uploads) shows on the selection line, under the
// chosen name; without a name it takes the place of the empty-selection text.
function showSelectionNotice(text, isError) {
  const { kind, name, total } = state.choice;
  const selection = byId("selection");
  selection.replaceChildren();
  if (name) {
    const kib = (selectedBytes() / 1024).toFixed(1);
    selection.append(
      element("div", "selection-name", `${kind}: ${name}`),
      element(
        "div",
        null,
        `분석 대상 .py ${state.selected.length}개 (제외 폴더 밖 ${total}개 중), ${kib} KiB`,
      ),
    );
  } else if (!text) {
    selection.append(element("div", null, "선택한 파일이 없습니다."));
  }
  if (text) {
    selection.append(element("div", isError ? "error" : null, text));
  }
}

function chooseFromInput(input, otherInputId) {
  state.selectionVersion += 1;
  byId(otherInputId).value = "";
  const files = Array.from(input.files);
  // Without this, picking the same file again after it changed fires no event.
  input.value = "";
  const items = files.map((file) => ({ file, path: uploadPath(file) }));
  if (input.id === "file-input") {
    applySelection(items, "파일", files.length ? files[0].name : "");
  } else {
    applySelection(items, "폴더", items.length ? items[0].path.split("/")[0] : "");
  }
}

function entryFile(entry) {
  return new Promise((resolve, reject) => entry.file(resolve, reject));
}

// readEntries() returns one batch at a time (100 in Chrome) until it is empty.
async function readAllEntries(directory) {
  const reader = directory.createReader();
  const entries = [];
  for (;;) {
    const batch = await new Promise((resolve, reject) =>
      reader.readEntries(resolve, reject),
    );
    if (batch.length === 0) {
      return entries;
    }
    entries.push(...batch);
  }
}

// fullPath is "/myproj/pkg/a.py"; without the leading "/" it matches the
// webkitRelativePath form the folder button gives.
async function collectEntry(entry, depth, items) {
  if (entry.isFile) {
    items.push({ file: await entryFile(entry), path: entry.fullPath.replace(/^\/+/, "") });
    return;
  }
  // Below the top folder, excluded folders are dropped anyway, so skip reading them.
  if (depth > 0 && state.rules.excluded_dirs.includes(entry.name)) {
    return;
  }
  for (const child of await readAllEntries(entry)) {
    await collectEntry(child, depth + 1, items);
  }
}

async function dropSelection(event) {
  event.preventDefault();
  byId("drop-zone").classList.remove("drag-over");
  if (!state.rules || state.uploading) {
    return;
  }
  // Entries must be taken before the first await: the item list is emptied
  // once the drop event returns.
  const entries = Array.from(event.dataTransfer.items)
    .filter((item) => item.kind === "file")
    .map((item) => item.webkitGetAsEntry())
    .filter((entry) => entry !== null);
  const version = ++state.selectionVersion;
  byId("file-input").value = "";
  byId("folder-input").value = "";
  // Drop problems and progress leave nothing selected.
  if (entries.length !== 1) {
    applySelection([], "", "");
    showSelectionNotice("파일 1개 또는 폴더 1개만 끌어 놓을 수 있습니다.", true);
    return;
  }
  const entry = entries[0];
  if (!entry.isFile) {
    applySelection([], "", "");
    showSelectionNotice("폴더를 읽는 중입니다.", false);
  }
  try {
    const items = [];
    await collectEntry(entry, 0, items);
    if (version === state.selectionVersion) {
      applySelection(items, entry.isFile ? "파일" : "폴더", entry.name);
    }
  } catch {
    if (version === state.selectionVersion) {
      applySelection([], "", "");
      showSelectionNotice("끌어 놓은 항목을 읽지 못했습니다.", true);
    }
  }
}

async function checkLlm() {
  const version = ++state.llmCheckVersion;
  const status = byId("llm-status");
  state.llmConnected = false;
  updateRunButton();
  if (!byId("llm-toggle").checked) {
    status.hidden = true;
    return;
  }
  status.hidden = false;
  status.textContent = "LLM 연결을 확인하는 중입니다.";
  status.classList.remove("error");
  let result = null;
  try {
    result = await requestJson("/api/llm-status");
  } catch {
    // fetch rejects when this web server cannot be reached; handled below.
  }
  if (version !== state.llmCheckVersion) {
    return;
  }
  if (result === null) {
    status.textContent = "LLM 연결 상태를 확인하지 못했습니다. 웹 서버 연결을 확인하세요.";
    status.classList.add("error");
    return;
  }
  if (!result.ok || !result.body) {
    status.textContent = errorText(result);
    status.classList.add("error");
    return;
  }
  const text = LLM_STATUS_TEXT[result.body.status] || LLM_STATUS_TEXT.unreachable;
  status.textContent = `${text} (모델: ${result.body.model})`;
  state.llmConnected = result.body.status === "connected";
  status.classList.toggle("error", !state.llmConnected);
  updateRunButton();
}

// Upload errors are shown under the chosen name, so the choice must not change
// until the server answers. Only the request is locked, not the analysis after it.
function setUploading(uploading) {
  state.uploading = uploading;
  for (const id of ["file-input", "folder-input"]) {
    byId(id).disabled = uploading;
  }
  for (const node of document.querySelectorAll(".picker, .drop-zone")) {
    node.classList.toggle("disabled", uploading);
  }
}

async function runAnalysis() {
  const form = new FormData();
  form.append("review_mode", byId("llm-toggle").checked ? "local" : "mock");
  for (const item of state.selected) {
    // The third argument keeps the folder path, which append() drops by default.
    form.append("files", item.file, item.path);
  }
  state.busy = true;
  updateRunButton();
  showSelectionNotice(null, false);
  showMessage("업로드하는 중입니다.", false);
  byId("result").hidden = true;
  // Clear the previous job's result so it never shows under the new job.
  byId("summary").textContent = "";
  byId("findings").replaceChildren();
  byId("downloads").replaceChildren();
  setUploading(true);
  try {
    const result = await requestJson("/api/analyses", { method: "POST", body: form });
    setUploading(false);
    if (result.status !== 202 || !result.body || !JOB_ID_PATTERN.test(result.body.id)) {
      showMessage("", false);
      if (result.body && result.body.code === "llm_unavailable") {
        // An LLM problem, not an upload problem: shown with the run button.
        showMessage(errorText(result), true);
      } else {
        showSelectionNotice(errorText(result), true);
      }
      finishJob();
      return;
    }
    showMessage("", false);
    pollJob(result.body.id);
  } catch {
    setUploading(false);
    showMessage("", false);
    // fetch reports a changed file and a lost connection the same way.
    showSelectionNotice(
      "업로드하지 못했습니다. 서버 연결을 확인하고, 선택한 뒤 파일이 바뀌었다면 다시 선택하세요.",
      true,
    );
    finishJob();
  }
}

function finishJob() {
  state.busy = false;
  updateRunButton();
}

async function pollJob(jobId) {
  let job;
  try {
    const result = await requestJson(apiPath(jobId, ""));
    if (!result.ok) {
      showMessage(errorText(result), true);
      finishJob();
      return;
    }
    job = result.body;
  } catch {
    showMessage("서버에 연결할 수 없습니다.", true);
    finishJob();
    return;
  }
  byId("result").hidden = false;
  byId("job-state").textContent = `상태: ${JOB_STATUS_TEXT[job.status] || job.status}`;
  renderOverview(job);
  if (job.status === "completed") {
    await renderResult(jobId).catch(() => showMessage("서버에 연결할 수 없습니다.", true));
    finishJob();
  } else if (job.status === "failed") {
    showMessage(job.error ? job.error.message : "분석에 실패했습니다.", true);
    finishJob();
  } else {
    setTimeout(() => pollJob(jobId), POLL_INTERVAL_MS);
  }
}

function reviewLabel(review) {
  if (review.client === "mock") {
    return "Mock (LLM 미사용)";
  }
  return `LLM (${review.model || "모델 미상"})`;
}

function renderOverview(job) {
  const rows = [
    ["위험도", job.risk_level || "-"],
    ["정적 분석 위험도", job.static_risk_level || "-"],
    ["리뷰", reviewLabel(job.review)],
    ["리뷰 상태", job.review.status || "-"],
    ["업로드", job.upload_name],
    ["분석 대상 .py", job.file_count],
  ];
  const overview = byId("overview");
  overview.replaceChildren();
  for (const [label, value] of rows) {
    overview.append(element("dt", null, label), element("dd", null, value));
  }
}

function findingLocation(finding) {
  const line = finding.line === null ? "No line" : `Line ${finding.line}`;
  const column = finding.column === null ? "" : `, Column ${finding.column}`;
  return `${finding.file ? `${finding.file}: ` : ""}${line}${column}`;
}

async function renderResult(jobId) {
  const downloads = byId("downloads");
  downloads.replaceChildren(
    reportLink(jobId, "json", "JSON 보고서"),
    reportLink(jobId, "html", "HTML 보고서"),
  );
  const result = await requestJson(apiPath(jobId, "/result"));
  if (!result.ok || !result.body) {
    showMessage(errorText(result), true);
    return;
  }
  byId("summary").textContent = result.body.summary || "";
  const findings = byId("findings");
  findings.replaceChildren();
  if (result.body.findings.length === 0) {
    findings.append(element("li", "muted", "finding이 없습니다."));
  }
  for (const finding of result.body.findings) {
    const item = element("li", "finding");
    const heading = element("div", "finding-heading");
    heading.append(
      element("span", `severity severity-${finding.severity}`, finding.severity),
      element("strong", null, finding.title),
    );
    item.append(
      heading,
      element("div", "muted", `${findingLocation(finding)} · ${finding.source}`),
      element("p", null, finding.reason),
      element("p", "recommendation", finding.recommendation),
    );
    findings.append(item);
  }
}

async function init() {
  byId("file-input").addEventListener("change", (event) =>
    chooseFromInput(event.target, "folder-input"),
  );
  byId("folder-input").addEventListener("change", (event) =>
    chooseFromInput(event.target, "file-input"),
  );
  const dropZone = byId("drop-zone");
  dropZone.addEventListener("dragover", (event) => {
    event.preventDefault();
    if (state.uploading) {
      event.dataTransfer.dropEffect = "none";
      return;
    }
    event.dataTransfer.dropEffect = "copy";
    dropZone.classList.add("drag-over");
  });
  dropZone.addEventListener("dragleave", () => dropZone.classList.remove("drag-over"));
  dropZone.addEventListener("drop", dropSelection);
  // A drop that misses the zone would otherwise open the file in the tab.
  for (const type of ["dragover", "drop"]) {
    window.addEventListener(type, (event) => event.preventDefault());
  }
  byId("llm-toggle").addEventListener("change", checkLlm);
  byId("run-button").addEventListener("click", runAnalysis);
  const result = await requestJson("/api/upload-rules");
  if (!result.ok || !result.body) {
    showMessage(errorText(result), true);
    return;
  }
  state.rules = result.body;
  updateRunButton();
  // Some browsers restore the checked toggle on reload without a change event.
  if (byId("llm-toggle").checked) {
    checkLlm();
  }
}

document.addEventListener("DOMContentLoaded", init);
