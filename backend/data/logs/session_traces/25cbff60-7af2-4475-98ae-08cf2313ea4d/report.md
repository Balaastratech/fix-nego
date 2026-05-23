# Structured Session Trace Report

- Session ID: `25cbff60-7af2-4475-98ae-08cf2313ea4d`
- Started At: `2026-05-23T09:55:27.926+05:30`
- Events: `39`
- Trace JSONL: `D:\Balaastra\hackothon\project code\backend\data\logs\session_traces\25cbff60-7af2-4475-98ae-08cf2313ea4d\trace.jsonl`
- Artifacts: `D:\Balaastra\hackothon\project code\backend\data\logs\session_traces\25cbff60-7af2-4475-98ae-08cf2313ea4d\artifacts`

## Event Timeline

### 0001 | +10 ms | session.websocket_connected

- Summary: WebSocket connection accepted for session
- Event ID: `evt_00001`
- Wall Time: `2026-05-23T09:55:27.937+05:30`
- Data:
  - requested_session_id: `None`
  - restored: `False`
  - state: `IDLE`

### 0002 | +105 ms | frontend.connection_established_received

- Summary: Overlay received websocket connection acknowledgement
- Event ID: `evt_00002`
- Wall Time: `2026-05-23T09:55:28.032+05:30`
- Data:
  - surface: `overlay`
  - detail: `{"session_id": "25cbff60-7af2-4475-98ae-08cf2313ea4d", "restored": false, "trace_report_path": "D:\\Balaastra\\hackothon\\project code\\backend\\data\\logs\\session_traces\\25cbff60-7af2-4475-98ae-08cf2313ea4d\\report...`

### 0003 | +3465 ms | frontend.meeting_capture_requested

- Summary: Overlay started meeting capture setup
- Event ID: `evt_00003`
- Wall Time: `2026-05-23T09:55:31.392+05:30`
- Data:
  - surface: `overlay`
  - detail: `{"source_id": "window:11277002:0", "selected_target": "AI Agents: Long Tasks Explained - Google Gemini - Brave"}`

### 0004 | +6386 ms | frontend.meeting_capture_started

- Summary: Meeting capture started successfully
- Event ID: `evt_00004`
- Wall Time: `2026-05-23T09:55:34.313+05:30`
- Data:
  - surface: `overlay`
  - detail: `{"source_id": "window:11277002:0", "has_audio": true, "video_track_label": "AI Agents: Long Tasks Explained - Google Gemini - Brave", "audio_track_count": 1}`

### 0005 | +9426 ms | frontend.privacy_consent_sent

- Summary: Overlay sent privacy consent before starting session
- Event ID: `evt_00005`
- Wall Time: `2026-05-23T09:55:37.353+05:30`
- Data:
  - surface: `overlay`
  - detail: `{"version": "1.0", "mode": "live"}`

### 0006 | +9462 ms | ws.message_received

- Summary: Backend received websocket message PRIVACY_CONSENT_GRANTED
- Event ID: `evt_00006`
- Wall Time: `2026-05-23T09:55:37.388+05:30`
- Data:
  - message_type: `PRIVACY_CONSENT_GRANTED`
  - payload: `{"version": "1.0", "mode": "live"}`

### 0007 | +9464 ms | session.privacy_consent_granted

- Summary: Privacy consent received from client
- Event ID: `evt_00007`
- Wall Time: `2026-05-23T09:55:37.391+05:30`
- Data:
  - version: `1.0`
  - mode: `live`

### 0008 | +9587 ms | frontend.start_negotiation_sent

- Summary: Overlay sent START_NEGOTIATION
- Event ID: `evt_00008`
- Wall Time: `2026-05-23T09:55:37.514+05:30`
- Data:
  - surface: `overlay`
  - detail: `{"meeting_title": "AI Agents: Long Tasks Explained - Google Gemini - Brave", "source_mode": "virtual_companion_desktop"}`

### 0009 | +9609 ms | ws.message_received

- Summary: Backend received websocket message START_NEGOTIATION
- Event ID: `evt_00009`
- Wall Time: `2026-05-23T09:55:37.536+05:30`
- Data:
  - message_type: `START_NEGOTIATION`
  - payload: `{"context": "Desktop companion virtual meeting session", "source_mode": "virtual_companion_desktop", "capture_preset": "meeting_window_default", "companion_quality_mode": "companion_ready", "meeting_binding": {"target...`

