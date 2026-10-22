'use strict';
const $ = id => document.getElementById(id);
let latest = null, stopped = false, updating = false;
const fmt = (n, digits = 1) => Number.isFinite(n) ? n.toFixed(digits) : '—';
const escapeText = text => String(text).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function clearLive(message) {
  latest = null;
  $('status').textContent = message;
  $('video').removeAttribute('src');
  $('waiting').hidden = false;
  $('waitMessage').textContent = message;
  $('chord').textContent = '—';
  $('chordState').textContent = '当前数据不可用';
  $('hands').textContent = '无新鲜手部数据';
  $('nodes').replaceChildren();
  $('world').getContext('2d').clearRect(0, 0, 800, 300);
  $('fps').textContent = '—';
  $('event').textContent = '—';
  $('boardState').textContent = 'UNAVAILABLE';
  $('audioState').textContent = '状态不可用';
  $('audioDetail').textContent = '等待新的服务状态';
  $('eventDetail').textContent = '历史事件见下方记录';
  $('selectHand').replaceChildren();
  $('record').disabled = true;
  for (const id of ['latency', 'arucoMs', 'totalMs']) $(id).textContent = '—';
  $('chordStrip').querySelectorAll('.active').forEach(node => node.classList.remove('active'));
}

function drawWorld(data) {
  const g = $('world').getContext('2d');
  g.clearRect(0, 0, 800, 300);
  g.font = '14px monospace'; g.fillStyle = '#a8b5ab';
  g.fillText('XY / LOCAL', 20, 25); g.fillText('XZ / LOCAL', 420, 25);
  for (const hand of data.hands) {
    g.strokeStyle = g.fillStyle = hand.handedness === 'Left' ? '#58d6b0' : '#f3ae4e';
    const offset = hand.handedness === 'Left' ? -65 : 65;
    for (let view = 0; view < 2; view++) {
      const pts = hand.landmarks_world_m.map(p => [200 + 400*view + offset + p[0]*1100, 165 + p[view === 0 ? 1 : 2]*1100]);
      g.lineWidth = 2;
      for (const [a, b] of data.connections) {g.beginPath(); g.moveTo(...pts[a]); g.lineTo(...pts[b]); g.stroke();}
      for (const p of pts) {g.beginPath(); g.arc(...p, 3, 0, Math.PI*2); g.fill();}
    }
  }
}

function renderTable() {
  if (!latest) return;
  const hand = latest.hands.find(h => String(h.track_id) === $('selectHand').value) || latest.hands[0];
  $('nodes').innerHTML = hand ? hand.landmarks_px.map((p, i) => {
    const uv = hand.landmarks_instrument_uv?.[i];
    const values = [fmt(p[0]), fmt(p[1]), fmt(p[2]), fmt(hand.landmarks_normalized[i][0], 4), fmt(hand.landmarks_normalized[i][1], 4), fmt(uv?.[0], 4), fmt(uv?.[1], 4)];
    return '<tr><td>'+i+'</td><td>'+escapeText(latest.landmark_names[i])+'</td>'+values.map(v=>'<td>'+v+'</td>').join('')+'</tr>';
  }).join('') : '<tr><td colspan="9">当前无手部节点</td></tr>';
}

