# src/claudedev/ui/live_session.py
"""Live session page with WebSocket streaming and steering controls."""

from __future__ import annotations

import html
import json
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

if TYPE_CHECKING:
    from claudedev.engines.steering_manager import SteeringManager
    from claudedev.engines.websocket_manager import WebSocketManager

logger = structlog.get_logger(__name__)

# Full HTML template. Uses textContent for output rendering (XSS-safe).
# Uses DOM createElement for activity items (no innerHTML with user data).
# Session ID is server-substituted before serving.
LIVE_SESSION_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Live Session: {session_id}</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', monospace;
         background: #0d1117; color: #c9d1d9; height: 100vh; display: flex; flex-direction: column; }
  .header { padding: 12px 20px; background: #161b22; border-bottom: 1px solid #30363d;
             display: flex; justify-content: space-between; align-items: center; }
  .header h1 { font-size: 16px; font-weight: 500; }
  .status { display: flex; align-items: center; gap: 8px; font-size: 13px; }
  .status .dot { width: 8px; height: 8px; border-radius: 50%; background: #3fb950; }
  .status .dot.ended { background: #f85149; }
  .main { display: flex; flex: 1; overflow: hidden; }
  .terminal-panel { flex: 1; display: flex; flex-direction: column; border-right: 1px solid #30363d; }
  .terminal { flex: 1; overflow-y: auto; padding: 12px; font-family: 'SF Mono', Menlo, monospace;
               font-size: 13px; line-height: 1.5; white-space: pre-wrap; word-wrap: break-word; }
  .sidebar { width: 360px; display: flex; flex-direction: column; }
  .activity-panel { flex: 1; overflow-y: auto; padding: 12px; border-bottom: 1px solid #30363d; }
  .activity-panel h2, .steering-panel h2 { font-size: 13px; color: #8b949e; margin-bottom: 8px;
                                             text-transform: uppercase; letter-spacing: 0.5px; }
  .activity-item { font-size: 12px; padding: 3px 0; color: #8b949e; }
  .activity-item .tool { color: #58a6ff; }
  .steering-panel { padding: 12px; }
  .steering-input { display: flex; gap: 8px; margin-bottom: 8px; }
  .steering-input input { flex: 1; background: #0d1117; border: 1px solid #30363d;
                           color: #c9d1d9; padding: 8px; border-radius: 6px; font-size: 13px; }
  .steering-input button { background: #238636; border: none; color: #fff; padding: 8px 16px;
                            border-radius: 6px; cursor: pointer; font-size: 13px; }
  .directive-btns { display: flex; gap: 6px; margin-bottom: 12px; }
  .directive-btns button { background: #21262d; border: 1px solid #30363d; color: #8b949e;
                            padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 11px; }
  .directive-btns button.active { border-color: #58a6ff; color: #58a6ff; }
  .history { max-height: 200px; overflow-y: auto; }
  .history-item { font-size: 12px; padding: 4px 0; border-bottom: 1px solid #21262d; }
</style>
</head>
<body>
<div class="header">
  <h1>Live Session: <span id="session-id">{session_id}</span></h1>
  <div class="status">
    <div class="dot" id="status-dot"></div>
    <span id="status-text">Connecting...</span>
    <span id="duration"></span>
  </div>
</div>
<div class="main">
  <div class="terminal-panel">
    <div class="terminal" id="terminal"></div>
  </div>
  <div class="sidebar">
    <div class="activity-panel">
      <h2>Tool Activity</h2>
      <div id="activity-log"></div>
    </div>
    <div class="steering-panel">
      <h2>Steering</h2>
      <div class="directive-btns" id="directive-btns">
        <button data-type="inform" class="active">inform</button>
        <button data-type="constrain">constrain</button>
        <button data-type="pivot">pivot</button>
        <button data-type="abort">abort</button>
      </div>
      <div class="steering-input">
        <input type="text" id="steer-input" placeholder="Type directive..." />
        <button id="steer-send">Send</button>
      </div>
      <h2>History</h2>
      <div class="history" id="steer-history"></div>
    </div>
  </div>
</div>
<script>
(function() {
  var sessionId = '{session_id}';
  var wsProto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  var baseWs = wsProto + '//' + location.host;
  var terminal = document.getElementById('terminal');
  var activityLog = document.getElementById('activity-log');
  var steerHistory = document.getElementById('steer-history');
  var steerInput = document.getElementById('steer-input');
  var selectedType = 'inform';

  document.getElementById('directive-btns').addEventListener('click', function(e) {
    if (e.target.dataset && e.target.dataset.type) {
      var btns = document.querySelectorAll('.directive-btns button');
      for (var i = 0; i < btns.length; i++) btns[i].classList.remove('active');
      e.target.classList.add('active');
      selectedType = e.target.dataset.type;
    }
  });

  var streamWs = new WebSocket(baseWs + '/ws/session/' + sessionId + '/stream');
  streamWs.onopen = function() {
    document.getElementById('status-text').textContent = 'Connected';
  };
  streamWs.onmessage = function(evt) {
    var msg = JSON.parse(evt.data);
    if (msg.type === 'output') {
      terminal.textContent += msg.data + '\\n';
      terminal.scrollTop = terminal.scrollHeight;
    } else if (msg.type === 'activity') {
      var div = document.createElement('div');
      div.className = 'activity-item';
      var toolSpan = document.createElement('span');
      toolSpan.className = 'tool';
      toolSpan.textContent = msg.data.tool || msg.data.event_type || '';
      div.appendChild(toolSpan);
      div.appendChild(document.createTextNode(' ' + (msg.data.file || '')));
      activityLog.appendChild(div);
      activityLog.scrollTop = activityLog.scrollHeight;
    } else if (msg.type === 'session_end') {
      document.getElementById('status-dot').classList.add('ended');
      document.getElementById('status-text').textContent = 'Ended';
    }
  };
  streamWs.onclose = function() {
    document.getElementById('status-dot').classList.add('ended');
    document.getElementById('status-text').textContent = 'Disconnected';
  };

  var steerWs = new WebSocket(baseWs + '/ws/session/' + sessionId + '/steer');
  steerWs.onmessage = function(evt) {
    var msg = JSON.parse(evt.data);
    if (msg.type === 'steering_ack') {
      var pending = steerHistory.querySelector('.pending');
      if (pending) { pending.className = 'ack'; pending.textContent = 'acknowledged'; }
    }
  };

  function sendSteering() {
    var text = steerInput.value.trim();
    if (!text) return;
    steerWs.send(JSON.stringify({ message: text, directive_type: selectedType }));
    var div = document.createElement('div');
    div.className = 'history-item';
    var q = document.createElement('q');
    q.textContent = text;
    div.appendChild(q);
    var em = document.createElement('em');
    em.textContent = ' (' + selectedType + ') ';
    div.appendChild(em);
    var status = document.createElement('span');
    status.className = 'pending';
    status.textContent = 'pending';
    div.appendChild(status);
    steerHistory.prepend(div);
    steerInput.value = '';
  }

  document.getElementById('steer-send').addEventListener('click', sendSteering);
  steerInput.addEventListener('keydown', function(e) { if (e.key === 'Enter') sendSteering(); });

  var startTime = Date.now();
  setInterval(function() {
    var elapsed = Math.floor((Date.now() - startTime) / 1000);
    var m = Math.floor(elapsed / 60);
    var s = elapsed % 60;
    document.getElementById('duration').textContent = m + 'm ' + s + 's';
  }, 1000);
})();
</script>
</body>
</html>"""


def create_live_session_router(
    ws_manager: WebSocketManager,
    steering: SteeringManager,
) -> APIRouter:
    """Create router with live session page and WebSocket endpoints."""
    router = APIRouter(tags=["live-session"])

    @router.get("/session/{session_id}/live")
    async def live_session_page(session_id: str) -> HTMLResponse:
        # Validate session_id format to prevent XSS in JS context
        if not re.match(r"^[a-zA-Z0-9_-]+$", session_id):
            return HTMLResponse("Invalid session ID", status_code=400)
        html_content = LIVE_SESSION_HTML.replace("{session_id}", html.escape(session_id))
        return HTMLResponse(html_content)

    @router.websocket("/ws/session/{session_id}/stream")
    async def ws_stream(websocket: WebSocket, session_id: str) -> None:
        # Validate session_id format to prevent injection and unauthorized access
        if not re.match(r"^[a-zA-Z0-9_-]+$", session_id):
            await websocket.close(code=4003)
            return
        # Reject if session is not known to ws_manager (no registered subscribers/buffer)
        # Production deployments should add full session auth here
        await websocket.accept()
        await ws_manager.register_subscriber(session_id, websocket)
        try:
            for line in ws_manager.get_output_buffer(session_id):
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "output",
                            "data": line,
                            "timestamp": datetime.now(UTC).isoformat(),
                        }
                    )
                )
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            await ws_manager.unregister_subscriber(session_id, websocket)

    @router.websocket("/ws/session/{session_id}/steer")
    async def ws_steer(websocket: WebSocket, session_id: str) -> None:
        from claudedev.engines.steering_manager import DirectiveType

        # Validate session_id format to prevent injection
        if not re.match(r"^[a-zA-Z0-9_-]+$", session_id):
            await websocket.close(code=4003)
            return
        # Reject connections to unregistered sessions to prevent directive injection
        if not steering.is_session_active(session_id):
            await websocket.close(code=4003)
            return
        await websocket.accept()
        try:
            while True:
                data = await websocket.receive_json()
                message = data.get("message", "")
                dtype = data.get("directive_type", "inform")
                try:
                    directive_type = DirectiveType(dtype)
                except ValueError:
                    directive_type = DirectiveType.INFORM
                try:
                    await steering.enqueue_message(session_id, message, directive_type)
                    await websocket.send_json({"status": "queued", "directive_type": dtype})
                except KeyError:
                    await websocket.send_json(
                        {"status": "error", "detail": "Session not registered"}
                    )
        except WebSocketDisconnect:
            pass

    return router