### 0010 | +9662 ms | session.session_start_requested

- Summary: Backend accepted START_NEGOTIATION and initialized the session runtime
- Event ID: `evt_00010`
- Wall Time: `2026-05-23T09:55:37.589+05:30`
- Data:
  - source_mode: `virtual_companion_desktop`
  - meeting_binding: `{"target_id": "window:11277002:0", "window_title": "AI Agents: Long Tasks Explained - Google Gemini - Brave", "process_name": null, "platform_hint": "generic", "output_device_id": "90c42ab7e82ca84a06b4a1c8be2a893fd854...`
  - selected_output_device: `{"device_id": "communications", "label": "Communications - Headphones (OnePlus Buds Pro 2) (Bluetooth)"}`
  - context: `Desktop companion virtual meeting session`
  - user_context: `{}`

### 0011 | +50848 ms | ai.gemini_live_connected

- Summary: Gemini Live session connected
- Event ID: `evt_00011`
- Wall Time: `2026-05-23T09:56:18.774+05:30`
- Data:
  - attempt: `1`
  - model: `gemini-live-2.5-flash-native-audio`

### 0012 | +53382 ms | frontend.session_started_received

- Summary: Overlay received SESSION_STARTED
- Event ID: `evt_00012`
- Wall Time: `2026-05-23T09:56:21.309+05:30`
- Data:
  - surface: `overlay`
  - detail: `{"meeting_title": "AI Agents: Long Tasks Explained - Google Gemini - Brave"}`

### 0013 | +53410 ms | ws.message_received

- Summary: Backend received websocket message MEETING_BINDING
- Event ID: `evt_00013`
- Wall Time: `2026-05-23T09:56:21.336+05:30`
- Data:
  - message_type: `MEETING_BINDING`
  - payload: `{"target_id": "window:11277002:0", "window_title": "AI Agents: Long Tasks Explained - Google Gemini - Brave", "platform_hint": "generic", "output_device_id": "90c42ab7e82ca84a06b4a1c8be2a893fd854794885a8bf680e03a0eb38...`

### 0014 | +53524 ms | frontend.meeting_binding_updated

- Summary: Meeting binding updated on backend
- Event ID: `evt_00014`
- Wall Time: `2026-05-23T09:56:21.450+05:30`
- Data:
  - binding: `{"target_id": "window:11277002:0", "window_title": "AI Agents: Long Tasks Explained - Google Gemini - Brave", "process_name": null, "platform_hint": "generic", "output_device_id": "90c42ab7e82ca84a06b4a1c8be2a893fd854...`
  - source_mode: `virtual_companion_desktop`

### 0015 | +53529 ms | ws.message_received

- Summary: Backend received websocket message CAPTURE_HEALTH
- Event ID: `evt_00015`
- Wall Time: `2026-05-23T09:56:21.455+05:30`
- Data:
  - message_type: `CAPTURE_HEALTH`
  - payload: `{"mic_forward_ok": true, "remote_audio_ok": true, "frame_capture_ok": true, "reply_output_ok": true, "helper_active": true, "process_loopback_ok": true}`

### 0016 | +53595 ms | frontend.capture_health_updated

- Summary: Capture health updated on backend
- Event ID: `evt_00016`
- Wall Time: `2026-05-23T09:56:21.522+05:30`
- Data:
  - health: `{"mic_forward_ok": true, "remote_audio_ok": true, "frame_capture_ok": true, "reply_output_ok": true, "helper_active": true, "process_loopback_ok": true, "unsafe_device_loopback": false, "degraded_reasons": []}`
  - degraded_mode: `None`

### 0017 | +63205 ms | frontend.hold_started

- Summary: Overlay activated hold-to-ask
- Event ID: `evt_00017`
- Wall Time: `2026-05-23T09:56:31.132+05:30`
- Data:
  - surface: `overlay`
  - detail: `{"source": "orb"}`

### 0018 | +63223 ms | ws.message_received

- Summary: Backend received websocket message HOLD_TO_ASK_STATE
- Event ID: `evt_00018`
- Wall Time: `2026-05-23T09:56:31.150+05:30`
- Data:
  - message_type: `HOLD_TO_ASK_STATE`
  - payload: `{"active": true, "muted_to_meeting": true, "source": "orb"}`

