# Structured Session Trace Report

- Session ID: `8929a39a-0328-48fb-85a4-b1041e5652ca`
- Started At: `2026-05-23T09:18:45.315+05:30`
- Events: `18`
- Trace JSONL: `D:\Balaastra\hackothon\project code\backend\data\logs\session_traces\8929a39a-0328-48fb-85a4-b1041e5652ca\trace.jsonl`
- Artifacts: `D:\Balaastra\hackothon\project code\backend\data\logs\session_traces\8929a39a-0328-48fb-85a4-b1041e5652ca\artifacts`

## Event Timeline

### 0001 | +20 ms | session.websocket_connected

- Summary: WebSocket connection accepted for session
- Event ID: `evt_00001`
- Wall Time: `2026-05-23T09:18:45.337+05:30`
- Data:
  - requested_session_id: `None`
  - restored: `False`
  - state: `IDLE`

### 0002 | +360 ms | frontend.connection_established_received

- Summary: Overlay received websocket connection acknowledgement
- Event ID: `evt_00002`
- Wall Time: `2026-05-23T09:18:45.678+05:30`
- Data:
  - surface: `overlay`
  - detail: `{"session_id": "8929a39a-0328-48fb-85a4-b1041e5652ca", "restored": false, "trace_report_path": "D:\\Balaastra\\hackothon\\project code\\backend\\data\\logs\\session_traces\\8929a39a-0328-48fb-85a4-b1041e5652ca\\report...`

### 0003 | +908 ms | frontend.meeting_capture_requested

- Summary: Overlay started meeting capture setup
- Event ID: `evt_00003`
- Wall Time: `2026-05-23T09:18:46.225+05:30`
- Data:
  - surface: `overlay`
  - detail: `{"source_id": "window:11277002:0", "selected_target": "AI Agents: Long Tasks Explained - Google Gemini - Brave"}`

### 0004 | +3436 ms | frontend.privacy_consent_sent

- Summary: Overlay sent privacy consent before starting session
- Event ID: `evt_00004`
- Wall Time: `2026-05-23T09:18:48.753+05:30`
- Data:
  - surface: `overlay`
  - detail: `{"version": "1.0", "mode": "live"}`

### 0005 | +3444 ms | ws.message_received

- Summary: Backend received websocket message PRIVACY_CONSENT_GRANTED
- Event ID: `evt_00005`
- Wall Time: `2026-05-23T09:18:48.761+05:30`
- Data:
  - message_type: `PRIVACY_CONSENT_GRANTED`
  - payload: `{"version": "1.0", "mode": "live"}`

### 0006 | +3454 ms | session.privacy_consent_granted

- Summary: Privacy consent received from client
- Event ID: `evt_00006`
- Wall Time: `2026-05-23T09:18:48.770+05:30`
- Data:
  - version: `1.0`
  - mode: `live`

### 0007 | +3682 ms | frontend.start_negotiation_sent

- Summary: Overlay sent START_NEGOTIATION
- Event ID: `evt_00007`
- Wall Time: `2026-05-23T09:18:48.998+05:30`
- Data:
  - surface: `overlay`
  - detail: `{"meeting_title": "AI Agents: Long Tasks Explained - Google Gemini - Brave", "source_mode": "virtual_companion_desktop"}`

### 0008 | +3694 ms | ws.message_received

- Summary: Backend received websocket message START_NEGOTIATION
- Event ID: `evt_00008`
- Wall Time: `2026-05-23T09:18:49.011+05:30`
- Data:
  - message_type: `START_NEGOTIATION`
  - payload: `{"context": "Desktop companion virtual meeting session", "source_mode": "virtual_companion_desktop", "capture_preset": "meeting_window_default", "companion_quality_mode": "companion_ready", "meeting_binding": {"target...`

### 0009 | +3745 ms | session.session_start_requested

