# Structured Session Trace Report

- Session ID: `26183d8c-b9b2-4b0e-bd79-06be5bfbb821`
- Started At: `2026-05-23T09:31:35.505+05:30`
- Events: `47`
- Trace JSONL: `D:\Balaastra\hackothon\project code\backend\data\logs\session_traces\26183d8c-b9b2-4b0e-bd79-06be5bfbb821\trace.jsonl`
- Artifacts: `D:\Balaastra\hackothon\project code\backend\data\logs\session_traces\26183d8c-b9b2-4b0e-bd79-06be5bfbb821\artifacts`

## Event Timeline

### 0001 | +33 ms | session.websocket_connected

- Summary: WebSocket connection accepted for session
- Event ID: `evt_00001`
- Wall Time: `2026-05-23T09:31:35.540+05:30`
- Data:
  - requested_session_id: `None`
  - restored: `False`
  - state: `IDLE`

### 0002 | +83 ms | frontend.connection_established_received

- Summary: Overlay received websocket connection acknowledgement
- Event ID: `evt_00002`
- Wall Time: `2026-05-23T09:31:35.589+05:30`
- Data:
  - surface: `overlay`
  - detail: `{"session_id": "26183d8c-b9b2-4b0e-bd79-06be5bfbb821", "restored": false, "trace_report_path": "D:\\Balaastra\\hackothon\\project code\\backend\\data\\logs\\session_traces\\26183d8c-b9b2-4b0e-bd79-06be5bfbb821\\report...`

### 0003 | +1443 ms | frontend.meeting_capture_requested

- Summary: Overlay started meeting capture setup
- Event ID: `evt_00003`
- Wall Time: `2026-05-23T09:31:36.949+05:30`
- Data:
  - surface: `overlay`
  - detail: `{"source_id": "window:11277002:0", "selected_target": "AI Agents: Long Tasks Explained - Google Gemini - Brave"}`

### 0004 | +3323 ms | frontend.meeting_capture_started

- Summary: Meeting capture started successfully
- Event ID: `evt_00004`
- Wall Time: `2026-05-23T09:31:38.829+05:30`
- Data:
  - surface: `overlay`
  - detail: `{"source_id": "window:11277002:0", "has_audio": true, "video_track_label": "AI Agents: Long Tasks Explained - Google Gemini - Brave", "audio_track_count": 1}`

### 0005 | +4957 ms | frontend.privacy_consent_sent

- Summary: Overlay sent privacy consent before starting session
- Event ID: `evt_00005`
- Wall Time: `2026-05-23T09:31:40.463+05:30`
- Data:
  - surface: `overlay`
  - detail: `{"version": "1.0", "mode": "live"}`

### 0006 | +4964 ms | ws.message_received

- Summary: Backend received websocket message PRIVACY_CONSENT_GRANTED
- Event ID: `evt_00006`
- Wall Time: `2026-05-23T09:31:40.470+05:30`
- Data:
  - message_type: `PRIVACY_CONSENT_GRANTED`
  - payload: `{"version": "1.0", "mode": "live"}`

### 0007 | +4965 ms | session.privacy_consent_granted

- Summary: Privacy consent received from client
- Event ID: `evt_00007`
- Wall Time: `2026-05-23T09:31:40.471+05:30`
- Data:
  - version: `1.0`
  - mode: `live`

### 0008 | +5059 ms | frontend.start_negotiation_sent

- Summary: Overlay sent START_NEGOTIATION
- Event ID: `evt_00008`
- Wall Time: `2026-05-23T09:31:40.564+05:30`
- Data:
  - surface: `overlay`
  - detail: `{"meeting_title": "AI Agents: Long Tasks Explained - Google Gemini - Brave", "source_mode": "virtual_companion_desktop"}`

### 0009 | +5061 ms | ws.message_received

- Summary: Backend received websocket message START_NEGOTIATION
- Event ID: `evt_00009`
- Wall Time: `2026-05-23T09:31:40.567+05:30`
- Data:
  - message_type: `START_NEGOTIATION`
  - payload: `{"context": "Desktop companion virtual meeting session", "source_mode": "virtual_companion_desktop", "capture_preset": "meeting_window_default", "companion_quality_mode": "companion_ready", "meeting_binding": {"target...`