### 0019 | +63318 ms | frontend.ai_playback_done

- Summary: Frontend reported AI playback completion
- Event ID: `evt_00019`
- Wall Time: `2026-05-23T09:56:31.245+05:30`

### 0020 | +63327 ms | ask_ai.hold_activated

- Summary: User started hold-to-ask
- Event ID: `evt_00020`
- Wall Time: `2026-05-23T09:56:31.254+05:30`
- Data:
  - response_mode: `auto`
  - source_mode: `virtual_companion_desktop`

### 0021 | +65366 ms | ask_ai.pre_query_brief_sent

- Summary: Pre-query brief injected into Gemini Live before the user question
- Event ID: `evt_00021`
- Wall Time: `2026-05-23T09:56:33.293+05:30`
- Artifacts: `artifacts/pre_query_brief.txt`
- Data:
  - chars: `908`
  - has_vision: `False`
  - has_market: `False`
  - has_transcript: `False`
  - vision_scene_type: `None`

### 0022 | +65368 ms | ask_ai.mode_instruction_sent

- Summary: Mode activation instruction injected before question audio
- Event ID: `evt_00022`
- Wall Time: `2026-05-23T09:56:33.294+05:30`
- Related Events: `evt_00021`
- Artifacts: `artifacts/mode_instruction.txt`
- Data:
  - response_mode: `auto`

### 0023 | +65370 ms | ws.message_received

- Summary: Backend received websocket message CAPTURE_HEALTH
- Event ID: `evt_00023`
- Wall Time: `2026-05-23T09:56:33.297+05:30`
- Data:
  - message_type: `CAPTURE_HEALTH`
  - payload: `{"mic_forward_ok": true, "remote_audio_ok": true, "frame_capture_ok": true, "reply_output_ok": true, "helper_active": true, "process_loopback_ok": true}`

### 0024 | +65431 ms | frontend.capture_health_updated

- Summary: Capture health updated on backend
- Event ID: `evt_00024`
- Wall Time: `2026-05-23T09:56:33.356+05:30`
- Data:
  - health: `{"mic_forward_ok": true, "remote_audio_ok": true, "frame_capture_ok": true, "reply_output_ok": true, "helper_active": true, "process_loopback_ok": true, "unsafe_device_loopback": false, "degraded_reasons": []}`
  - degraded_mode: `None`

### 0025 | +72141 ms | frontend.hold_released

- Summary: Overlay released hold-to-ask
- Event ID: `evt_00025`
- Wall Time: `2026-05-23T09:56:40.068+05:30`
- Data:
  - surface: `overlay`
  - detail: `{"source": "orb"}`

### 0026 | +72231 ms | ws.message_received

- Summary: Backend received websocket message HOLD_TO_ASK_STATE
- Event ID: `evt_00026`
- Wall Time: `2026-05-23T09:56:40.158+05:30`
- Data:
  - message_type: `HOLD_TO_ASK_STATE`
  - payload: `{"active": false, "muted_to_meeting": false, "source": "orb"}`

### 0027 | +72358 ms | ask_ai.question_audio_sent

- Summary: Captured ask-AI audio sent to Gemini Live as WAV
- Event ID: `evt_00027`
- Wall Time: `2026-05-23T09:56:40.285+05:30`
- Related Events: `evt_00021`, `evt_00022`
- Artifacts: `artifacts/ask_ai_question_audio.wav`
- Data:
  - audio_bytes: `278392`
  - wav_bytes: `278436`
  - chunk_count: `36`
  - hold_duration_ms: `9000`

### 0028 | +72405 ms | ws.message_received

- Summary: Backend received websocket message CAPTURE_HEALTH
- Event ID: `evt_00028`
- Wall Time: `2026-05-23T09:56:40.331+05:30`
- Data:
  - message_type: `CAPTURE_HEALTH`
  - payload: `{"mic_forward_ok": true, "remote_audio_ok": true, "frame_capture_ok": true, "reply_output_ok": true, "helper_active": true, "process_loopback_ok": true}`

### 0029 | +72419 ms | frontend.capture_health_updated

