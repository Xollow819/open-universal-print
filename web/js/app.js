/* Print Studio — library, viewer, scan, text docs, contacts, printing. */
"use strict";

const LS_KEY = "oup_docs_v1";
const MAX_IMG = 1600; // downscale uploads to keep localStorage sane

/* ---------- storage ---------- */
function loadDocs() {
  try { return JSON.parse(localStorage.getItem(LS_KEY) || "[]"); }
  catch (e) { return []; }
}
function saveDocs(docs) {
  localStorage.setItem(LS_KEY, JSON.stringify(docs));
}
function addDoc(doc) {
  const docs = loadDocs();
  doc.id = "d" + Date.now().toString(36) + Math.floor(Math.random() * 1e4);
  doc.createdAt = Date.now();
  docs.unshift(doc);
  saveDocs(docs);
  return doc;
}
function getDoc(id) { return loadDocs().find(d => d.id === id); }
function updateDoc(id, patch) {
  const docs = loadDocs();
  const d = docs.find(x => x.id === id);
  if (d) { Object.assign(d, patch); saveDocs(docs); }
}
function deleteDoc(id) {
  saveDocs(loadDocs().filter(d => d.id !== id));
}

/* ---------- helpers ---------- */
const $ = sel => document.querySelector(sel);
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g,
    c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function fmtDate(ts) { return new Date(ts).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" }); }
function fmtSize(n) {
  if (n == null) return "";
  return n > 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB";
}
function downscaleImage(dataUrl) {
  return new Promise(resolve => {
    const img = new Image();
    img.onload = () => {
      let { width: w, height: h } = img;
      const scale = Math.min(1, MAX_IMG / Math.max(w, h));
      w = Math.round(w * scale); h = Math.round(h * scale);
      const c = document.createElement("canvas");
      c.width = w; c.height = h;
      c.getContext("2d").drawImage(img, 0, 0, w, h);
      resolve(c.toDataURL("image/jpeg", 0.85));
    };
    img.onerror = () => resolve(dataUrl);
    img.src = dataUrl;
  });
}
function readFile(file) {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = reject;
    r.readAsDataURL(file);
  });
}

/* ---------- router ---------- */
const TITLES = {
  "view-library": "Library", "view-scan": "Scan", "view-create": "Create",
  "view-help": "Help", "view-viewer": "Document", "view-editor": "Edit photo",
  "view-textedit": "Text document", "view-contacts": "Contacts",
};
let navStack = ["view-library"];
function showView(id, push = true) {
  document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
  document.getElementById(id).classList.add("active");
  $("#topbar-title").textContent = TITLES[id] || "";
  document.querySelectorAll(".tab").forEach(t =>
    t.classList.toggle("active", t.dataset.view === id));
  if (push && navStack[navStack.length - 1] !== id) navStack.push(id);
  window.scrollTo(0, 0);
  if (id === "view-library") renderLibrary();
}
function goBack() {
  stopCamera();
  navStack.pop();
  const prev = navStack[navStack.length - 1] || "view-library";
  showView(prev, false);
}

/* ---------- library ---------- */
let listMode = "grid";
function renderLibrary() {
  const q = $("#search").value.trim().toLowerCase();
  const docs = loadDocs().filter(d =>
    !q || (d.name || "").toLowerCase().includes(q));
  const list = $("#doc-list");
  list.className = listMode;
  $("#empty-state").classList.toggle("hidden", docs.length > 0);
  list.innerHTML = docs.map(d => {
    const thumb = d.type === "image"
      ? `<div class="doc-thumb"><img src="${d.dataUrl}" alt=""></div>`
      : `<div class="doc-thumb">${d.type === "pdf" ? "📄" : "✎"}</div>`;
    return `<div class="doc-card" data-id="${d.id}">${thumb}
      <div class="doc-meta"><strong>${esc(d.name)}</strong>
      <small>${fmtDate(d.createdAt)}${d.size ? " · " + fmtSize(d.size) : ""}</small></div></div>`;
  }).join("");
  list.querySelectorAll(".doc-card").forEach(c =>
    c.addEventListener("click", () => openViewer(c.dataset.id)));
}

