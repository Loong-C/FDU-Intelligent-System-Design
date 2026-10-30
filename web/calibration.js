'use strict';
// Only display scaling/reflection lives here. All projective geometry and hit tests remain in Python.
function calibrationRawPoint(x, y, box, width, height, mirrored) {
  const scale = Math.min(box.width / width, box.height / height);
  const left = box.left + (box.width - width * scale) / 2;
  const top = box.top + (box.height - height * scale) / 2;
  const px = (x - left) / scale, py = (y - top) / scale;
  if (px < 0 || py < 0 || px > width - 1 || py > height - 1) return null;
  return [mirrored ? width - 1 - px : px, py];
}
if (typeof module !== 'undefined') module.exports = {calibrationRawPoint};

if (typeof document !== 'undefined') {
  const el = id => document.getElementById(id);
  const dialog = el('calibrationDialog'), canvas = el('calibrationCanvas');
  let session = null, points = [], frozenImage = null, previewImage = null, previewToken = null, busy = false;
  async function request(action, data = {}) {
    const r = await fetch('/api/calibration/' + action, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
    if (!r.ok) throw Error(await r.text());
    return r.json();
  }
  function draw() {
    const g = canvas.getContext('2d');
    g.clearRect(0, 0, canvas.width, canvas.height);
    if (frozenImage) g.drawImage(previewImage || frozenImage, 0, 0);
    if (session) points.forEach((p, i) => {
      const x = session.mirrored ? canvas.width - 1 - p[0] : p[0];
      g.fillStyle = '#e85d34'; g.beginPath(); g.arc(x, p[1], 6, 0, 2*Math.PI); g.fill();
      g.font = 'bold 20px sans-serif'; g.fillText(String(i+1), x+10, p[1]-8);
    });
    el('calibrationUndo').disabled = busy || !points.length;
    el('calibrationReset').disabled = busy || !points.length;
    el('calibrationPreview').disabled = busy || points.length !== 4;
    el('calibrationSave').disabled = busy || !previewToken;
    el('calibrationCapture').disabled = busy;
    el('calibrationCancel').disabled = busy;
    el('boardName').disabled = busy;
    el('calibrationCount').textContent = session ? `已选 ${points.length}/4 · 冻结帧 F${session.frame_id} · IDs ${session.visible_ids.join(', ')}` : '请先捕获一帧';
  }
  function changed() {previewToken = previewImage = null; draw();}
  async function loadImage(base64) {
    const image = new Image(); image.src = 'data:image/jpeg;base64,' + base64; await image.decode(); return image;
  }
  async function work(fn) {
    if (busy) return;
    busy = true; el('calibrationError').textContent = ''; draw();
    try {await fn();} catch (e) {el('calibrationError').textContent = e.message;}
    finally {busy = false; draw();}
  }
  el('calibrate').onclick = () => {dialog.showModal(); draw();};
  el('calibrationCapture').onclick = () => work(async () => {
    session = await request('capture'); points = []; previewToken = previewImage = null;
    canvas.width = session.frame_width; canvas.height = session.frame_height;
    frozenImage = await loadImage(session.image_base64);
  });
  canvas.onclick = event => {
    if (busy || !session || !frozenImage || points.length >= 4) return;
    const point = calibrationRawPoint(event.clientX, event.clientY, canvas.getBoundingClientRect(), canvas.width, canvas.height, session.mirrored);
    if (point) {points.push(point); changed();}
  };
  el('calibrationUndo').onclick = () => {points.pop(); changed();};
  el('calibrationReset').onclick = () => {points = []; changed();};
  el('boardName').oninput = changed;
  el('calibrationPreview').onclick = () => work(async () => {
    previewToken = null;
    const data = await request('preview', {session_id:session.session_id, points_raw:points, board_id:el('boardName').value});
    previewImage = await loadImage(data.image_base64); previewToken = data.preview_token;
    el('calibrationError').textContent = '预览有效：请检查演奏区域，再确认保存。';
  });
  el('calibrationSave').onclick = () => work(async () => {
    const data = await request('save', {session_id:session.session_id, preview_token:previewToken});
    session = null; points = []; frozenImage = previewImage = previewToken = null;
    dialog.close(); el('error').textContent = `已保存并启用 ${data.saved}。重启时使用 --board ${data.saved}`;
  });
  async function cancel() {
    if (session) {
      try {await request('cancel', {session_id:session.session_id});}
      catch (e) {el('error').textContent = e.message;}
    }
    session = null; points = []; frozenImage = previewImage = previewToken = null; dialog.close();
  }
  el('calibrationCancel').onclick = () => work(cancel);
  dialog.addEventListener('cancel', event => {event.preventDefault(); if (!busy) work(cancel);});
}
