/* ══════════════════════════════════════════════════════
   ANTI-API · app.js
   Un tab de chat independiente por modelo
══════════════════════════════════════════════════════ */

// ── DOM refs fijos ────────────────────────────────────
const promptInput      = document.getElementById("prompt-input");
const sendButton       = document.getElementById("send-button");
const headlessCheckbox = document.getElementById("headless-checkbox");
const keepPageCheckbox = document.getElementById("keep-page-checkbox");
const newChatButton    = document.getElementById("new-chat-button");
const cookieJsonInput  = document.getElementById("cookie-json-input");
const saveCookieButton = document.getElementById("save-cookie-button");
const loadCookieButton = document.getElementById("load-cookie-button");
const cookieStatusText = document.getElementById("cookie-status-text");
const cookieDot        = document.getElementById("cookie-dot");
const verifyButton     = document.getElementById("verify-button");
const verifyResult     = document.getElementById("verify-result");
const modelTabsEl      = document.getElementById("model-tabs");
const chatPanelsEl     = document.getElementById("chat-panels");
const turnCounter      = document.getElementById("turn-counter");
const clearHistoryBtn  = document.getElementById("clear-history-button");
const sortDateBtn      = document.getElementById("sort-date-button");
const statusText       = document.getElementById("status-text");
const statusDot        = document.getElementById("status-dot");
const activeModelDisp  = document.getElementById("active-model-display");
const modelDescription = document.getElementById("model-description");
const toast            = document.getElementById("toast");
const toastText        = document.getElementById("toast-text");

// ── State global ──────────────────────────────────────
let models        = [];
let activeModel   = null;   // nombre del modelo en tab activo
let allCookies    = {};     // { modelName: cookiesDict }

// Estado por modelo
// { modelName: { history: [], turnN: 0, pendingCount: 0 } }
let modelState    = {};

// ── Helpers ───────────────────────────────────────────
function showToast(msg, timeout = 4000) {
  toastText.textContent = msg;
  toast.hidden = false;
  if (timeout) setTimeout(() => { toast.hidden = true; }, timeout);
}

function setStatus(online, label) {
  statusText.textContent = label;
  statusDot.className = "status-dot " + (online ? "online" : "error");
}

function formatTS(isoStr) {
  if (!isoStr) return "";
  const d = new Date(isoStr);
  const fecha = d.toLocaleDateString("es-ES", { day: "2-digit", month: "2-digit", year: "numeric" });
  const hora  = d.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  return `${fecha} ${hora}`;
}

// ── Cookie UI ─────────────────────────────────────────
function setCookieUI(hasCookies) {
  if (hasCookies) {
    cookieDot.className = "cookie-dot ok";
    cookieStatusText.textContent = "Configuradas";
  } else {
    cookieDot.className = "cookie-dot";
    cookieStatusText.textContent = "Sin configurar";
  }
}

// ── Persist cookies ───────────────────────────────────
function saveCookiesLS() {
  localStorage.setItem("anti_cookies", JSON.stringify(allCookies));
}
function loadCookiesLS() {
  try {
    const s = localStorage.getItem("anti_cookies");
    if (s) allCookies = JSON.parse(s);
  } catch { allCookies = {}; }
}

// ── Persist history por modelo ────────────────────────
function saveModelHistory(modelName) {
  const st = modelState[modelName];
  if (!st) return;
  localStorage.setItem(`anti_history_${modelName}`, JSON.stringify(st.history));
  localStorage.setItem(`anti_turn_${modelName}`, String(st.turnN));
}
function loadModelHistory(modelName) {
  try {
    const h = localStorage.getItem(`anti_history_${modelName}`);
    const t = localStorage.getItem(`anti_turn_${modelName}`);
    if (h) modelState[modelName].history = JSON.parse(h);
    if (t) modelState[modelName].turnN   = parseInt(t, 10) || 0;
  } catch {}
}

// ── Cookie sidebar actions ────────────────────────────
function saveCookies() {
  const raw = cookieJsonInput.value.trim();
  if (!activeModel) { showToast("Selecciona un modelo (tab)."); return; }
  if (!raw) { showToast("Pega las cookies JSON primero."); return; }
  try {
    allCookies[activeModel] = JSON.parse(raw);
    saveCookiesLS();
    setCookieUI(true);
    showToast("Cookies guardadas para " + activeModel);
  } catch { showToast("JSON de cookies inválido."); }
}
function loadCookies() {
  if (!activeModel) { showToast("Selecciona un modelo (tab)."); return; }
  if (allCookies[activeModel]) {
    cookieJsonInput.value = JSON.stringify(allCookies[activeModel], null, 2);
    setCookieUI(true);
  } else {
    showToast("No hay cookies guardadas para " + activeModel);
  }
}