async function handleFiles(files) {
  for (const file of files) {
    const isPdf = file.type === "application/pdf" || /\.pdf$/i.test(file.name);
    let dataUrl = await readFile(file);
    let size = file.size;
    if (!isPdf && file.type.startsWith("image/")) {
      dataUrl = await downscaleImage(dataUrl);
      size = Math.round(dataUrl.length * 0.75);
    }
    addDoc({ name: file.name.replace(/\.[^.]+$/, "") || "Untitled",
             type: isPdf ? "pdf" : "image", dataUrl, size,
             mime: file.type });
  }
  renderLibrary();
  showView("view-library");
}

/* ---------- viewer ---------- */
let currentDocId = null;
function openViewer(id) {
  const d = getDoc(id);
  if (!d) return;
  currentDocId = id;
  const body = $("#viewer-body");
  if (d.type === "image") body.innerHTML = `<img src="${d.dataUrl}" alt="">`;
  else if (d.type === "pdf") body.innerHTML = `<iframe src="${d.dataUrl}"></iframe>`;
  else body.innerHTML = `<div class="text-doc"><h2>${esc(d.name)}</h2><div>${d.html || ""}</div></div>`;
  $("#viewer-edit").classList.toggle("hidden", d.type !== "image");
  showView("view-viewer");
}

/* ---------- printing ---------- */
function doPrint(html, cls = "") {
  const area = $("#print-area");
  area.className = cls;
  area.innerHTML = html;
  setTimeout(() => window.print(), 50);
}
function printDoc(id) {
  const d = getDoc(id);
  if (!d) return;
  if (d.type === "image") {
    doPrint(`<img class="doc" src="${d.dataUrl}">`);
  } else if (d.type === "pdf") {
    // Browsers can't inject a PDF into the print flow; open it for the native dialog.
    const w = window.open();
    w.document.write(`<iframe src="${d.dataUrl}" style="width:100%;height:100vh;border:0" onload="this.contentWindow.print()"></iframe>`);
  } else {
    doPrint(`<div class="sheet"><h1>${esc(d.name)}</h1><div class="body">${d.html || ""}</div></div>`, "sheet");
  }
}

/* ---------- scan ---------- */
let cameraStream = null;
async function startCamera() {
  try {
    cameraStream = await navigator.mediaDevices.getUserMedia(
      { video: { facingMode: "environment" } });
    const v = $("#camera-video");
    v.srcObject = cameraStream;
    $("#camera-box").classList.remove("hidden");
  } catch (e) {
    alert("Camera unavailable: " + e.message);
  }
}
function stopCamera() {
  if (cameraStream) {
    cameraStream.getTracks().forEach(t => t.stop());
    cameraStream = null;
  }
  $("#camera-box").classList.add("hidden");
}
function capturePhoto() {
  const v = $("#camera-video");
  if (!v.videoWidth) { alert("Camera not ready yet."); return; }
  const c = $("#scan-canvas");
  const scale = Math.min(1, MAX_IMG / Math.max(v.videoWidth, v.videoHeight));
  c.width = Math.round(v.videoWidth * scale);
  c.height = Math.round(v.videoHeight * scale);
  c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
  c.classList.remove("hidden");
  const name = "Scan " + new Date().toLocaleString();
  if (confirm(`Save this scan as "${name}"?`)) {
    addDoc({ name, type: "image", dataUrl: c.toDataURL("image/jpeg", 0.9) });
    stopCamera();
    c.classList.add("hidden");
    showView("view-library");
  }
}

