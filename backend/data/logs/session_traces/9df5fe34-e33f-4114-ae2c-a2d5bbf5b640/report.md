# Structured Session Trace Report

- Session ID: `9df5fe34-e33f-4114-ae2c-a2d5bbf5b640`
- Started At: `2026-05-23T10:18:00.108+05:30`
- Events: `20`
- Trace JSONL: `D:\Balaastra\hackothon\project code\backend\data\logs\session_traces\9df5fe34-e33f-4114-ae2c-a2d5bbf5b640\trace.jsonl`
- Artifacts: `D:\Balaastra\hackothon\project code\backend\data\logs\session_traces\9df5fe34-e33f-4114-ae2c-a2d5bbf5b640\artifacts`

## Event Timeline

### 0001 | +54 ms | session.websocket_connected

- Summary: WebSocket connection accepted for session
- Event ID: `evt_00001`
- Wall Time: `2026-05-23T10:18:00.163+05:30`
- Data:
  - requested_session_id: `None`
  - restored: `False`
  - state: `IDLE`

### 0002 | +62226 ms | transcript.stream_transcript_final

- Summary: Final Deepgram transcript received for user
- Event ID: `evt_00002`
- Wall Time: `2026-05-23T10:19:02.334+05:30`
- Data:
  - speaker: `user`
  - text: `You hear me? Can you hear me?`
  - confidence: `0.9980469`
  - source: `desktop_local_mic`
  - speech_final: `True`

### 0003 | +62235 ms | extraction.text_extraction_triggered

- Summary: Transcript accumulation triggered a text extraction cycle
- Event ID: `evt_00003`
- Wall Time: `2026-05-23T10:19:02.343+05:30`
- Related Events: `evt_00002`
- Artifacts: `artifacts/text_extraction_cycle_21_transcript.txt`, `artifacts/text_extraction_cycle_21_prompt.txt`
- Data:
  - cycle: `21`
  - transcript_chars: `42`
  - transcript_hash: `-1685658257723436187`

### 0004 | +78825 ms | extraction.text_extraction_completed

- Summary: Text extraction cycle completed
- Event ID: `evt_00004`
- Wall Time: `2026-05-23T10:19:18.934+05:30`
- Related Events: `evt_00002`
- Artifacts: `artifacts/text_extraction_cycle_21_transcript.txt`, `artifacts/text_extraction_cycle_21_prompt.txt`, `artifacts/text_extraction_cycle_32_result.json`
- Data:
  - cycle: `32`
  - keys: `["buyer_offer", "counterparty_company", "counterparty_goal", "counterparty_person_name", "counterparty_price", "counterparty_sentiment", "item", "key_moments", "leverage_points", "meeting_legal_terms", "negotiation_ty...`

### 0005 | +78853 ms | context.context_post_processed

- Summary: Extracted context merged into live session state
- Event ID: `evt_00005`
- Wall Time: `2026-05-23T10:19:18.961+05:30`
- Related Events: `evt_00004`
- Artifacts: `artifacts/context_postprocess_cycle_32.json`
- Data:
  - cycle: `32`
  - critical_event_count: `0`
  - critical_events: `[]`

### 0006 | +88808 ms | transcript.stream_transcript_final

- Summary: Final Deepgram transcript received for user
- Event ID: `evt_00006`
- Wall Time: `2026-05-23T10:19:28.915+05:30`
- Data:
  - speaker: `user`
  - text: `The fuck is going on? And can you hear me or not?`
  - confidence: `0.9980469`
  - source: `desktop_local_mic`
  - speech_final: `False`

### 0007 | +89293 ms | transcript.stream_transcript_final

- Summary: Final Deepgram transcript received for user
- Event ID: `evt_00007`
- Wall Time: `2026-05-23T10:19:29.401+05:30`
- Data:
  - speaker: `user`
  - text: `The fuck I'm seeing half transcript.`
  - confidence: `0.79296875`
  - source: `desktop_local_mic`
  - speech_final: `True`

### 0008 | +89314 ms | extraction.text_extraction_triggered

- Summary: Transcript accumulation triggered a text extraction cycle
- Event ID: `evt_00008`
- Wall Time: `2026-05-23T10:19:29.421+05:30`
- Related Events: `evt_00007`
- Artifacts: `artifacts/text_extraction_cycle_39_transcript.txt`, `artifacts/text_extraction_cycle_39_prompt.txt`
- Data:
  - cycle: `39`
  - transcript_chars: `92`
  - transcript_hash: `-594034406348409452`

### 0009 | +94736 ms | extraction.text_extraction_completed

- Summary: Text extraction cycle completed
- Event ID: `evt_00009`
- Wall Time: `2026-05-23T10:19:34.845+05:30`
- Related Events: `evt_00007`
- Artifacts: `artifacts/text_extraction_cycle_39_transcript.txt`, `artifacts/text_extraction_cycle_39_prompt.txt`, `artifacts/text_extraction_cycle_43_result.json`
- Data:
  - cycle: `43`
  - keys: `["buyer_offer", "counterparty_company", "counterparty_goal", "counterparty_person_name", "counterparty_price", "counterparty_sentiment", "item", "key_moments", "leverage_points", "meeting_legal_terms", "negotiation_ty...`

### 0010 | +94760 ms | context.context_post_processed