### 0010 | +5074 ms | session.session_start_requested

- Summary: Backend accepted START_NEGOTIATION and initialized the session runtime
- Event ID: `evt_00010`
- Wall Time: `2026-05-23T09:31:40.580+05:30`
- Data:
  - source_mode: `virtual_companion_desktop`
  - meeting_binding: `{"target_id": "window:11277002:0", "window_title": "AI Agents: Long Tasks Explained - Google Gemini - Brave", "process_name": null, "platform_hint": "generic", "output_device_id": "90c42ab7e82ca84a06b4a1c8be2a893fd854...`
  - selected_output_device: `{"device_id": "communications", "label": "Communications - Headphones (OnePlus Buds Pro 2) (Bluetooth)"}`
  - context: `Desktop companion virtual meeting session`
  - user_context: `{}`

### 0011 | +14582 ms | ai.gemini_live_connected

- Summary: Gemini Live session connected
- Event ID: `evt_00011`
- Wall Time: `2026-05-23T09:31:50.088+05:30`
- Data:
  - attempt: `1`
  - model: `gemini-live-2.5-flash-native-audio`

### 0012 | +15939 ms | frontend.session_started_received

- Summary: Overlay received SESSION_STARTED
- Event ID: `evt_00012`
- Wall Time: `2026-05-23T09:31:51.446+05:30`
- Data:
  - surface: `overlay`
  - detail: `{"meeting_title": "AI Agents: Long Tasks Explained - Google Gemini - Brave"}`

### 0013 | +15942 ms | ws.message_received

- Summary: Backend received websocket message MEETING_BINDING
- Event ID: `evt_00013`
- Wall Time: `2026-05-23T09:31:51.448+05:30`
- Data:
  - message_type: `MEETING_BINDING`
  - payload: `{"target_id": "window:11277002:0", "window_title": "AI Agents: Long Tasks Explained - Google Gemini - Brave", "platform_hint": "generic", "output_device_id": "90c42ab7e82ca84a06b4a1c8be2a893fd854794885a8bf680e03a0eb38...`

### 0014 | +16009 ms | frontend.meeting_binding_updated

- Summary: Meeting binding updated on backend
- Event ID: `evt_00014`
- Wall Time: `2026-05-23T09:31:51.514+05:30`
- Data:
  - binding: `{"target_id": "window:11277002:0", "window_title": "AI Agents: Long Tasks Explained - Google Gemini - Brave", "process_name": null, "platform_hint": "generic", "output_device_id": "90c42ab7e82ca84a06b4a1c8be2a893fd854...`
  - source_mode: `virtual_companion_desktop`

### 0015 | +16011 ms | ws.message_received

- Summary: Backend received websocket message CAPTURE_HEALTH
- Event ID: `evt_00015`
- Wall Time: `2026-05-23T09:31:51.517+05:30`
- Data:
  - message_type: `CAPTURE_HEALTH`
  - payload: `{"mic_forward_ok": true, "remote_audio_ok": true, "frame_capture_ok": true, "reply_output_ok": true, "helper_active": true, "process_loopback_ok": true}`

### 0016 | +16031 ms | frontend.capture_health_updated

- Summary: Capture health updated on backend
- Event ID: `evt_00016`
- Wall Time: `2026-05-23T09:31:51.537+05:30`
- Data:
  - health: `{"mic_forward_ok": true, "remote_audio_ok": true, "frame_capture_ok": true, "reply_output_ok": true, "helper_active": true, "process_loopback_ok": true, "unsafe_device_loopback": false, "degraded_reasons": []}`
  - degraded_mode: `None`

### 0017 | +26534 ms | transcript.stream_transcript_final

- Summary: Final Deepgram transcript received for user
- Event ID: `evt_00017`
- Wall Time: `2026-05-23T09:32:02.040+05:30`
- Data:
  - speaker: `user`
  - text: `Can you hear`
  - confidence: `0.9970703`
  - source: `desktop_local_mic`
  - speech_final: `True`

### 0018 | +26552 ms | extraction.text_extraction_triggered

