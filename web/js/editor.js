/* Print Studio — canvas photo editor: rotate, flip, filters, adjustments, crop, text. */
"use strict";

const PhotoEditor = (() => {
  const canvas = () => document.getElementById("editor-canvas");
  let img = null;          // source Image
  let saveId = null;       // library doc id to overwrite (or null = new)
  let cropMode = false;
  let cropRect = null;     // {x,y,w,h} in displayed px
  let dragStart = null;

  const state = {
    rotation: 0,           // 0..3 quarter turns
    flipH: false,
    filter: "none",
    bright: 100, contrast: 100, sat: 100,
    texts: [],             // {text, size, color, pos: 'top'|'center'|'bottom'}
  };
  function resetState() {
    Object.assign(state, { rotation: 0, flipH: false, filter: "none",
      bright: 100, contrast: 100, sat: 100, texts: [] });
    cropRect = null; cropMode = false;
    document.getElementById("ed-crop-apply").classList.add("hidden");
    for (const [id, val] of [["ed-bright", 100], ["ed-contrast", 100], ["ed-sat", 100]])
      document.getElementById(id).value = val;
    document.getElementById("ed-filter").value = "none";
  }

  function open(dataUrl, docId = null) {
    saveId = docId;
    resetState();
    img = new Image();
    img.onload = () => { render(); showView("view-editor"); };
    img.src = dataUrl;
  }

  function filterString() {
    const f = [];
    if (state.filter === "grayscale") f.push("grayscale(1)");
    if (state.filter === "sepia") f.push("sepia(1)");
    if (state.filter === "invert") f.push("invert(1)");
    f.push(`brightness(${state.bright}%)`);
    f.push(`contrast(${state.contrast}%)`);
    f.push(`saturate(${state.sat}%)`);
    return f.join(" ");
  }

  function render() {
    if (!img) return;
    const c = canvas(), ctx = c.getContext("2d");
    const swap = state.rotation % 2 === 1;
    const iw = img.naturalWidth, ih = img.naturalHeight;
    // fit within ~720px for editing
    const fit = Math.min(1, 720 / Math.max(iw, ih));
    const dw = Math.round((swap ? ih : iw) * fit);
    const dh = Math.round((swap ? iw : ih) * fit);
    c.width = dw; c.height = dh;
    ctx.save();
    ctx.filter = filterString();
    ctx.translate(dw / 2, dh / 2);
    ctx.rotate(state.rotation * Math.PI / 2);
    ctx.scale(state.flipH ? -1 : 1, 1);
    const rw = swap ? dh : dw, rh = swap ? dw : dh;
    ctx.drawImage(img, -rw / 2, -rh / 2, rw, rh);
    ctx.restore();
    // crop overlay
    if (cropRect) {
      ctx.save();
      ctx.strokeStyle = "#0a84ff"; ctx.lineWidth = 2;
      ctx.setLineDash([6, 4]);
      ctx.strokeRect(cropRect.x, cropRect.y, cropRect.w, cropRect.h);
      ctx.fillStyle = "rgba(10,132,255,.15)";
      ctx.fillRect(cropRect.x, cropRect.y, cropRect.w, cropRect.h);
      ctx.restore();
    }
    // text overlays
    for (const t of state.texts) {
      ctx.save();
      ctx.font = `bold ${Math.round(dh * t.size / 100)}px sans-serif`;
      ctx.textAlign = "center";
      ctx.fillStyle = t.color;
      ctx.strokeStyle = "rgba(0,0,0,.4)"; ctx.lineWidth = 2;
      const y = t.pos === "top" ? dh * 0.12 : t.pos === "bottom" ? dh * 0.9 : dh * 0.52;
      ctx.strokeText(t.text, dw / 2, y);
      ctx.fillText(t.text, dw / 2, y);
      ctx.restore();
    }
  }

  function applyCrop() {
    if (!cropRect || !img) return;
    const c = canvas();
    const sx = img.naturalWidth / c.width, sy = img.naturalHeight / c.height;
    // account for current rotation by rendering first, then cropping the render
    const tmp = document.createElement("canvas");
    tmp.width = c.width; tmp.height = c.height;
    tmp.getContext("2d").drawImage(c, 0, 0);
    const out = document.createElement("canvas");
    out.width = Math.round(cropRect.w); out.height = Math.round(cropRect.h);
    out.getContext("2d").drawImage(tmp, cropRect.x, cropRect.y, cropRect.w, cropRect.h, 0, 0, out.width, out.height);
    const kept = { rotation: 0, flipH: false };
    img = new Image();
    img.onload = () => {
      Object.assign(state, kept);
      cropRect = null; cropMode = false;
      document.getElementById("ed-crop-apply").classList.add("hidden");
      render();
    };
    img.src = out.toDataURL("image/jpeg", 0.92);
  }

  function save() {
    if (!img) return;
    const dataUrl = canvas().toDataURL("image/jpeg", 0.9);
    if (saveId && typeof updateDoc === "function") {
      updateDoc(saveId, { dataUrl, size: Math.round(dataUrl.length * 0.75) });
    } else if (typeof addDoc === "function") {
      addDoc({ name: "Edited photo", type: "image", dataUrl,
               size: Math.round(dataUrl.length * 0.75) });
    }
    showView("view-library");
  }

  function canvasPos(e) {
    const r = canvas().getBoundingClientRect();
    const p = e.touches ? e.touches[0] : e;
    return { x: (p.clientX - r.left) * (canvas().width / r.width),
             y: (p.clientY - r.top) * (canvas().height / r.height) };
  }

  function wire() {
    document.getElementById("ed-rotate").addEventListener("click", () => {
      state.rotation = (state.rotation + 1) % 4; render();
    });
    document.getElementById("ed-flip").addEventListener("click", () => {
      state.flipH = !state.flipH; render();
    });
    document.getElementById("ed-filter").addEventListener("change", e => {
      state.filter = e.target.value; render();
    });
    for (const [id, key] of [["ed-bright", "bright"], ["ed-contrast", "contrast"], ["ed-sat", "sat"]])
      document.getElementById(id).addEventListener("input", e => {
        state[key] = +e.target.value; render();
      });
    document.getElementById("ed-crop").addEventListener("click", () => {
      cropMode = !cropMode; cropRect = null;
      document.getElementById("ed-crop-apply").classList.toggle("hidden", !cropMode);
      document.getElementById("ed-crop").textContent = cropMode ? "Cancel crop" : "Crop";
      render();
    });
    document.getElementById("ed-crop-apply").addEventListener("click", applyCrop);
    document.getElementById("ed-text-add").addEventListener("click", () => {
      const input = document.getElementById("ed-text-input");
      const text = input.value.trim();
      if (!text) return;
      const pos = state.texts.length % 3 === 0 ? "bottom" : state.texts.length % 3 === 1 ? "top" : "center";
      state.texts.push({ text, size: 7, color: "#ffffff", pos });
      input.value = "";
      render();
    });
    document.getElementById("editor-save").addEventListener("click", save);

    const c = () => canvas();
    const start = e => { if (!cropMode) return; dragStart = canvasPos(e); cropRect = null; e.preventDefault(); };
    const move = e => {
      if (!cropMode || !dragStart) return;
      const p = canvasPos(e);
      cropRect = { x: Math.min(dragStart.x, p.x), y: Math.min(dragStart.y, p.y),
                   w: Math.abs(p.x - dragStart.x), h: Math.abs(p.y - dragStart.y) };
      render(); e.preventDefault();
    };
    const end = () => { dragStart = null; };
    document.addEventListener("DOMContentLoaded", () => {
      const cv = document.getElementById("editor-canvas");
      cv.addEventListener("pointerdown", start);
      cv.addEventListener("pointermove", move);
      window.addEventListener("pointerup", end);
    });
  }

  // wire immediately if DOM already loaded (script order), else on DOMContentLoaded
  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", wire);
  else wire();

  return { open };
})();
