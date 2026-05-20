[WebSocket] Sending: {"type":"PRIVACY_CONSENT_GRANTED","payload":{"version":"1.0","mode":"live"}}
D:\Balaastra\hackothon\project code\frontend\hooks\useNegotiation.ts:234 NEGOTIATION_STATE_CHANGED: {previous_state: 'IDLE', current_state: 'CONSENTED', timestamp: 1775529756.9258132}
D:\Balaastra\hackothon\project code\frontend\hooks\useEnrollment.ts:33 [Enrollment] Triggering enrollment...
D:\Balaastra\hackothon\project code\frontend\hooks\useNegotiation.ts:406 [Enrollment] Starting voice enrollment
D:\Balaastra\hackothon\project code\frontend\hooks\useEnrollment.ts:39 [Enrollment] Enrollment triggered
D:\Balaastra\hackothon\project code\frontend\hooks\useNegotiation.ts:440 [Enrollment] Audio capture started (VAD bypassed), waiting 500ms for stabilization...
D:\Balaastra\hackothon\project code\frontend\hooks\useNegotiation.ts:445 [Enrollment] Sending ENROLLMENT_START to backend
D:\Balaastra\hackothon\project code\frontend\lib\websocket.ts:133 [WebSocket] sendControl called: ENROLLMENT_START {}
D:\Balaastra\hackothon\project code\frontend\lib\websocket.ts:136 [WebSocket] Sending: {"type":"ENROLLMENT_START","payload":{}}
D:\Balaastra\hackothon\project code\frontend\hooks\useNegotiation.ts:157 [Enrollment] ENROLLMENT_COMPLETE received: {success: true, message: 'Voice sample ready.', speaker_mode: 'auto', speechbrain_profile_state: 'ready', progress: null, …}
D:\Balaastra\hackothon\project code\frontend\hooks\useEnrollment.ts:48 [Enrollment] Stopping capture, state: success
D:\Balaastra\hackothon\project code\frontend\lib\audio-worklet-manager.ts:329 [VAD] initializing vad
ort-wasm-simd.wasm:0x82c2bc 2026-04-07 08:13:02.366200 [W:onnxruntime:, graph.cc:3490 CleanUnusedInitializersAndNodeArgs] Removing initializer '140'. It is not used by any node and should be removed from the model.
lt @ ort-web.min.js:7
P @ ort-web.min.js:7
$func11504 @ ort-wasm-simd.wasm:0x82c2bc
$func2149 @ ort-wasm-simd.wasm:0x16396e
$func584 @ ort-wasm-simd.wasm:0x48a63
$func11428 @ ort-wasm-simd.wasm:0x8296b1
$func631 @ ort-wasm-simd.wasm:0x4d0e8
v @ ort-web.min.js:7
$func92 @ ort-wasm-simd.wasm:0xb052
$func5739 @ ort-wasm-simd.wasm:0x4799cb
$func140 @ ort-wasm-simd.wasm:0x1064c
$func11064 @ ort-wasm-simd.wasm:0x811d54
$func2505 @ ort-wasm-simd.wasm:0x1b1083
$func734 @ ort-wasm-simd.wasm:0x5f81a
$func1128 @ ort-wasm-simd.wasm:0xa2da5
$func2106 @ ort-wasm-simd.wasm:0x15877a
$func5908 @ ort-wasm-simd.wasm:0x4a6cbe
h @ ort-web.min.js:7
$func5859 @ ort-wasm-simd.wasm:0x492c3a
o @ ort-web.min.js:7
$func5858 @ ort-wasm-simd.wasm:0x492531
$Ra @ ort-wasm-simd.wasm:0x6ebff8
e._OrtCreateSession @ ort-web.min.js:7
e.createSessionFinalize @ ort-web.min.js:7
e.createSession @ ort-web.min.js:7
e.createSession @ ort-web.min.js:7
loadModel @ ort-web.min.js:7
await in loadModel
createSessionHandler @ ort-web.min.js:7
create @ inference-session-impl.js:176
await in create
SileroLegacy.new @ legacy.js:43
await in SileroLegacy.new
new @ real-time-vad.js:172
new @ real-time-vad.js:91
createBrowserVad @ D:\Balaastra\hackothon\project code\frontend\lib\audio-worklet-manager.ts:329
startCapture @ D:\Balaastra\hackothon\project code\frontend\lib\audio-worklet-manager.ts:99
await in startCapture
useNegotiation.useCallback[startNegotiation] @ D:\Balaastra\hackothon\project code\frontend\hooks\useNegotiation.ts:327
await in useNegotiation.useCallback[startNegotiation]
Home.useCallback[handleStartNegotiation] @ D:\Balaastra\hackothon\project code\frontend\app\page.tsx:173
executeDispatch @ react-dom-client.development.js:16971
runWithFiberInDEV @ react-dom-client.development.js:872
processDispatchQueue @ react-dom-client.development.js:17021
eval @ react-dom-client.development.js:17622
batchedUpdates$1 @ react-dom-client.development.js:3312
dispatchEventForPluginEventSystem @ react-dom-client.development.js:17175
dispatchEvent @ react-dom-client.development.js:21358
dispatchDiscreteEvent @ react-dom-client.development.js:21326
ort-wasm-simd.wasm:0x82c2bc 2026-04-07 08:13:02.377400 [W:onnxruntime:, graph.cc:3490 CleanUnusedInitializersAndNodeArgs] Removing initializer '131'. It is not used by any node and should be removed from the model.
lt @ ort-web.min.js:7
P @ ort-web.min.js:7
$func11504 @ ort-wasm-simd.wasm:0x82c2bc
$func2149 @ ort-wasm-simd.wasm:0x16396e
$func584 @ ort-wasm-simd.wasm:0x48a63
$func11428 @ ort-wasm-simd.wasm:0x8296b1
$func631 @ ort-wasm-simd.wasm:0x4d0e8
v @ ort-web.min.js:7
$func92 @ ort-wasm-simd.wasm:0xb052
$func5739 @ ort-wasm-simd.wasm:0x4799cb
$func140 @ ort-wasm-simd.wasm:0x1064c
$func11064 @ ort-wasm-simd.wasm:0x811d54
$func2505 @ ort-wasm-simd.wasm:0x1b1083
$func734 @ ort-wasm-simd.wasm:0x5f81a
$func1128 @ ort-wasm-simd.wasm:0xa2da5
$func2106 @ ort-wasm-simd.wasm:0x15877a
$func5908 @ ort-wasm-simd.wasm:0x4a6cbe
h @ ort-web.min.js:7
$func5859 @ ort-wasm-simd.wasm:0x492c3a
o @ ort-web.min.js:7
$func5858 @ ort-wasm-simd.wasm:0x492531
$Ra @ ort-wasm-simd.wasm:0x6ebff8
e._OrtCreateSession @ ort-web.min.js:7
e.createSessionFinalize @ ort-web.min.js:7
e.createSession @ ort-web.min.js:7
e.createSession @ ort-web.min.js:7
loadModel @ ort-web.min.js:7
await in loadModel
createSessionHandler @ ort-web.min.js:7
create @ inference-session-impl.js:176
await in create
SileroLegacy.new @ legacy.js:43
await in SileroLegacy.new
new @ real-time-vad.js:172
new @ real-time-vad.js:91
createBrowserVad @ D:\Balaastra\hackothon\project code\frontend\lib\audio-worklet-manager.ts:329
startCapture @ D:\Balaastra\hackothon\project code\frontend\lib\audio-worklet-manager.ts:99
await in startCapture
useNegotiation.useCallback[startNegotiation] @ D:\Balaastra\hackothon\project code\frontend\hooks\useNegotiation.ts:327
await in useNegotiation.useCallback[startNegotiation]
Home.useCallback[handleStartNegotiation] @ D:\Balaastra\hackothon\project code\frontend\app\page.tsx:173
executeDispatch @ react-dom-client.development.js:16971
runWithFiberInDEV @ react-dom-client.development.js:872
processDispatchQueue @ react-dom-client.development.js:17021
eval @ react-dom-client.development.js:17622
batchedUpdates$1 @ react-dom-client.development.js:3312
dispatchEventForPluginEventSystem @ react-dom-client.development.js:17175
dispatchEvent @ react-dom-client.development.js:21358
dispatchDiscreteEvent @ react-dom-client.development.js:21326
ort-wasm-simd.wasm:0x82c2bc 2026-04-07 08:13:02.378300 [W:onnxruntime:, graph.cc:3490 CleanUnusedInitializersAndNodeArgs] Removing initializer '139'. It is not used by any node and should be removed from the model.
lt @ ort-web.min.js:7
P @ ort-web.min.js:7
$func11504 @ ort-wasm-simd.wasm:0x82c2bc
$func2149 @ ort-wasm-simd.wasm:0x16396e
$func584 @ ort-wasm-simd.wasm:0x48a63
$func11428 @ ort-wasm-simd.wasm:0x8296b1
$func631 @ ort-wasm-simd.wasm:0x4d0e8
v @ ort-web.min.js:7
$func92 @ ort-wasm-simd.wasm:0xb052
$func5739 @ ort-wasm-simd.wasm:0x4799cb
$func140 @ ort-wasm-simd.wasm:0x1064c
$func11064 @ ort-wasm-simd.wasm:0x811d54
$func2505 @ ort-wasm-simd.wasm:0x1b1083
$func734 @ ort-wasm-simd.wasm:0x5f81a
$func1128 @ ort-wasm-simd.wasm:0xa2da5
$func2106 @ ort-wasm-simd.wasm:0x15877a
$func5908 @ ort-wasm-simd.wasm:0x4a6cbe
h @ ort-web.min.js:7
$func5859 @ ort-wasm-simd.wasm:0x492c3a
o @ ort-web.min.js:7
$func5858 @ ort-wasm-simd.wasm:0x492531
$Ra @ ort-wasm-simd.wasm:0x6ebff8
e._OrtCreateSession @ ort-web.min.js:7
e.createSessionFinalize @ ort-web.min.js:7
e.createSession @ ort-web.min.js:7
e.createSession @ ort-web.min.js:7
loadModel @ ort-web.min.js:7
await in loadModel
createSessionHandler @ ort-web.min.js:7
create @ inference-session-impl.js:176
await in create
SileroLegacy.new @ legacy.js:43
await in SileroLegacy.new
new @ real-time-vad.js:172
new @ real-time-vad.js:91
createBrowserVad @ D:\Balaastra\hackothon\project code\frontend\lib\audio-worklet-manager.ts:329
startCapture @ D:\Balaastra\hackothon\project code\frontend\lib\audio-worklet-manager.ts:99
await in startCapture
useNegotiation.useCallback[startNegotiation] @ D:\Balaastra\hackothon\project code\frontend\hooks\useNegotiation.ts:327
await in useNegotiation.useCallback[startNegotiation]
Home.useCallback[handleStartNegotiation] @ D:\Balaastra\hackothon\project code\frontend\app\page.tsx:173
executeDispatch @ react-dom-client.development.js:16971
runWithFiberInDEV @ react-dom-client.development.js:872
processDispatchQueue @ react-dom-client.development.js:17021
eval @ react-dom-client.development.js:17622
batchedUpdates$1 @ react-dom-client.development.js:3312
dispatchEventForPluginEventSystem @ react-dom-client.development.js:17175
dispatchEvent @ react-dom-client.development.js:21358
dispatchDiscreteEvent @ react-dom-client.development.js:21326
ort-wasm-simd.wasm:0x82c2bc 2026-04-07 08:13:02.378700 [W:onnxruntime:, graph.cc:3490 CleanUnusedInitializersAndNodeArgs] Removing initializer '136'. It is not used by any node and should be removed from the model.
lt @ ort-web.min.js:7
P @ ort-web.min.js:7
$func11504 @ ort-wasm-simd.wasm:0x82c2bc
$func2149 @ ort-wasm-simd.wasm:0x16396e
$func584 @ ort-wasm-simd.wasm:0x48a63
$func11428 @ ort-wasm-simd.wasm:0x8296b1
$func631 @ ort-wasm-simd.wasm:0x4d0e8
v @ ort-web.min.js:7
$func92 @ ort-wasm-simd.wasm:0xb052
$func5739 @ ort-wasm-simd.wasm:0x4799cb
$func140 @ ort-wasm-simd.wasm:0x1064c
$func11064 @ ort-wasm-simd.wasm:0x811d54
$func2505 @ ort-wasm-simd.wasm:0x1b1083
$func734 @ ort-wasm-simd.wasm:0x5f81a
$func1128 @ ort-wasm-simd.wasm:0xa2da5
$func2106 @ ort-wasm-simd.wasm:0x15877a
$func5908 @ ort-wasm-simd.wasm:0x4a6cbe
h @ ort-web.min.js:7
$func5859 @ ort-wasm-simd.wasm:0x492c3a
o @ ort-web.min.js:7
$func5858 @ ort-wasm-simd.wasm:0x492531
$Ra @ ort-wasm-simd.wasm:0x6ebff8
e._OrtCreateSession @ ort-web.min.js:7
e.createSessionFinalize @ ort-web.min.js:7
e.createSession @ ort-web.min.js:7
e.createSession @ ort-web.min.js:7
loadModel @ ort-web.min.js:7
await in loadModel
createSessionHandler @ ort-web.min.js:7
create @ inference-session-impl.js:176
await in create
SileroLegacy.new @ legacy.js:43
await in SileroLegacy.new
new @ real-time-vad.js:172
new @ real-time-vad.js:91
createBrowserVad @ D:\Balaastra\hackothon\project code\frontend\lib\audio-worklet-manager.ts:329
startCapture @ D:\Balaastra\hackothon\project code\frontend\lib\audio-worklet-manager.ts:99
await in startCapture
useNegotiation.useCallback[startNegotiation] @ D:\Balaastra\hackothon\project code\frontend\hooks\useNegotiation.ts:327
await in useNegotiation.useCallback[startNegotiation]
Home.useCallback[handleStartNegotiation] @ D:\Balaastra\hackothon\project code\frontend\app\page.tsx:173
executeDispatch @ react-dom-client.development.js:16971
runWithFiberInDEV @ react-dom-client.development.js:872
processDispatchQueue @ react-dom-client.development.js:17021
eval @ react-dom-client.development.js:17622
batchedUpdates$1 @ react-dom-client.development.js:3312
dispatchEventForPluginEventSystem @ react-dom-client.development.js:17175
dispatchEvent @ react-dom-client.development.js:21358
dispatchDiscreteEvent @ react-dom-client.development.js:21326
ort-wasm-simd.wasm:0x82c2bc 2026-04-07 08:13:02.379800 [W:onnxruntime:, graph.cc:3490 CleanUnusedInitializersAndNodeArgs] Removing initializer '134'. It is not used by any node and should be removed from the model.
lt @ ort-web.min.js:7
P @ ort-web.min.js:7
$func11504 @ ort-wasm-simd.wasm:0x82c2bc
$func2149 @ ort-wasm-simd.wasm:0x16396e
$func584 @ ort-wasm-simd.wasm:0x48a63
$func11428 @ ort-wasm-simd.wasm:0x8296b1
$func631 @ ort-wasm-simd.wasm:0x4d0e8
v @ ort-web.min.js:7
$func92 @ ort-wasm-simd.wasm:0xb052
$func5739 @ ort-wasm-simd.wasm:0x4799cb
$func140 @ ort-wasm-simd.wasm:0x1064c
$func11064 @ ort-wasm-simd.wasm:0x811d54
$func2505 @ ort-wasm-simd.wasm:0x1b1083
$func734 @ ort-wasm-simd.wasm:0x5f81a
$func1128 @ ort-wasm-simd.wasm:0xa2da5
$func2106 @ ort-wasm-simd.wasm:0x15877a
$func5908 @ ort-wasm-simd.wasm:0x4a6cbe
h @ ort-web.min.js:7
$func5859 @ ort-wasm-simd.wasm:0x492c3a
o @ ort-web.min.js:7
$func5858 @ ort-wasm-simd.wasm:0x492531
$Ra @ ort-wasm-simd.wasm:0x6ebff8
e._OrtCreateSession @ ort-web.min.js:7
e.createSessionFinalize @ ort-web.min.js:7
e.createSession @ ort-web.min.js:7
e.createSession @ ort-web.min.js:7
loadModel @ ort-web.min.js:7
await in loadModel
createSessionHandler @ ort-web.min.js:7
create @ inference-session-impl.js:176
await in create
SileroLegacy.new @ legacy.js:43
await in SileroLegacy.new
new @ real-time-vad.js:172
new @ real-time-vad.js:91
createBrowserVad @ D:\Balaastra\hackothon\project code\frontend\lib\audio-worklet-manager.ts:329
startCapture @ D:\Balaastra\hackothon\project code\frontend\lib\audio-worklet-manager.ts:99
await in startCapture
useNegotiation.useCallback[startNegotiation] @ D:\Balaastra\hackothon\project code\frontend\hooks\useNegotiation.ts:327
await in useNegotiation.useCallback[startNegotiation]
Home.useCallback[handleStartNegotiation] @ D:\Balaastra\hackothon\project code\frontend\app\page.tsx:173
executeDispatch @ react-dom-client.development.js:16971
runWithFiberInDEV @ react-dom-client.development.js:872
processDispatchQueue @ react-dom-client.development.js:17021
eval @ react-dom-client.development.js:17622
batchedUpdates$1 @ react-dom-client.development.js:3312
dispatchEventForPluginEventSystem @ react-dom-client.development.js:17175
dispatchEvent @ react-dom-client.development.js:21358
dispatchDiscreteEvent @ react-dom-client.development.js:21326
ort-wasm-simd.wasm:0x82c2bc 2026-04-07 08:13:02.381400 [W:onnxruntime:, graph.cc:3490 CleanUnusedInitializersAndNodeArgs] Removing initializer '628'. It is not used by any node and should be removed from the model.
lt @ ort-web.min.js:7
P @ ort-web.min.js:7
$func11504 @ ort-wasm-simd.wasm:0x82c2bc
$func2149 @ ort-wasm-simd.wasm:0x16396e
$func584 @ ort-wasm-simd.wasm:0x48a63
$func11428 @ ort-wasm-simd.wasm:0x8296b1
$func631 @ ort-wasm-simd.wasm:0x4d0e8
v @ ort-web.min.js:7
$func92 @ ort-wasm-simd.wasm:0xb052
$func5739 @ ort-wasm-simd.wasm:0x4799cb
$func140 @ ort-wasm-simd.wasm:0x1064c
$func11064 @ ort-wasm-simd.wasm:0x811d54
$func2505 @ ort-wasm-simd.wasm:0x1b1083
$func734 @ ort-wasm-simd.wasm:0x5f81a
$func1128 @ ort-wasm-simd.wasm:0xa2da5
$func2106 @ ort-wasm-simd.wasm:0x15877a
$func5908 @ ort-wasm-simd.wasm:0x4a6cbe
h @ ort-web.min.js:7
$func5859 @ ort-wasm-simd.wasm:0x492c3a
o @ ort-web.min.js:7
$func5858 @ ort-wasm-simd.wasm:0x492531
$Ra @ ort-wasm-simd.wasm:0x6ebff8
e._OrtCreateSession @ ort-web.min.js:7
e.createSessionFinalize @ ort-web.min.js:7
e.createSession @ ort-web.min.js:7
e.createSession @ ort-web.min.js:7
loadModel @ ort-web.min.js:7
await in loadModel
createSessionHandler @ ort-web.min.js:7
create @ inference-session-impl.js:176
await in create
SileroLegacy.new @ legacy.js:43
await in SileroLegacy.new
new @ real-time-vad.js:172
new @ real-time-vad.js:91
createBrowserVad @ D:\Balaastra\hackothon\project code\frontend\lib\audio-worklet-manager.ts:329
startCapture @ D:\Balaastra\hackothon\project code\frontend\lib\audio-worklet-manager.ts:99
await in startCapture
useNegotiation.useCallback[startNegotiation] @ D:\Balaastra\hackothon\project code\frontend\hooks\useNegotiation.ts:327
await in useNegotiation.useCallback[startNegotiation]
Home.useCallback[handleStartNegotiation] @ D:\Balaastra\hackothon\project code\frontend\app\page.tsx:173
executeDispatch @ react-dom-client.development.js:16971
runWithFiberInDEV @ react-dom-client.development.js:872
processDispatchQueue @ react-dom-client.development.js:17021
eval @ react-dom-client.development.js:17622
batchedUpdates$1 @ react-dom-client.development.js:3312
dispatchEventForPluginEventSystem @ react-dom-client.development.js:17175
dispatchEvent @ react-dom-client.development.js:21358
dispatchDiscreteEvent @ react-dom-client.development.js:21326
ort-wasm-simd.wasm:0x82c2bc 2026-04-07 08:13:02.383600 [W:onnxruntime:, graph.cc:3490 CleanUnusedInitializersAndNodeArgs] Removing initializer '625'. It is not used by any node and should be removed from the model.
lt @ ort-web.min.js:7
P @ ort-web.min.js:7
$func11504 @ ort-wasm-simd.wasm:0x82c2bc
$func2149 @ ort-wasm-simd.wasm:0x16396e
$func584 @ ort-wasm-simd.wasm:0x48a63
$func11428 @ ort-wasm-simd.wasm:0x8296b1
$func631 @ ort-wasm-simd.wasm:0x4d0e8
v @ ort-web.min.js:7
$func92 @ ort-wasm-simd.wasm:0xb052
$func5739 @ ort-wasm-simd.wasm:0x4799cb
$func140 @ ort-wasm-simd.wasm:0x1064c
$func11064 @ ort-wasm-simd.wasm:0x811d54
$func2505 @ ort-wasm-simd.wasm:0x1b1083
$func734 @ ort-wasm-simd.wasm:0x5f81a
$func1128 @ ort-wasm-simd.wasm:0xa2da5
$func2106 @ ort-wasm-simd.wasm:0x15877a
$func5908 @ ort-wasm-simd.wasm:0x4a6cbe
h @ ort-web.min.js:7
$func5859 @ ort-wasm-simd.wasm:0x492c3a
o @ ort-web.min.js:7
$func5858 @ ort-wasm-simd.wasm:0x492531
$Ra @ ort-wasm-simd.wasm:0x6ebff8
e._OrtCreateSession @ ort-web.min.js:7
e.createSessionFinalize @ ort-web.min.js:7
e.createSession @ ort-web.min.js:7
e.createSession @ ort-web.min.js:7
loadModel @ ort-web.min.js:7
await in loadModel
createSessionHandler @ ort-web.min.js:7
create @ inference-session-impl.js:176
await in create
SileroLegacy.new @ legacy.js:43
await in SileroLegacy.new
new @ real-time-vad.js:172
new @ real-time-vad.js:91
createBrowserVad @ D:\Balaastra\hackothon\project code\frontend\lib\audio-worklet-manager.ts:329
startCapture @ D:\Balaastra\hackothon\project code\frontend\lib\audio-worklet-manager.ts:99
await in startCapture
useNegotiation.useCallback[startNegotiation] @ D:\Balaastra\hackothon\project code\frontend\hooks\useNegotiation.ts:327
await in useNegotiation.useCallback[startNegotiation]
Home.useCallback[handleStartNegotiation] @ D:\Balaastra\hackothon\project code\frontend\app\page.tsx:173
executeDispatch @ react-dom-client.development.js:16971
runWithFiberInDEV @ react-dom-client.development.js:872
processDispatchQueue @ react-dom-client.development.js:17021
eval @ react-dom-client.development.js:17622
batchedUpdates$1 @ react-dom-client.development.js:3312
dispatchEventForPluginEventSystem @ react-dom-client.development.js:17175
dispatchEvent @ react-dom-client.development.js:21358
dispatchDiscreteEvent @ react-dom-client.development.js:21326
ort-wasm-simd.wasm:0x82c2bc 2026-04-07 08:13:02.384900 [W:onnxruntime:, graph.cc:3490 CleanUnusedInitializersAndNodeArgs] Removing initializer '623'. It is not used by any node and should be removed from the model.
lt @ ort-web.min.js:7
P @ ort-web.min.js:7
$func11504 @ ort-wasm-simd.wasm:0x82c2bc
$func2149 @ ort-wasm-simd.wasm:0x16396e
$func584 @ ort-wasm-simd.wasm:0x48a63
$func11428 @ ort-wasm-simd.wasm:0x8296b1
$func631 @ ort-wasm-simd.wasm:0x4d0e8
v @ ort-web.min.js:7
$func92 @ ort-wasm-simd.wasm:0xb052
$func5739 @ ort-wasm-simd.wasm:0x4799cb
$func140 @ ort-wasm-simd.wasm:0x1064c
$func11064 @ ort-wasm-simd.wasm:0x811d54
$func2505 @ ort-wasm-simd.wasm:0x1b1083
$func734 @ ort-wasm-simd.wasm:0x5f81a
$func1128 @ ort-wasm-simd.wasm:0xa2da5
$func2106 @ ort-wasm-simd.wasm:0x15877a
$func5908 @ ort-wasm-simd.wasm:0x4a6cbe
h @ ort-web.min.js:7
$func5859 @ ort-wasm-simd.wasm:0x492c3a
o @ ort-web.min.js:7
$func5858 @ ort-wasm-simd.wasm:0x492531
$Ra @ ort-wasm-simd.wasm:0x6ebff8
e._OrtCreateSession @ ort-web.min.js:7
e.createSessionFinalize @ ort-web.min.js:7
e.createSession @ ort-web.min.js:7
e.createSession @ ort-web.min.js:7
loadModel @ ort-web.min.js:7
await in loadModel
createSessionHandler @ ort-web.min.js:7
create @ inference-session-impl.js:176
await in create
SileroLegacy.new @ legacy.js:43
await in SileroLegacy.new
new @ real-time-vad.js:172
new @ real-time-vad.js:91
createBrowserVad @ D:\Balaastra\hackothon\project code\frontend\lib\audio-worklet-manager.ts:329
startCapture @ D:\Balaastra\hackothon\project code\frontend\lib\audio-worklet-manager.ts:99
await in startCapture
useNegotiation.useCallback[startNegotiation] @ D:\Balaastra\hackothon\project code\frontend\hooks\useNegotiation.ts:327
await in useNegotiation.useCallback[startNegotiation]
Home.useCallback[handleStartNegotiation] @ D:\Balaastra\hackothon\project code\frontend\app\page.tsx:173
executeDispatch @ react-dom-client.development.js:16971
runWithFiberInDEV @ react-dom-client.development.js:872
processDispatchQueue @ react-dom-client.development.js:17021
eval @ react-dom-client.development.js:17622
batchedUpdates$1 @ react-dom-client.development.js:3312
dispatchEventForPluginEventSystem @ react-dom-client.development.js:17175
dispatchEvent @ react-dom-client.development.js:21358
dispatchDiscreteEvent @ react-dom-client.development.js:21326
ort-wasm-simd.wasm:0x82c2bc 2026-04-07 08:13:02.389600 [W:onnxruntime:, graph.cc:3490 CleanUnusedInitializersAndNodeArgs] Removing initializer '629'. It is not used by any node and should be removed from the model.
lt @ ort-web.min.js:7
P @ ort-web.min.js:7
$func11504 @ ort-wasm-simd.wasm:0x82c2bc
$func2149 @ ort-wasm-simd.wasm:0x16396e
$func584 @ ort-wasm-simd.wasm:0x48a63
$func11428 @ ort-wasm-simd.wasm:0x8296b1
$func631 @ ort-wasm-simd.wasm:0x4d0e8
v @ ort-web.min.js:7
$func92 @ ort-wasm-simd.wasm:0xb052
$func5739 @ ort-wasm-simd.wasm:0x4799cb
$func140 @ ort-wasm-simd.wasm:0x1064c
$func11064 @ ort-wasm-simd.wasm:0x811d54
$func2505 @ ort-wasm-simd.wasm:0x1b1083
$func734 @ ort-wasm-simd.wasm:0x5f81a
$func1128 @ ort-wasm-simd.wasm:0xa2da5
$func2106 @ ort-wasm-simd.wasm:0x15877a
$func5908 @ ort-wasm-simd.wasm:0x4a6cbe
h @ ort-web.min.js:7
$func5859 @ ort-wasm-simd.wasm:0x492c3a
o @ ort-web.min.js:7
$func5858 @ ort-wasm-simd.wasm:0x492531
$Ra @ ort-wasm-simd.wasm:0x6ebff8
e._OrtCreateSession @ ort-web.min.js:7
e.createSessionFinalize @ ort-web.min.js:7
e.createSession @ ort-web.min.js:7
e.createSession @ ort-web.min.js:7
loadModel @ ort-web.min.js:7
await in loadModel
createSessionHandler @ ort-web.min.js:7
create @ inference-session-impl.js:176
await in create
SileroLegacy.new @ legacy.js:43
await in SileroLegacy.new
new @ real-time-vad.js:172
new @ real-time-vad.js:91
createBrowserVad @ D:\Balaastra\hackothon\project code\frontend\lib\audio-worklet-manager.ts:329
startCapture @ D:\Balaastra\hackothon\project code\frontend\lib\audio-worklet-manager.ts:99
await in startCapture
useNegotiation.useCallback[startNegotiation] @ D:\Balaastra\hackothon\project code\frontend\hooks\useNegotiation.ts:327
await in useNegotiation.useCallback[startNegotiation]
Home.useCallback[handleStartNegotiation] @ D:\Balaastra\hackothon\project code\frontend\app\page.tsx:173
executeDispatch @ react-dom-client.development.js:16971
runWithFiberInDEV @ react-dom-client.development.js:872
processDispatchQueue @ react-dom-client.development.js:17021
eval @ react-dom-client.development.js:17622
batchedUpdates$1 @ react-dom-client.development.js:3312
dispatchEventForPluginEventSystem @ react-dom-client.development.js:17175
dispatchEvent @ react-dom-client.development.js:21358
dispatchDiscreteEvent @ react-dom-client.development.js:21326
ort-wasm-simd.wasm:0x82c2bc 2026-04-07 08:13:02.392000 [W:onnxruntime:, graph.cc:3490 CleanUnusedInitializersAndNodeArgs] Removing initializer '620'. It is not used by any node and should be removed from the model.
lt @ ort-web.min.js:7
P @ ort-web.min.js:7
$func11504 @ ort-wasm-simd.wasm:0x82c2bc
$func2149 @ ort-wasm-simd.wasm:0x16396e
$func584 @ ort-wasm-simd.wasm:0x48a63
$func11428 @ ort-wasm-simd.wasm:0x8296b1
$func631 @ ort-wasm-simd.wasm:0x4d0e8
v @ ort-web.min.js:7
$func92 @ ort-wasm-simd.wasm:0xb052
$func5739 @ ort-wasm-simd.wasm:0x4799cb
$func140 @ ort-wasm-simd.wasm:0x1064c
$func11064 @ ort-wasm-simd.wasm:0x811d54
$func2505 @ ort-wasm-simd.wasm:0x1b1083
$func734 @ ort-wasm-simd.wasm:0x5f81a
$func1128 @ ort-wasm-simd.wasm:0xa2da5
$func2106 @ ort-wasm-simd.wasm:0x15877a
$func5908 @ ort-wasm-simd.wasm:0x4a6cbe
h @ ort-web.min.js:7
$func5859 @ ort-wasm-simd.wasm:0x492c3a
o @ ort-web.min.js:7
$func5858 @ ort-wasm-simd.wasm:0x492531
$Ra @ ort-wasm-simd.wasm:0x6ebff8
e._OrtCreateSession @ ort-web.min.js:7
e.createSessionFinalize @ ort-web.min.js:7
e.createSession @ ort-web.min.js:7
e.createSession @ ort-web.min.js:7
loadModel @ ort-web.min.js:7
await in loadModel
createSessionHandler @ ort-web.min.js:7
create @ inference-session-impl.js:176
await in create
SileroLegacy.new @ legacy.js:43
await in SileroLegacy.new
new @ real-time-vad.js:172
new @ real-time-vad.js:91
createBrowserVad @ D:\Balaastra\hackothon\project code\frontend\lib\audio-worklet-manager.ts:329
startCapture @ D:\Balaastra\hackothon\project code\frontend\lib\audio-worklet-manager.ts:99
await in startCapture
useNegotiation.useCallback[startNegotiation] @ D:\Balaastra\hackothon\project code\frontend\hooks\useNegotiation.ts:327
await in useNegotiation.useCallback[startNegotiation]
Home.useCallback[handleStartNegotiation] @ D:\Balaastra\hackothon\project code\frontend\app\page.tsx:173
executeDispatch @ react-dom-client.development.js:16971
runWithFiberInDEV @ react-dom-client.development.js:872
processDispatchQueue @ react-dom-client.development.js:17021
eval @ react-dom-client.development.js:17622
batchedUpdates$1 @ react-dom-client.development.js:3312
dispatchEventForPluginEventSystem @ react-dom-client.development.js:17175
dispatchEvent @ react-dom-client.development.js:21358
dispatchDiscreteEvent @ react-dom-client.development.js:21326
logging.js:8 [VAD] vad is initialized
D:\Balaastra\hackothon\project code\frontend\lib\websocket.ts:133 [WebSocket] sendControl called: START_NEGOTIATION {context: '', user_context: {…}}
D:\Balaastra\hackothon\project code\frontend\lib\websocket.ts:136 [WebSocket] Sending: {"type":"START_NEGOTIATION","payload":{"context":"","user_context":{}}}
D:\Balaastra\hackothon\project code\frontend\hooks\useNegotiation.ts:234 NEGOTIATION_STATE_CHANGED: {previous_state: 'CONSENTED', current_state: 'ACTIVE', timestamp: 1775529783.5388405}
real-time-vad.js:255 [Violation] 'message' handler took 169ms
logging.js:8 [VAD] Detected real speech start
D:\Balaastra\hackothon\project code\frontend\lib\websocket.ts:133 [WebSocket] sendControl called: UTTERANCE_END {utterance_id: '8f248ac2-44b1-48dd-8eaf-39b8c386a984', started_at: 1775529803.003, ended_at: 1775529807.612, duration_ms: 4609, rms: 3258.305519169435}
D:\Balaastra\hackothon\project code\frontend\lib\websocket.ts:136 [WebSocket] Sending: {"type":"UTTERANCE_END","payload":{"utterance_id":"8f248ac2-44b1-48dd-8eaf-39b8c386a984","started_at":1775529803.003,"ended_at":1775529807.612,"duration_ms":4609,"rms":3258.305519169435}}
logging.js:8 [VAD] Detected real speech start
D:\Balaastra\hackothon\project code\frontend\lib\websocket.ts:133 [WebSocket] sendControl called: UTTERANCE_END {utterance_id: '14c1c1c9-9d5f-4936-9126-fa0b786089fa', started_at: 1775529822.488, ended_at: 1775529826.622, duration_ms: 4134, rms: 3382.5486020159415}
D:\Balaastra\hackothon\project code\frontend\lib\websocket.ts:136 [WebSocket] Sending: {"type":"UTTERANCE_END","payload":{"utterance_id":"14c1c1c9-9d5f-4936-9126-fa0b786089fa","started_at":1775529822.488,"ended_at":1775529826.622,"duration_ms":4134,"rms":3382.5486020159415}}
logging.js:8 [VAD] Detected real speech start
D:\Balaastra\hackothon\project code\frontend\lib\websocket.ts:133 [WebSocket] sendControl called: UTTERANCE_END {utterance_id: 'f2deaa48-fa8b-4e64-a85a-fa2a5b56898f', started_at: 1775529865.88, ended_at: 1775529869.531, duration_ms: 3651, rms: 2731.3361004735393}
D:\Balaastra\hackothon\project code\frontend\lib\websocket.ts:136 [WebSocket] Sending: {"type":"UTTERANCE_END","payload":{"utterance_id":"f2deaa48-fa8b-4e64-a85a-fa2a5b56898f","started_at":1775529865.88,"ended_at":1775529869.531,"duration_ms":3651,"rms":2731.3361004735393}}
logging.js:8 [VAD] Detected real speech start
D:\Balaastra\hackothon\project code\frontend\lib\websocket.ts:133 [WebSocket] sendControl called: UTTERANCE_END {utterance_id: '02d1d093-f01b-4737-ab8a-becff8523cb1', started_at: 1775529878.645, ended_at: 1775529882.296, duration_ms: 3651, rms: 2347.0387534082174}
D:\Balaastra\hackothon\project code\frontend\lib\websocket.ts:136 [WebSocket] Sending: {"type":"UTTERANCE_END","payload":{"utterance_id":"02d1d093-f01b-4737-ab8a-becff8523cb1","started_at":1775529878.645,"ended_at":1775529882.296,"duration_ms":3651,"rms":2347.0387534082174}}
scheduler.development.js:14 [Violation] 'message' handler took 183ms
logging.js:8 [VAD] Detected real speech start
D:\Balaastra\hackothon\project code\frontend\lib\websocket.ts:133 [WebSocket] sendControl called: UTTERANCE_END {utterance_id: 'e3b6a623-e614-4b3d-9fb6-6a57a003e8d5', started_at: 1775529908.115, ended_at: 1775529912.058, duration_ms: 3943, rms: 2297.493510872229}
D:\Balaastra\hackothon\project code\frontend\lib\websocket.ts:136 [WebSocket] Sending: {"type":"UTTERANCE_END","payload":{"utterance_id":"e3b6a623-e614-4b3d-9fb6-6a57a003e8d5","started_at":1775529908.115,"ended_at":1775529912.058,"duration_ms":3943,"rms":2297.493510872229}}
logging.js:8 [VAD] Detected real speech start
D:\Balaastra\hackothon\project code\frontend\lib\websocket.ts:133 [WebSocket] sendControl called: UTTERANCE_END {utterance_id: '0a990b50-0876-4f4a-8742-1b102e754ff8', started_at: 1775529921.177, ended_at: 1775529925.017, duration_ms: 3840, rms: 2546.4643670194955}
D:\Balaastra\hackothon\project code\frontend\lib\websocket.ts:136 [WebSocket] Sending: {"type":"UTTERANCE_END","payload":{"utterance_id":"0a990b50-0876-4f4a-8742-1b102e754ff8","started_at":1775529921.177,"ended_at":1775529925.017,"duration_ms":3840,"rms":2546.4643670194955}}