// ── Tab management ────────────────────────────────────
function getPanel(modelName) {
  return document.getElementById(`panel-${modelName}`);
}
function getTab(modelName) {
  return document.getElementById(`tab-${modelName}`);
}

function switchTab(modelName) {
  // Ocultar todos
  document.querySelectorAll(".model-tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll(".chat-panel").forEach(p => p.classList.remove("active"));

  // Activar el seleccionado
  const tab   = getTab(modelName);
  const panel = getPanel(modelName);
  if (tab)   tab.classList.add("active");
  if (panel) panel.classList.add("active");

  activeModel = modelName;

  // Actualizar sidebar
  const m = models.find(x => x.name === modelName);
  activeModelDisp.textContent = m ? (m.display_name || m.name) : modelName;
  modelDescription.textContent = m ? (m.description || m.display_name || m.name) : "";

  // Mostrar cookies del modelo activo
  if (allCookies[modelName]) {
    cookieJsonInput.value = JSON.stringify(allCookies[modelName], null, 2);
    setCookieUI(true);
  } else {
    cookieJsonInput.value = "";
    setCookieUI(false);
  }

  // Mostrar estado de verificación del modelo
  updateVerifyUI(modelName);

  updateTurnCounter();
}

function buildTab(model) {
  const tab = document.createElement("button");
  tab.className = "model-tab";
  tab.id = `tab-${model.name}`;

  const dot = document.createElement("span");
  dot.className = "tab-dot";
  tab.appendChild(dot);

  const label = document.createElement("span");
  label.textContent = model.display_name || model.name;
  tab.appendChild(label);

  tab.addEventListener("click", () => switchTab(model.name));
  return tab;
}

function buildPanel(model) {
  const panel = document.createElement("div");
  panel.className = "chat-panel";
  panel.id = `panel-${model.name}`;

  const empty = document.createElement("div");
  empty.className = "chat-empty";
  empty.id = `empty-${model.name}`;
  empty.innerHTML = `<div class="empty-icon">💬</div><p>${model.display_name || model.name}</p><span>Escribe algo para empezar</span>`;
  panel.appendChild(empty);

  return panel;
}

function setTabPending(modelName, pending) {
  const tab = getTab(modelName);
  if (!tab) return;
  let dot = tab.querySelector(".tab-dot, .tab-pending");
  if (pending) {
    dot.className = "tab-pending";
  } else {
    dot.className = "tab-dot";
  }
}

// ── Turn counter ──────────────────────────────────────
function updateTurnCounter() {
  if (!activeModel) { turnCounter.textContent = "0 turnos"; return; }
  const n = modelState[activeModel]?.turnN || 0;
  turnCounter.textContent = n === 0 ? "0 turnos" : n === 1 ? "1 turno" : `${n} turnos`;
}

// ── Render history en panel ───────────────────────────
function renderHistory(modelName) {
  const panel = getPanel(modelName);
  const empty = document.getElementById(`empty-${modelName}`);
  const st    = modelState[modelName];
  if (!panel || !st) return;

  // Borrar bloques previos (no el empty)
  Array.from(panel.children).forEach(el => {
    if (!el.classList.contains("chat-empty")) el.remove();
  });

  if (st.history.length === 0) {
    if (empty) empty.style.display = "";
    return;
  }
  if (empty) empty.style.display = "none";

  st.history.forEach(entry => {
    panel.appendChild(buildBlock(entry));
  });

  panel.scrollTop = panel.scrollHeight;
}

// ── Build chat blocks ─────────────────────────────────
function buildBlock(entry) {
  const block = document.createElement("div");
  block.className = "msg-block";
  block.id = `turn-${entry.model}-${entry.n}`;
  block.dataset.ts = entry.ts || "";

  const label = document.createElement("div");
  label.className = "turn-label";

  const numBadge = document.createElement("span");
  numBadge.className = "turn-number";
  numBadge.textContent = `#${entry.n}`;
  label.appendChild(numBadge);

  const tsSpan = document.createElement("span");
  tsSpan.textContent = `  Enviado: ${formatTS(entry.ts)}`;
  label.appendChild(tsSpan);

  block.appendChild(label);

  const q = document.createElement("div");
  q.className = "msg-question";
  q.textContent = entry.question;
  block.appendChild(q);

  if (entry.answer !== undefined) {
    block.appendChild(buildAnswer(entry.model, entry.answer, entry.ts_resp, entry.n, entry.question));
  }

  return block;
}

function buildAnswer(model, text, ts_resp, questionN, questionText) {
  const wrap = document.createElement("div");

  const meta = document.createElement("div");
  meta.className = "msg-meta";

  const badge = document.createElement("span");
  badge.className = "model-badge";
  badge.textContent = (model || "IA").toUpperCase();
  meta.appendChild(badge);

  if (questionN) {
    const numSpan = document.createElement("span");
    numSpan.textContent = `Respuesta #${questionN}`;
    numSpan.style.fontWeight = "600";
    meta.appendChild(numSpan);
  }

  if (ts_resp) {
    const tsSpan = document.createElement("span");
    tsSpan.textContent = formatTS(ts_resp);
    meta.appendChild(tsSpan);
  }
  wrap.appendChild(meta);

  // Echo de la pregunta original dentro de la respuesta
  if (questionText) {
    const echo = document.createElement("div");
    echo.className = "answer-question-echo";
    const echoLabel = document.createElement("span");
    echoLabel.className = "echo-label";
    echoLabel.textContent = `Pregunta #${questionN || "?"}:`;
    echo.appendChild(echoLabel);
    echo.appendChild(document.createTextNode(questionText));
    wrap.appendChild(echo);
  }

  const ans = document.createElement("div");
  ans.className = "msg-answer" + (text.startsWith("ERROR:") ? " msg-error" : "");
  ans.textContent = text.startsWith("ERROR:") ? "❌ " + text.slice(7) : text;
  if (text.startsWith("ERROR:")) {
    ans.style.borderColor = "rgba(239,68,68,0.4)";
    ans.style.color = "#ef4444";
  }
  wrap.appendChild(ans);

  return wrap;
}

// ── Send prompt ───────────────────────────────────────
async function sendPrompt() {
  const model    = activeModel;
  const prompt   = promptInput.value.trim();
  const headless = headlessCheckbox.checked;
  const keepPage = keepPageCheckbox.checked;

  if (!model)  { showToast("Selecciona un tab de modelo."); return; }
  if (!prompt) { showToast("Escribe un prompt."); return; }

  let cookies = null;
  const cookieRaw = cookieJsonInput.value.trim();
  if (cookieRaw) {
    try { cookies = JSON.parse(cookieRaw); }
    catch { showToast("JSON de cookies inválido."); return; }
  }

  const st = modelState[model];
  st.turnN++;
  const entry = { n: st.turnN, model, question: prompt, ts: new Date().toISOString() };
  st.history.push(entry);
  saveModelHistory(model);

  // Render pregunta + thinking
  const panel = getPanel(model);
  const empty = document.getElementById(`empty-${model}`);
  if (empty) empty.style.display = "none";

  const block = buildBlock(entry);
  const thinkId = `thinking-${model}-${entry.n}`;
  const thinkBubble = document.createElement("div");
  thinkBubble.className = "msg-answer loading";
  thinkBubble.id = thinkId;
  thinkBubble.innerHTML = `<div class="thinking-dots"><span></span><span></span><span></span></div>`;
  block.appendChild(thinkBubble);
  panel.appendChild(block);
  panel.scrollTop = panel.scrollHeight;

  updateTurnCounter();
  promptInput.value = "";
  autoResize();

  // Indicador en tab
  st.pendingCount++;
  setTabPending(model, true);
  updateGlobalStatus();

  try {
    const payload = { model, prompt, headless, keep_page: keepPage };
    if (cookies) payload.cookies = cookies;

    const res  = await fetch("/api/send", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();

    const tb = document.getElementById(thinkId);
    if (tb) tb.remove();

    const ts_resp = new Date().toISOString();

    if (!res.ok || !data.success) {
      entry.answer  = "ERROR: " + (data.error || "Error desconocido");
      entry.ts_resp = ts_resp;
    } else {
      entry.answer  = data.response;
      entry.ts_resp = ts_resp;
    }

    saveModelHistory(model);
    block.appendChild(buildAnswer(data.model || model, entry.answer, ts_resp, entry.n, entry.question));
    panel.scrollTop = panel.scrollHeight;

  } catch (err) {
    const tb = document.getElementById(thinkId);
    if (tb) tb.remove();
    entry.answer = "ERROR: " + err.message;
    saveModelHistory(model);
    block.appendChild(buildAnswer(model, entry.answer, new Date().toISOString(), entry.n, entry.question));
    panel.scrollTop = panel.scrollHeight;
  } finally {
    st.pendingCount = Math.max(0, st.pendingCount - 1);
    if (st.pendingCount === 0) setTabPending(model, false);
    updateGlobalStatus();
  }
}

function updateGlobalStatus() {
  const total = Object.values(modelState).reduce((s, st) => s + st.pendingCount, 0);
  if (total === 0) setStatus(true, "Panel listo");
  else setStatus(true, total === 1 ? "Procesando..." : `Procesando (${total})...`);
}

// ── Verify connection ─────────────────────────────────
async function verifyConnection() {
  if (!activeModel) { showToast("Selecciona un modelo (tab)."); return; }
  const cookieRaw = cookieJsonInput.value.trim();
  if (!cookieRaw) { showToast("Pega las cookies antes de verificar."); return; }
  let cookies;
  try { cookies = JSON.parse(cookieRaw); }
  catch { showToast("JSON de cookies inválido."); return; }

  verifyButton.disabled = true;
  verifyButton.textContent = "Verificando...";
  verifyResult.hidden = false;
  verifyResult.textContent = "Conectando...";
  verifyResult.style.color = "";

  try {
    const res  = await fetch("/api/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model: activeModel, cookies, headless: headlessCheckbox.checked }),
    });
    const data = await res.json();
    if (data.success) {
      verifyResult.textContent = "✅ " + data.message;
      verifyResult.style.color = "var(--green)";
      setCookieUI(true);
    } else {
      verifyResult.textContent = "❌ " + data.error;
      verifyResult.style.color = "var(--red)";
    }
  } catch (err) {
    verifyResult.textContent = "❌ Error de red: " + err.message;
    verifyResult.style.color = "var(--red)";
  } finally {
    verifyButton.disabled = false;
    verifyButton.textContent = "Verificar conexión";
  }
}

// ── Clear history ─────────────────────────────────────
function clearHistory() {
  if (!activeModel) return;
  if (!confirm(`¿Borrar historial de ${activeModel}?`)) return;
  const st = modelState[activeModel];
  st.history = [];
  st.turnN   = 0;
  saveModelHistory(activeModel);
  renderHistory(activeModel);
  updateTurnCounter();
}

// ── Sort by date ──────────────────────────────────────
function sortByDate() {
  if (!activeModel) return;
  const st = modelState[activeModel];
  if (!st || st.history.length < 2) return;
  st.history.sort((a, b) => new Date(a.ts) - new Date(b.ts));
  saveModelHistory(activeModel);
  renderHistory(activeModel);
  showToast("Historial ordenado por fecha de envio", 2000);
}

// ── Auto-verificación al arrancar ────────────────────
// Estado de verificación por modelo para mostrarlo en sidebar al cambiar tab
const modelVerifyState = {}; // { modelName: { status: 'ok'|'error'|'checking'|'none', msg: '' } }

async function autoVerifyOne(modelName) {
  const cookies = allCookies[modelName];
  if (!cookies || !Object.keys(cookies).length) {
    modelVerifyState[modelName] = { status: "none", msg: "" };
    return;
  }

  modelVerifyState[modelName] = { status: "checking", msg: "Verificando sesión..." };
  updateVerifyUI(modelName);

  // Poner dot en amarillo mientras verifica
  const tab = getTab(modelName);
  if (tab) {
    let dot = tab.querySelector(".tab-dot, .tab-pending");
    if (dot) dot.className = "tab-pending";
  }

  // Cargar las cookies en el textarea si es el modelo activo
  if (modelName === activeModel) {
    cookieJsonInput.value = JSON.stringify(cookies, null, 2);
    setCookieUI(true);
  }

  try {
    const res  = await fetch("/api/validate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        model: modelName,
        cookies,
        headless: true,
      }),
    });
    const data = await res.json();

    if (data.success) {
      modelVerifyState[modelName] = { status: "ok", msg: "✅ Sesión activa" };
      // Dot verde permanente
      if (tab) {
        let dot = tab.querySelector(".tab-dot, .tab-pending");
        if (dot) { dot.className = "tab-dot"; dot.style.background = "var(--green)"; }
      }
    } else {
      modelVerifyState[modelName] = { status: "error", msg: "❌ " + (data.error || "Sesión inválida") };
      if (tab) {
        let dot = tab.querySelector(".tab-dot, .tab-pending");
        if (dot) { dot.className = "tab-dot"; dot.style.background = "var(--red)"; }
      }
    }
  } catch (e) {
    modelVerifyState[modelName] = { status: "error", msg: "❌ Error de red: " + e.message };
    if (tab) {
      let dot = tab.querySelector(".tab-dot, .tab-pending");
      if (dot) { dot.className = "tab-dot"; dot.style.background = "var(--red)"; }
    }
  }

  updateVerifyUI(modelName);
}