- Summary: Capture health updated on backend
- Event ID: `evt_00029`
- Wall Time: `2026-05-23T09:56:40.345+05:30`
- Data:
  - health: `{"mic_forward_ok": true, "remote_audio_ok": true, "frame_capture_ok": true, "reply_output_ok": true, "helper_active": true, "process_loopback_ok": true, "unsafe_device_loopback": false, "degraded_reasons": []}`
  - degraded_mode: `None`

### 0030 | +85717 ms | transcript.stream_transcript_final

- Summary: Final Deepgram transcript received for counterparty
- Event ID: `evt_00030`
- Wall Time: `2026-05-23T09:56:53.642+05:30`
- Data:
  - speaker: `counterparty`
  - text: `Analysis shows that Gemini interface with a paper titled The Academic Foundation Beyond Pass one.`
  - confidence: `0.81591797`
  - source: `desktop_remote_app`
  - speech_final: `False`

### 0031 | +85760 ms | ws.message_received

- Summary: Backend received websocket message START_COPILOT
- Event ID: `evt_00031`
- Wall Time: `2026-05-23T09:56:53.687+05:30`
- Data:
  - message_type: `START_COPILOT`
  - payload: `{}`

### 0032 | +89607 ms | transcript.stream_transcript_final

- Summary: Final Deepgram transcript received for counterparty
- Event ID: `evt_00032`
- Wall Time: `2026-05-23T09:56:57.534+05:30`
- Data:
  - speaker: `counterparty`
  - text: `It discusses flaws in current AI testing, ability metrics,`
  - confidence: `0.99316406`
  - source: `desktop_remote_app`
  - speech_final: `False`

### 0033 | +89718 ms | frontend.ai_playback_done_sent

- Summary: Overlay sent AI_PLAYBACK_DONE after audio playback finished
- Event ID: `evt_00033`
- Wall Time: `2026-05-23T09:56:57.644+05:30`
- Data:
  - surface: `overlay`
  - detail: `{}`

### 0034 | +89747 ms | ws.message_received

- Summary: Backend received websocket message AI_PLAYBACK_DONE
- Event ID: `evt_00034`
- Wall Time: `2026-05-23T09:56:57.673+05:30`
- Data:
  - message_type: `AI_PLAYBACK_DONE`
  - payload: `{}`

### 0035 | +91099 ms | transcript.stream_transcript_final

- Summary: Final Deepgram transcript received for counterparty
- Event ID: `evt_00035`
- Wall Time: `2026-05-23T09:56:59.025+05:30`
- Data:
  - speaker: `counterparty`
  - text: `the MOP paradox, and the memory trap regarding AI performance.`
  - confidence: `0.9760742`
  - source: `desktop_remote_app`
  - speech_final: `True`

### 0036 | +91110 ms | extraction.text_extraction_triggered

- Summary: Transcript accumulation triggered a text extraction cycle
- Event ID: `evt_00036`
- Wall Time: `2026-05-23T09:56:59.036+05:30`
- Related Events: `evt_00035`
- Artifacts: `artifacts/text_extraction_cycle_26_transcript.txt`, `artifacts/text_extraction_cycle_26_prompt.txt`
- Data:
  - cycle: `26`
  - transcript_chars: `83`
  - transcript_hash: `5774321626398797099`

### 0037 | +98324 ms | session.websocket_disconnect

- Summary: Client websocket disconnected
- Event ID: `evt_00037`
- Wall Time: `2026-05-23T09:57:06.250+05:30`
- Data:
  - state: `ACTIVE`

### 0038 | +98362 ms | session.websocket_cleanup

- Summary: WebSocket cleanup started
- Event ID: `evt_00038`
- Wall Time: `2026-05-23T09:57:06.289+05:30`
- Data:
  - state: `ACTIVE`

### 0039 | +99157 ms | session.session_finalized

- Summary: Session cleanup finalized and report generation starting
- Event ID: `evt_00039`
- Wall Time: `2026-05-23T09:57:07.084+05:30`
- Data:
  - state: `ACTIVE`
  - metrics: `{"stt_requests": 1, "stt_successes": 0, "stt_empty_results": 1, "stt_retry_count": 0, "speaker_user_count": 0, "speaker_counterparty_count": 0, "speaker_unknown_count": 0, "avg_utterance_duration_ms": 0.0, "utterance_...`