function render(data) {
  latest = data;
  const board = data.instrument || {}, interaction = data.interaction || {}, audio = data.audio || {};
  const running = data.status === 'running';
  $('status').textContent = running ? '● 本地服务运行中' : data.status === 'error' ? '服务错误' : data.status === 'stopped' ? '服务已停止' : '启动中';
  $('cameraName').textContent = data.camera_name || '等待摄像头';
  $('simulation').hidden = data.source !== 'synthetic';
  $('fps').textContent = data.fps ?? '—';
  $('latency').textContent = fmt(data.inference_ms);
  $('arucoMs').textContent = fmt(board.aruco_ms);
  $('totalMs').textContent = fmt(data.vision_total_ms);
  $('chord').textContent = interaction.current_chord || '—';
  $('chordState').textContent = interaction.chord_valid ? '左手选择有效' : interaction.current_chord ? '上次选择 · 当前不可发声' : interaction.candidate_chord ? '候选 '+interaction.candidate_chord+' · 请稍作停留' : '等待左手选择';
  $('boardState').textContent = ({valid:'VALID · 已定位', held:'HELD · 暂停演奏', lost:'LOST · 等待标记'})[board.status] || '等待定位';
  $('markerState').textContent = (board.visible_ids || []).filter(i=>[0,1,2,3].includes(i)).length+' / 4 MARKERS'+(board.homography_age_s ? ' · '+fmt(board.homography_age_s, 2)+' s' : '');
  $('audioState').textContent = ({ready:'输出流就绪', mock:'MOCK · 无实际声音', disabled:'已关闭', error:'ERROR · 输出不可用', closed:'已关闭'})[data.audio_status] || '初始化中';
  $('audioDetail').textContent = audio.error || (audio.backend || '—')+' · 已消费 '+(audio.played_events || 0)+' · 队列 '+(audio.queue_depth || 0)+' · 丢弃 '+(audio.dropped_events || 0);
  const recent = data.recent_events || [], event = recent.at(-1);
  $('event').textContent = event ? (event.direction === 'down' ? '↓ 下扫' : '↑ 上扫')+' · '+event.chord : '—';
  $('eventDetail').textContent = event ? '#'+event.event_id+' · velocity '+event.velocity+' · frame '+event.source_frame_id : '等待新事件';
  $('events').innerHTML = recent.length ? recent.slice(-6).reverse().map(e=>'<li><span>#'+e.event_id+' '+(e.direction === 'down' ? '↓' : '↑')+' '+escapeText(e.chord)+'</span><span>VEL '+e.velocity+' / F'+e.source_frame_id+'</span></li>').join('') : '<li>尚无扫弦事件</li>';
  const chords = Object.keys(data.layout?.chords || {});
  $('chordStrip').innerHTML = chords.map((name, i)=>'<div class="chord-chip '+(interaction.chord_valid && name === interaction.current_chord ? 'active' : '')+'">'+escapeText(name)+'<small>0'+(i+1)+'</small></div>').join('');
  $('hands').textContent = data.hands.map(h=>(h.handedness === 'Left' ? '左手 / 和弦' : '右手 / 扫弦')+' #'+h.track_id+' · '+fmt(h.confidence*100, 0)+'%').join('　') || '等待双手进入画面';
  $('error').textContent = [data.error, audio.error, data.recording_error].filter(Boolean).join(' · ');
  $('record').textContent = data.recording ? '停止录制' : '开始录制';
  $('record').disabled = !running && !data.recording;
  $('recording').textContent = data.recording ? '● 正在录制：'+data.last_recording : data.last_recording ? '已保存：'+data.last_recording : '录制节点、板面和事件；不保存视频。';
  $('frameInfo').textContent = 'F'+(data.frame_id || 0)+' · '+(data.frame_width || 0)+'×'+(data.frame_height || 0)+' · '+(data.mirrored ? '镜像' : '原始');
  const old = $('selectHand').value;
  const options = data.hands.map(h=>'<option value="'+h.track_id+'">'+h.handedness+' #'+h.track_id+'</option>').join('');
  if ($('selectHand').innerHTML !== options) $('selectHand').innerHTML = options;
  if (data.hands.some(h=>String(h.track_id) === old)) $('selectHand').value = old;
  if ($('debug').open) {renderTable(); drawWorld(data);}
}

async function update() {
  if (stopped || updating) return;
  updating = true;
  try {
    const response = await fetch('/api/snapshot', {signal:AbortSignal.timeout(3000)});
    if (!response.ok) throw Error('HTTP '+response.status);
    const {packet, image_base64:image} = await response.json();
    if (packet.status === 'running' && Date.now()/1000-packet.timestamp_unix_s > 1) throw Error('画面已过期');
    if (image && packet.status === 'running') {
      // One response carries one immutable packet/JPEG pair. No JS geometry or inference.
      const next = new Image();
      next.src = 'data:image/jpeg;base64,'+image;
      await next.decode();
      if (stopped) return;
      $('video').src = next.src;
      $('waiting').hidden = true;
      render(packet);
    } else {
      render(packet);
      clearLive(packet.error || (packet.status === 'stopped' ? '服务已停止，可重新运行启动脚本。' : '摄像头启动中…'));
    }
  } catch (error) {
    if (!stopped) {clearLive('本地服务未连接或画面已过期'); $('error').textContent = error.message;}
  } finally {
    updating = false;
    if (!stopped) setTimeout(update, 80);
  }
}

$('selectHand').onchange = renderTable;
$('debug').ontoggle = () => {if (latest && $('debug').open) {renderTable(); drawWorld(latest);}};
$('record').onclick = async () => {
  try {
    $('record').disabled = true;
    const r = await fetch('/api/record/'+(latest?.recording ? 'stop' : 'start'), {method:'POST'});
    if (!r.ok) throw Error(await r.text());
    render(await r.json());
  } catch (e) {$('error').textContent = e.message; $('record').disabled = false;}
};
$('stop').onclick = async () => {
  try {
    const r = await fetch('/api/shutdown', {method:'POST'});
    if (!r.ok) throw Error(await r.text());
    stopped = true; clearLive('服务已停止，可重新运行启动脚本。');
    $('record').disabled = $('stop').disabled = true;
    $('audioState').textContent = '已停止';
  } catch (e) {$('error').textContent = e.message;}
};
update();