/* ---------- text editor ---------- */
let editingId = null;
function openTextEditor(id = null) {
  editingId = id;
  const d = id ? getDoc(id) : null;
  $("#text-title").value = d ? d.name : "";
  $("#text-body").innerHTML = d ? (d.html || "") : "";
  showView("view-textedit");
}
function saveTextDoc() {
  const name = $("#text-title").value.trim() || "Untitled document";
  const html = $("#text-body").innerHTML;
  if (editingId) updateDoc(editingId, { name, html });
  else addDoc({ name, type: "text", html });
  showView("view-library");
}

/* ---------- contacts sheet ---------- */
function contactRow(name = "", phone = "", email = "") {
  const div = document.createElement("div");
  div.className = "contact-row";
  div.innerHTML = `<input placeholder="Name" value="${esc(name)}">
    <input placeholder="Phone" value="${esc(phone)}">
    <input placeholder="Email" value="${esc(email)}">
    <button class="btn rm">✕</button>`;
  div.querySelector(".rm").addEventListener("click", () => div.remove());
  return div;
}
function printContacts() {
  const rows = [...document.querySelectorAll("#contact-rows .contact-row")].map(r => {
    const [n, p, e] = [...r.querySelectorAll("input")].map(i => i.value.trim());
    return { n, p, e };
  }).filter(c => c.n || c.p || c.e);
  if (!rows.length) { alert("Add at least one contact."); return; }
  const trs = rows.map(c =>
    `<tr><td>${esc(c.n)}</td><td>${esc(c.p)}</td><td>${esc(c.e)}</td></tr>`).join("");
  doPrint(`<div class="sheet"><h1>Contacts</h1>
    <table class="contacts"><tr><th>Name</th><th>Phone</th><th>Email</th></tr>${trs}</table></div>`, "sheet");
}

/* ---------- wire up ---------- */
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".tab").forEach(t =>
    t.addEventListener("click", () => { navStack = [t.dataset.view]; showView(t.dataset.view, false); }));
  document.querySelectorAll("[data-back]").forEach(b =>
    b.addEventListener("click", goBack));

  $("#search").addEventListener("input", renderLibrary);
  $("#view-toggle").addEventListener("click", () => {
    listMode = listMode === "grid" ? "list" : "grid";
    renderLibrary();
  });
  $("#upload-btn").addEventListener("click", () => $("#file-input").click());
  $("#file-input").addEventListener("change", e => {
    handleFiles([...e.target.files]);
    e.target.value = "";
  });

  $("#viewer-print").addEventListener("click", () => printDoc(currentDocId));
  $("#viewer-edit").addEventListener("click", () => {
    const d = getDoc(currentDocId);
    if (d) PhotoEditor.open(d.dataUrl, currentDocId);
  });
  $("#viewer-delete").addEventListener("click", () => {
    if (confirm("Delete this document?")) {
      deleteDoc(currentDocId);
      goBack();
    }
  });

  $("#camera-start").addEventListener("click", startCamera);
  $("#camera-stop").addEventListener("click", stopCamera);
  $("#camera-capture").addEventListener("click", capturePhoto);
  $("#scan-upload").addEventListener("click", () => $("#file-input").click());

  $("#new-text-btn").addEventListener("click", () => openTextEditor());
  document.querySelectorAll(".fmt-bar .btn").forEach(b =>
    b.addEventListener("click", () => {
      document.execCommand(b.dataset.cmd, false, null);
      $("#text-body").focus();
    }));
  $("#text-save").addEventListener("click", saveTextDoc);
  $("#text-print").addEventListener("click", () => {
    const name = $("#text-title").value.trim() || "Untitled document";
    doPrint(`<div class="sheet"><h1>${esc(name)}</h1><div class="body">${$("#text-body").innerHTML}</div></div>`, "sheet");
  });

  $("#new-contacts-btn").addEventListener("click", () => {
    if (!$("#contact-rows").children.length)
      $("#contact-rows").appendChild(contactRow());
    showView("view-contacts");
  });
  $("#contact-add").addEventListener("click", () =>
    $("#contact-rows").appendChild(contactRow()));
  $("#contacts-print").addEventListener("click", printContacts);

  renderLibrary();
});
