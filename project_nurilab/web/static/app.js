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
  selected: [],
  llmConnected: false,
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

// Same rules as the server: keep .py files, and drop files under an excluded
// folder below the top folder (the top folder itself is the analysis root).
function keepFile(path) {
  const parts = path.split("/");
  if (!state.rules.extensions.includes(fileSuffix(parts[parts.length - 1]))) {
    return false;
  }
  return !parts.slice(1).some((part) => state.rules.excluded_dirs.includes(part));
}

function selectionProblem() {
  if (state.selected.length === 0) {
    return "분석할 .py 파일이 없습니다.";
  }
  if (state.selected.length > state.rules.max_python_files) {
    return `.py 파일은 최대 ${state.rules.max_python_files}개까지 올릴 수 있습니다.`;
  }
  const totalBytes = state.selected.reduce((sum, file) => sum + file.size, 0);
  if (totalBytes > state.rules.max_upload_bytes) {
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

function selectFiles(files, otherInputId) {
  byId(otherInputId).value = "";
  const all = Array.from(files);
  state.selected = state.rules ? all.filter((file) => keepFile(uploadPath(file))) : [];
  const totalBytes = state.selected.reduce((sum, file) => sum + file.size, 0);
  const selection = byId("selection");
  if (all.length === 0) {
    selection.textContent = "선택한 파일이 없습니다.";
  } else {
    const kib = (totalBytes / 1024).toFixed(1);
    selection.textContent =
      `분석 대상 .py ${state.selected.length}개 (선택 ${all.length}개 중), ${kib} KiB`;
  }
  const problem = all.length === 0 ? null : selectionProblem();
  showMessage(problem || "", Boolean(problem));
  updateRunButton();
}

async function checkLlm() {
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
  const result = await requestJson("/api/llm-status");
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

async function runAnalysis() {
  const form = new FormData();
  form.append("review_mode", byId("llm-toggle").checked ? "local" : "mock");
  for (const file of state.selected) {
    // The third argument keeps the folder path, which append() drops by default.
    form.append("files", file, uploadPath(file));
  }
  state.busy = true;
  updateRunButton();
  showMessage("업로드하는 중입니다.", false);
  byId("result").hidden = true;
  try {
    const result = await requestJson("/api/analyses", { method: "POST", body: form });
    if (result.status !== 202 || !result.body || !JOB_ID_PATTERN.test(result.body.id)) {
      showMessage(errorText(result), true);
      finishJob();
      return;
    }
    showMessage("", false);
    pollJob(result.body.id);
  } catch {
    showMessage("서버에 연결할 수 없습니다.", true);
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
    await renderResult(jobId);
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
    selectFiles(event.target.files, "folder-input"),
  );
  byId("folder-input").addEventListener("change", (event) =>
    selectFiles(event.target.files, "file-input"),
  );
  byId("llm-toggle").addEventListener("change", checkLlm);
  byId("run-button").addEventListener("click", runAnalysis);
  const result = await requestJson("/api/upload-rules");
  if (!result.ok || !result.body) {
    showMessage(errorText(result), true);
    return;
  }
  state.rules = result.body;
  updateRunButton();
}

document.addEventListener("DOMContentLoaded", init);