- Summary: Transcript accumulation triggered a text extraction cycle
- Event ID: `evt_00018`
- Wall Time: `2026-05-23T09:32:02.059+05:30`
- Related Events: `evt_00017`
- Artifacts: `artifacts/text_extraction_cycle_9_transcript.txt`, `artifacts/text_extraction_cycle_9_prompt.txt`
- Data:
  - cycle: `9`
  - transcript_chars: `25`
  - transcript_hash: `-8960724355201700820`

### 0019 | +26609 ms | ws.message_received

- Summary: Backend received websocket message START_COPILOT
- Event ID: `evt_00019`
- Wall Time: `2026-05-23T09:32:02.115+05:30`
- Data:
  - message_type: `START_COPILOT`
  - payload: `{}`

### 0020 | +33359 ms | frontend.hold_started

- Summary: Overlay activated hold-to-ask
- Event ID: `evt_00020`
- Wall Time: `2026-05-23T09:32:08.865+05:30`
- Data:
  - surface: `overlay`
  - detail: `{"source": "orb"}`

### 0021 | +33369 ms | ws.message_received

- Summary: Backend received websocket message HOLD_TO_ASK_STATE
- Event ID: `evt_00021`
- Wall Time: `2026-05-23T09:32:08.875+05:30`
- Data:
  - message_type: `HOLD_TO_ASK_STATE`
  - payload: `{"active": true, "muted_to_meeting": true, "source": "orb"}`

### 0022 | +33413 ms | frontend.ai_playback_done

- Summary: Frontend reported AI playback completion
- Event ID: `evt_00022`
- Wall Time: `2026-05-23T09:32:08.918+05:30`

### 0023 | +33415 ms | ask_ai.hold_activated

- Summary: User started hold-to-ask
- Event ID: `evt_00023`
- Wall Time: `2026-05-23T09:32:08.921+05:30`
- Data:
  - response_mode: `auto`
  - source_mode: `virtual_companion_desktop`

### 0024 | +35429 ms | ask_ai.pre_query_brief_sent

- Summary: Pre-query brief injected into Gemini Live before the user question
- Event ID: `evt_00024`
- Wall Time: `2026-05-23T09:32:10.935+05:30`
- Artifacts: `artifacts/pre_query_brief.txt`
- Data:
  - chars: `934`
  - has_vision: `False`
  - has_market: `False`
  - has_transcript: `True`
  - vision_scene_type: `None`

### 0025 | +35434 ms | ask_ai.mode_instruction_sent

- Summary: Mode activation instruction injected before question audio
- Event ID: `evt_00025`
- Wall Time: `2026-05-23T09:32:10.939+05:30`
- Related Events: `evt_00024`
- Artifacts: `artifacts/mode_instruction.txt`
- Data:
  - response_mode: `auto`

### 0026 | +35438 ms | ws.message_received

- Summary: Backend received websocket message CAPTURE_HEALTH
- Event ID: `evt_00026`
- Wall Time: `2026-05-23T09:32:10.944+05:30`
- Data:
  - message_type: `CAPTURE_HEALTH`
  - payload: `{"mic_forward_ok": true, "remote_audio_ok": true, "frame_capture_ok": true, "reply_output_ok": true, "helper_active": true, "process_loopback_ok": true}`

### 0027 | +35541 ms | frontend.capture_health_updated

- Summary: Capture health updated on backend
- Event ID: `evt_00027`
- Wall Time: `2026-05-23T09:32:11.046+05:30`
- Data:
  - health: `{"mic_forward_ok": true, "remote_audio_ok": true, "frame_capture_ok": true, "reply_output_ok": true, "helper_active": true, "process_loopback_ok": true, "unsafe_device_loopback": false, "degraded_reasons": []}`
  - degraded_mode: `None`

### 0028 | +39159 ms | frontend.hold_released

- Summary: Overlay released hold-to-ask
- Event ID: `evt_00028`
- Wall Time: `2026-05-23T09:32:14.665+05:30`
- Data:
  - surface: `overlay`
  - detail: `{"source": "orb"}`

### 0029 | +39181 ms | ws.message_received

- Summary: Backend received websocket message HOLD_TO_ASK_STATE
- Event ID: `evt_00029`
- Wall Time: `2026-05-23T09:32:14.687+05:30`
- Data:
  - message_type: `HOLD_TO_ASK_STATE`
  - payload: `{"active": false, "muted_to_meeting": false, "source": "orb"}`

