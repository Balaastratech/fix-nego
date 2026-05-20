# Desktop Companion Runtime

This desktop app is the Windows companion shell for virtual meetings.

## What it does

- Captures your local mic and sends source-tagged `LOCAL_MIC_PCM` to the backend.
- Captures a selected meeting window and sends `SCREEN_FRAME` plus `REMOTE_APP_PCM` when audio is available.
- Plays AI reply audio on your selected listening output.
- Forwards your live mic to a selected virtual-audio route output.
- During Hold-to-Ask, the mic-forward route is muted while backend query capture continues.

## Required Windows audio setup for private Hold-to-Ask

Windows does not expose a built-in app-only virtual microphone device. For the privacy path to work end to end, install a virtual audio cable and set the meeting app to use the cable's paired microphone input.

Recommended device pairing pattern:

- Desktop companion meeting route output: `CABLE Input` or equivalent virtual playback endpoint
- Meeting app microphone input: paired `CABLE Output` or equivalent virtual recording endpoint
- Desktop companion listening output: your real headphones or speaker output

## Expected meeting setup

1. Start the desktop companion.
2. Pick the meeting window.
3. Pick your listening output for AI replies.
4. Pick the virtual meeting-route output.
5. In Zoom, Meet, Teams, or another meeting app, choose the paired virtual microphone device.
6. Start the session.
7. Hold `Hold To Ask` to pause meeting mic forwarding and privately query the AI.

## Current degraded states

- `virtual_mic_helper_unavailable`: no recognizable virtual route output selected
- `remote_audio_unavailable`: the selected meeting capture did not provide an audio track
- `frame_capture_unavailable`: window capture stopped

## Install

```powershell
cd desktop
npm install
npm start
```

## Install VB-CABLE with the bundled helper

```powershell
cd desktop
powershell -ExecutionPolicy Bypass -File .\scripts\install-vbcable.ps1
```