function updateVerifyUI(modelName) {
  // Solo actualizar el sidebar si el modelo activo coincide
  if (modelName !== activeModel) return;
  const vs = modelVerifyState[modelName];
  if (!vs || vs.status === "none") {
    verifyResult.hidden = true;
    return;
  }
  verifyResult.hidden = false;
  verifyResult.textContent = vs.msg;
  verifyResult.style.color =
    vs.status === "ok"       ? "var(--green)" :
    vs.status === "error"    ? "var(--red)"   :
    "var(--yellow)";
}

function autoVerifyAll() {
  // Lanzar en paralelo — una petición por modelo con cookies
  models.forEach(m => {
    if (allCookies[m.name] && Object.keys(allCookies[m.name]).length > 0) {
      autoVerifyOne(m.name);
    } else {
      modelVerifyState[m.name] = { status: "none", msg: "" };
    }
  });
}

// ── Textarea autosize ─────────────────────────────────
function autoResize() {
  promptInput.style.height = "auto";
  promptInput.style.height = Math.min(promptInput.scrollHeight, 160) + "px";
}

// ── Init ─────────────────────────────────────────────
async function init() {
  loadCookiesLS();

  try {
    const res = await fetch("/api/models");
    if (!res.ok) throw new Error("No se pudo cargar modelos.");
    models = await res.json();
    if (!models.length) throw new Error("No hay modelos en models.json");

    // Crear tab + panel + state por cada modelo
    models.forEach(m => {
      modelState[m.name]       = { history: [], turnN: 0, pendingCount: 0 };
      modelVerifyState[m.name] = { status: "none", msg: "" };
      loadModelHistory(m.name);

      modelTabsEl.appendChild(buildTab(m));
      const panel = buildPanel(m);
      chatPanelsEl.appendChild(panel);

      // Renderizar historial cargado
      renderHistory(m.name);
    });

    // Activar primer tab
    switchTab(models[0].name);
    setStatus(true, "Panel listo");

    // Auto-verificar en paralelo todos los modelos con cookies guardadas
    // Sin bloquear — cada uno actualiza su tab dot cuando termina
    autoVerifyAll();

  } catch (err) {
    setStatus(false, "Error de inicio");
    showToast(err.message, 0);
  }

  // Events
  sendButton.addEventListener("click", sendPrompt);
  saveCookieButton.addEventListener("click", saveCookies);
  loadCookieButton.addEventListener("click", loadCookies);
  verifyButton.addEventListener("click", verifyConnection);
  clearHistoryBtn.addEventListener("click", clearHistory);
  sortDateBtn.addEventListener("click", sortByDate);

  newChatButton.addEventListener("click", async () => {
    if (!activeModel) { showToast("Selecciona un tab."); return; }
    newChatButton.disabled = true;
    newChatButton.textContent = "↺ Reseteando...";
    try {
      await fetch("/api/session/reset", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ model: activeModel }),
      });
      newChatButton.textContent = "✓ Listo";
      setTimeout(() => { newChatButton.textContent = "↺ Nueva conversación"; }, 1500);
    } catch {
      newChatButton.textContent = "↺ Nueva conversación";
      showToast("No se pudo resetear la sesión.");
    } finally {
      setTimeout(() => { newChatButton.disabled = false; }, 1600);
    }
  });

  promptInput.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendPrompt();
    }
  });
  promptInput.addEventListener("input", autoResize);
}

window.addEventListener("DOMContentLoaded", init);