### 0030 | +39335 ms | ask_ai.question_audio_sent

- Summary: Captured ask-AI audio sent to Gemini Live as WAV
- Event ID: `evt_00030`
- Wall Time: `2026-05-23T09:32:14.841+05:30`
- Related Events: `evt_00024`, `evt_00025`
- Artifacts: `artifacts/ask_ai_question_audio.wav`
- Data:
  - audio_bytes: `182866`
  - wav_bytes: `182910`
  - chunk_count: `20`
  - hold_duration_ms: `5874`

### 0031 | +39420 ms | ws.message_received

- Summary: Backend received websocket message CAPTURE_HEALTH
- Event ID: `evt_00031`
- Wall Time: `2026-05-23T09:32:14.926+05:30`
- Data:
  - message_type: `CAPTURE_HEALTH`
  - payload: `{"mic_forward_ok": true, "remote_audio_ok": true, "frame_capture_ok": true, "reply_output_ok": true, "helper_active": true, "process_loopback_ok": true}`

### 0032 | +39444 ms | frontend.capture_health_updated

- Summary: Capture health updated on backend
- Event ID: `evt_00032`
- Wall Time: `2026-05-23T09:32:14.950+05:30`
- Data:
  - health: `{"mic_forward_ok": true, "remote_audio_ok": true, "frame_capture_ok": true, "reply_output_ok": true, "helper_active": true, "process_loopback_ok": true, "unsafe_device_loopback": false, "degraded_reasons": []}`
  - degraded_mode: `None`

### 0033 | +40236 ms | extraction.text_extraction_completed

- Summary: Text extraction cycle completed
- Event ID: `evt_00033`
- Wall Time: `2026-05-23T09:32:15.742+05:30`
- Related Events: `evt_00017`
- Artifacts: `artifacts/text_extraction_cycle_9_transcript.txt`, `artifacts/text_extraction_cycle_9_prompt.txt`, `artifacts/text_extraction_cycle_18_result.json`
- Data:
  - cycle: `18`
  - keys: `["buyer_offer", "counterparty_company", "counterparty_goal", "counterparty_person_name", "counterparty_price", "counterparty_sentiment", "item", "key_moments", "leverage_points", "meeting_legal_terms", "negotiation_ty...`

### 0034 | +40249 ms | context.context_post_processed

- Summary: Extracted context merged into live session state
- Event ID: `evt_00034`
- Wall Time: `2026-05-23T09:32:15.754+05:30`
- Related Events: `evt_00033`
- Artifacts: `artifacts/context_postprocess_cycle_18.json`
- Data:
  - cycle: `18`
  - critical_event_count: `0`
  - critical_events: `[]`

### 0035 | +43707 ms | ask_ai.question_transcribed

- Summary: Background STT transcribed the ask-AI question for display
- Event ID: `evt_00035`
- Wall Time: `2026-05-23T09:32:19.213+05:30`
- Data:
  - question_id: `ask_ai_1779508928924`
  - text: `So what can you see on your screen and describe me what you can see`

### 0036 | +43893 ms | ai.ai_response_completed

- Summary: Gemini completed an AI response turn
- Event ID: `evt_00036`
- Wall Time: `2026-05-23T09:32:19.400+05:30`
- Related Events: `evt_00035`, `evt_00024`, `evt_00025`, `evt_00034`
- Artifacts: `artifacts/ai_response_text.txt`
- Data:
  - context: `ask_ai`
  - response_mode: `auto`
  - question_event_id: `evt_00035`
  - pre_query_brief_event_id: `evt_00024`
  - vision_event_id: `None`
  - context_event_id: `evt_00034`
  - research_event_id: `None`

### 0037 | +43988 ms | injection.coalesced_intel_injected

- Summary: Coalesced listener intel injected into Gemini Live
- Event ID: `evt_00037`
- Wall Time: `2026-05-23T09:32:19.494+05:30`
- Related Events: `evt_00034`
- Artifacts: `artifacts/coalesced_intel_injection.txt`
- Data:
  - chars: `651`
  - critical_event_count: `0`