- Summary: Backend accepted START_NEGOTIATION and initialized the session runtime
- Event ID: `evt_00009`
- Wall Time: `2026-05-23T09:18:49.062+05:30`
- Data:
  - source_mode: `virtual_companion_desktop`
  - meeting_binding: `{"target_id": "window:11277002:0", "window_title": "AI Agents: Long Tasks Explained - Google Gemini - Brave", "process_name": null, "platform_hint": "generic", "output_device_id": "default", "output_device_label": "De...`
  - selected_output_device: `{"device_id": "communications", "label": "Communications - ZEB-EA320 (Intel(R) Display Audio)"}`
  - context: `Desktop companion virtual meeting session`
  - user_context: `{}`

### 0010 | +14747 ms | ai.gemini_live_connected

- Summary: Gemini Live session connected
- Event ID: `evt_00010`
- Wall Time: `2026-05-23T09:19:00.065+05:30`
- Data:
  - attempt: `1`
  - model: `gemini-live-2.5-flash-native-audio`

### 0011 | +14818 ms | frontend.session_started_received

- Summary: Overlay received SESSION_STARTED
- Event ID: `evt_00011`
- Wall Time: `2026-05-23T09:19:00.135+05:30`
- Data:
  - surface: `overlay`
  - detail: `{"meeting_title": "AI Agents: Long Tasks Explained - Google Gemini - Brave"}`

### 0012 | +14822 ms | ws.message_received

- Summary: Backend received websocket message MEETING_BINDING
- Event ID: `evt_00012`
- Wall Time: `2026-05-23T09:19:00.139+05:30`
- Data:
  - message_type: `MEETING_BINDING`
  - payload: `{"target_id": "window:11277002:0", "window_title": "AI Agents: Long Tasks Explained - Google Gemini - Brave", "platform_hint": "generic", "output_device_id": "default", "output_device_label": "Default - CABLE Input (V...`

### 0013 | +14996 ms | frontend.meeting_binding_updated

- Summary: Meeting binding updated on backend
- Event ID: `evt_00013`
- Wall Time: `2026-05-23T09:19:00.313+05:30`
- Data:
  - binding: `{"target_id": "window:11277002:0", "window_title": "AI Agents: Long Tasks Explained - Google Gemini - Brave", "process_name": null, "platform_hint": "generic", "output_device_id": "default", "output_device_label": "De...`
  - source_mode: `virtual_companion_desktop`

### 0014 | +14998 ms | ws.message_received

- Summary: Backend received websocket message CAPTURE_HEALTH
- Event ID: `evt_00014`
- Wall Time: `2026-05-23T09:19:00.316+05:30`
- Data:
  - message_type: `CAPTURE_HEALTH`
  - payload: `{"mic_forward_ok": true, "remote_audio_ok": false, "frame_capture_ok": false, "reply_output_ok": true, "helper_active": true, "process_loopback_ok": false}`

### 0015 | +15063 ms | frontend.capture_health_updated

- Summary: Capture health updated on backend
- Event ID: `evt_00015`
- Wall Time: `2026-05-23T09:19:00.380+05:30`
- Data:
  - health: `{"mic_forward_ok": true, "remote_audio_ok": false, "frame_capture_ok": false, "reply_output_ok": true, "helper_active": true, "process_loopback_ok": false, "unsafe_device_loopback": false, "degraded_reasons": []}`
  - degraded_mode: `source_missing`

### 0016 | +75396 ms | session.websocket_disconnect

- Summary: Client websocket disconnected
- Event ID: `evt_00016`
- Wall Time: `2026-05-23T09:20:00.714+05:30`
- Data:
  - state: `ACTIVE`

### 0017 | +75412 ms | session.websocket_cleanup

- Summary: WebSocket cleanup started
- Event ID: `evt_00017`
- Wall Time: `2026-05-23T09:20:00.729+05:30`
- Data:
  - state: `ACTIVE`

### 0018 | +75911 ms | session.session_finalized

- Summary: Session cleanup finalized and report generation starting
- Event ID: `evt_00018`
- Wall Time: `2026-05-23T09:20:01.228+05:30`
- Data:
  - state: `ACTIVE`
  - metrics: `{"stt_requests": 1, "stt_successes": 0, "stt_empty_results": 1, "stt_retry_count": 0, "speaker_user_count": 0, "speaker_counterparty_count": 0, "speaker_unknown_count": 0, "avg_utterance_duration_ms": 0.0, "utterance_...`