- Summary: Extracted context merged into live session state
- Event ID: `evt_00010`
- Wall Time: `2026-05-23T10:19:34.868+05:30`
- Related Events: `evt_00009`
- Artifacts: `artifacts/context_postprocess_cycle_43.json`
- Data:
  - cycle: `43`
  - critical_event_count: `0`
  - critical_events: `[]`

### 0011 | +115459 ms | ai.ai_response_completed

- Summary: Gemini completed an AI response turn
- Event ID: `evt_00011`
- Wall Time: `2026-05-23T10:19:55.568+05:30`
- Related Events: `evt_00010`
- Artifacts: `artifacts/ai_response_text.txt`
- Data:
  - context: `ask_ai`
  - response_mode: `auto`
  - question_event_id: `None`
  - pre_query_brief_event_id: `None`
  - vision_event_id: `None`
  - context_event_id: `evt_00010`
  - research_event_id: `None`

### 0012 | +125054 ms | transcript.stream_transcript_final

- Summary: Final Deepgram transcript received for counterparty
- Event ID: `evt_00012`
- Wall Time: `2026-05-23T10:20:05.162+05:30`
- Data:
  - speaker: `counterparty`
  - text: `Once you confirm can hear you, proceed by asking for their opening offer.`
  - confidence: `1.0`
  - source: `desktop_remote_app`
  - speech_final: `True`

### 0013 | +129071 ms | extraction.text_extraction_triggered

- Summary: Transcript accumulation triggered a text extraction cycle
- Event ID: `evt_00013`
- Wall Time: `2026-05-23T10:20:09.179+05:30`
- Related Events: `evt_00012`
- Artifacts: `artifacts/text_extraction_cycle_66_transcript.txt`, `artifacts/text_extraction_cycle_66_prompt.txt`
- Data:
  - cycle: `66`
  - transcript_chars: `187`
  - transcript_hash: `-7517704081610057932`

### 0014 | +131651 ms | ai.ai_response_completed

- Summary: Gemini completed an AI response turn
- Event ID: `evt_00014`
- Wall Time: `2026-05-23T10:20:11.759+05:30`
- Related Events: `evt_00010`
- Artifacts: `artifacts/ai_response_text_2.txt`
- Data:
  - context: `ask_ai`
  - response_mode: `auto`
  - question_event_id: `None`
  - pre_query_brief_event_id: `None`
  - vision_event_id: `None`
  - context_event_id: `evt_00010`
  - research_event_id: `None`

### 0015 | +134332 ms | extraction.text_extraction_completed

- Summary: Text extraction cycle completed
- Event ID: `evt_00015`
- Wall Time: `2026-05-23T10:20:14.439+05:30`
- Related Events: `evt_00012`
- Artifacts: `artifacts/text_extraction_cycle_66_transcript.txt`, `artifacts/text_extraction_cycle_66_prompt.txt`, `artifacts/text_extraction_cycle_66_result.json`
- Data:
  - cycle: `66`
  - keys: `["buyer_offer", "counterparty_company", "counterparty_goal", "counterparty_person_name", "counterparty_price", "counterparty_sentiment", "item", "key_moments", "leverage_points", "meeting_legal_terms", "negotiation_ty...`

### 0016 | +134334 ms | context.context_post_processed

- Summary: Extracted context merged into live session state
- Event ID: `evt_00016`
- Wall Time: `2026-05-23T10:20:14.442+05:30`
- Related Events: `evt_00015`
- Artifacts: `artifacts/context_postprocess_cycle_66.json`
- Data:
  - cycle: `66`
  - critical_event_count: `0`
  - critical_events: `[]`

### 0017 | +135971 ms | vision.vision_analysis_completed

- Summary: Vision model analyzed the current frame set
- Event ID: `evt_00017`
- Wall Time: `2026-05-23T10:20:16.079+05:30`
- Related Events: `evt_00016`, `evt_00012`
- Artifacts: `artifacts/vision_prompt.txt`, `artifacts/vision_request_context.json`, `artifacts/vision_frame_1.jpg`, `artifacts/vision_frame_2.jpg`, `artifacts/vision_result.json`
- Data:
  - scene_type: `screen`
  - confidence: `None`
  - frame_count: `2`
  - document_text_chars: `159`

### 0018 | +142934 ms | session.websocket_disconnect

- Summary: Client websocket disconnected
- Event ID: `evt_00018`
- Wall Time: `2026-05-23T10:20:23.042+05:30`
- Data:
  - state: `ACTIVE`

### 0019 | +143001 ms | session.websocket_cleanup

- Summary: WebSocket cleanup started
- Event ID: `evt_00019`
- Wall Time: `2026-05-23T10:20:23.109+05:30`
- Data:
  - state: `ACTIVE`

### 0020 | +143755 ms | session.session_finalized

- Summary: Session cleanup finalized and report generation starting
- Event ID: `evt_00020`
- Wall Time: `2026-05-23T10:20:23.863+05:30`
- Data:
  - state: `ACTIVE`
  - metrics: `{"stt_requests": 0, "stt_successes": 0, "stt_empty_results": 0, "stt_retry_count": 0, "speaker_user_count": 0, "speaker_counterparty_count": 0, "speaker_unknown_count": 0, "avg_utterance_duration_ms": 0.0, "utterance_...`