### 0038 | +46202 ms | transcript.stream_transcript_final

- Summary: Final Deepgram transcript received for counterparty
- Event ID: `evt_00038`
- Wall Time: `2026-05-23T09:32:21.707+05:30`
- Data:
  - speaker: `counterparty`
  - text: `See a web`
  - confidence: `0.97265625`
  - source: `desktop_remote_app`
  - speech_final: `True`

### 0039 | +46220 ms | extraction.text_extraction_triggered

- Summary: Transcript accumulation triggered a text extraction cycle
- Event ID: `evt_00039`
- Wall Time: `2026-05-23T09:32:21.726+05:30`
- Related Events: `evt_00038`
- Artifacts: `artifacts/text_extraction_cycle_22_transcript.txt`, `artifacts/text_extraction_cycle_22_prompt.txt`
- Data:
  - cycle: `22`
  - transcript_chars: `56`
  - transcript_hash: `-6379214204425131901`

### 0040 | +49509 ms | extraction.text_extraction_completed

- Summary: Text extraction cycle completed
- Event ID: `evt_00040`
- Wall Time: `2026-05-23T09:32:25.015+05:30`
- Related Events: `evt_00038`
- Artifacts: `artifacts/text_extraction_cycle_22_transcript.txt`, `artifacts/text_extraction_cycle_22_prompt.txt`, `artifacts/text_extraction_cycle_24_result.json`
- Data:
  - cycle: `24`
  - keys: `["buyer_offer", "counterparty_company", "counterparty_goal", "counterparty_person_name", "counterparty_price", "counterparty_sentiment", "item", "key_moments", "leverage_points", "meeting_legal_terms", "negotiation_ty...`

### 0041 | +49512 ms | context.context_post_processed

- Summary: Extracted context merged into live session state
- Event ID: `evt_00041`
- Wall Time: `2026-05-23T09:32:25.018+05:30`
- Related Events: `evt_00040`
- Artifacts: `artifacts/context_postprocess_cycle_24.json`
- Data:
  - cycle: `24`
  - critical_event_count: `0`
  - critical_events: `[]`

### 0042 | +50109 ms | transcript.stream_transcript_final

- Summary: Final Deepgram transcript received for counterparty
- Event ID: `evt_00042`
- Wall Time: `2026-05-23T09:32:25.615+05:30`
- Data:
  - speaker: `counterparty`
  - text: `from gemini.google.com discussing AI aids. The main`
  - confidence: `0.9760742`
  - source: `desktop_remote_app`
  - speech_final: `False`

### 0043 | +50937 ms | frontend.ai_playback_done_sent

- Summary: Overlay sent AI_PLAYBACK_DONE after audio playback finished
- Event ID: `evt_00043`
- Wall Time: `2026-05-23T09:32:26.442+05:30`
- Data:
  - surface: `overlay`
  - detail: `{}`

### 0044 | +50950 ms | ws.message_received

- Summary: Backend received websocket message AI_PLAYBACK_DONE
- Event ID: `evt_00044`
- Wall Time: `2026-05-23T09:32:26.456+05:30`
- Data:
  - message_type: `AI_PLAYBACK_DONE`
  - payload: `{}`

### 0045 | +58272 ms | session.websocket_disconnect

- Summary: Client websocket disconnected
- Event ID: `evt_00045`
- Wall Time: `2026-05-23T09:32:33.777+05:30`
- Data:
  - state: `ACTIVE`

### 0046 | +58284 ms | session.websocket_cleanup

- Summary: WebSocket cleanup started
- Event ID: `evt_00046`
- Wall Time: `2026-05-23T09:32:33.790+05:30`
- Data:
  - state: `ACTIVE`

### 0047 | +58827 ms | session.session_finalized

- Summary: Session cleanup finalized and report generation starting
- Event ID: `evt_00047`
- Wall Time: `2026-05-23T09:32:34.332+05:30`
- Data:
  - state: `ACTIVE`
  - metrics: `{"stt_requests": 1, "stt_successes": 0, "stt_empty_results": 1, "stt_retry_count": 0, "speaker_user_count": 0, "speaker_counterparty_count": 0, "speaker_unknown_count": 0, "avg_utterance_duration_ms": 0.0, "utterance_...`

