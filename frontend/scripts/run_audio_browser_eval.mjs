import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright-core";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const FRONTEND_ROOT = path.resolve(__dirname, "..");
const PROJECT_ROOT = path.resolve(FRONTEND_ROOT, "..");
const BACKEND_ROOT = path.join(PROJECT_ROOT, "backend");

const args = parseArgs(process.argv.slice(2));
const manifestPath = path.resolve(args.manifest || path.join(BACKEND_ROOT, "evals", "audio_fixtures", "manifest.json"));
const frontendUrl = args.frontendUrl || process.env.AUDIO_EVAL_FRONTEND_URL || "http://localhost:3000";
const outRoot = path.resolve(args.outDir || path.join(BACKEND_ROOT, "data", "audio_eval_reports", "browser"));
const transcriptTimeoutMs = Number(args.transcriptTimeoutMs || 30000);
const runId = timestampRunId();

if (!fs.existsSync(manifestPath)) {
  console.error(`Audio manifest not found: ${manifestPath}`);
  process.exit(1);
}

const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf-8"));
let scenarios = manifest.scenarios || [];
if (args.scenarioId?.length) {
  const selected = new Set(args.scenarioId);
  scenarios = scenarios.filter((scenario) => selected.has(scenario.id));
}
if (args.limit) {
  scenarios = scenarios.slice(0, Number(args.limit));
}
if (!scenarios.length) {
  console.error("No audio scenarios selected.");
  process.exit(1);
}

const browserExecutable = resolveEdgeExecutable();
if (!browserExecutable) {
  console.error("Microsoft Edge executable not found.");
  process.exit(1);
}

const runDir = path.join(outRoot, runId);
fs.mkdirSync(runDir, { recursive: true });

const summaryTurns = [];
const summaryScenarios = [];

const browser = await chromium.launch({
  headless: true,
  executablePath: browserExecutable,
});

try {
  for (const scenario of scenarios) {
    console.log(`RUN ${scenario.id}`);
    const context = await browser.newContext();
    const page = await context.newPage();
    await page.addInitScript(initAudioEvalScript);
    await page.goto(frontendUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(1500);

    const scenarioTurns = [];
    const scenarioEvents = [];
    try {
      await acceptConsentAndOpenEnrollment(page);

      const enrollmentAudio = loadBase64Audio(path.join(path.dirname(manifestPath), scenario.enrollment_audio_path));
      await page.evaluate(async (b64) => {
        await window.__audioEvalPlayBase64(b64);
      }, enrollmentAudio);

      await finishEnrollmentAndStartSession(page);
      await page.getByRole("button", { name: /Start Session/i }).click({ timeout: 30000 });
      await page.getByRole("button", { name: /End Session/i }).waitFor({ timeout: 30000, state: "visible" });
      await page.waitForTimeout(1200);

      for (let index = 0; index < scenario.turns.length; index += 1) {
        const turn = scenario.turns[index];
        await page.evaluate(() => window.__audioEvalClearTurnWindow());
        const audioBase64 = loadBase64Audio(path.join(path.dirname(manifestPath), turn.audio_path));
        await page.evaluate(async (b64) => {
          await window.__audioEvalPlayBase64(b64);
        }, audioBase64);

        const observed = await waitForTranscriptWindow(page, transcriptTimeoutMs);
        scenarioTurns.push(scoreTurn({
          scenario,
          turn,
          observed,
        }));
      }

      await page.getByRole("button", { name: /End Session/i }).click({ timeout: 20000 }).catch(() => {});
      scenarioEvents.push(await page.evaluate(() => window.__audioEvalSnapshot()));

      const scenarioReport = buildScenarioReport({
        runId,
        manifestId: manifest.manifest_id,
        scenario,
        turns: scenarioTurns,
        suite: "audio_browser_eval",
        events: scenarioEvents,
      });
      fs.writeFileSync(path.join(runDir, `${scenario.id}.json`), JSON.stringify(scenarioReport, null, 2) + "\n");
      summaryTurns.push(...scenarioTurns);
      summaryScenarios.push({
        id: scenario.id,
        voice_pair_id: scenario.voice_pair_id,
        condition: scenario.condition,
      });
      console.log(
        `DONE ${scenario.id} speaker_accuracy=${scenarioReport.summary.speaker_accuracy.toFixed(3)} wer_mean=${scenarioReport.summary.wer_mean} pass=${scenarioReport.summary.pass}`
      );
    } finally {
      await context.close();
    }
  }

  const summary = buildAggregateReport({
    runId,
    manifestId: manifest.manifest_id,
    suite: "audio_browser_eval",
    scenarios: summaryScenarios,
    turns: summaryTurns,
  });
  fs.writeFileSync(path.join(runDir, "summary.json"), JSON.stringify(summary, null, 2) + "\n");
  console.log(`REPORT ${runDir}`);
  process.exit(summary.summary.pass ? 0 : 1);
} finally {
  await browser.close();
}

function parseArgs(argv) {
  const result = { scenarioId: [] };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const next = argv[i + 1];
    if (arg === "--manifest") result.manifest = next, i += 1;
    else if (arg === "--frontend-url") result.frontendUrl = next, i += 1;
    else if (arg === "--out-dir") result.outDir = next, i += 1;
    else if (arg === "--limit") result.limit = next, i += 1;
    else if (arg === "--scenario-id") result.scenarioId.push(next), i += 1;
    else if (arg === "--transcript-timeout-ms") result.transcriptTimeoutMs = next, i += 1;
  }
  return result;
}

function resolveEdgeExecutable() {
  const candidates = [
    process.env.MSEDGE_PATH,
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
  ].filter(Boolean);
  return candidates.find((candidate) => fs.existsSync(candidate)) || null;
}

function loadBase64Audio(filePath) {
  return fs.readFileSync(filePath).toString("base64");
}

async function acceptConsentAndOpenEnrollment(page) {
  const consentButton = page.getByRole("button", { name: "I Understand and Consent" });
  for (let attempt = 0; attempt < 3; attempt += 1) {
    await consentButton.click({ timeout: 30000 });
    try {
      await page.getByRole("button", { name: "Start Enrollment" }).waitFor({ timeout: 8000, state: "visible" });
      await page.getByRole("button", { name: "Start Enrollment" }).click({ timeout: 30000 });
      return;
    } catch (_error) {
      await page.waitForTimeout(1000);
    }
  }

  const buttonTexts = await page.locator("button").allTextContents();
  const body = await page.locator("body").innerText();
  throw new Error(
    `Failed to reach enrollment modal after consent. Buttons=${JSON.stringify(buttonTexts)} Body=${JSON.stringify(body.slice(0, 2000))}`
  );
}

async function finishEnrollmentAndStartSession(page) {
  const continueButton = page.getByRole("button", { name: "Continue" });
  const startSessionButton = page.getByRole("button", { name: /Start Session/i });
  const enrollmentHeading = page.getByText("Voice Enrollment", { exact: true });
  const deadline = Date.now() + 45000;

  while (Date.now() < deadline) {
    if (await continueButton.isVisible().catch(() => false)) {
      await continueButton.click({ timeout: 5000 });
      await enrollmentHeading.waitFor({ state: "hidden", timeout: 10000 }).catch(() => {});
      return;
    }
    const modalVisible = await enrollmentHeading.isVisible().catch(() => false);
    if (!modalVisible && await startSessionButton.isVisible().catch(() => false)) {
      return;
    }
    await page.waitForTimeout(500);
  }

  const buttonTexts = await page.locator("button").allTextContents();
  const body = await page.locator("body").innerText();
  throw new Error(
    `Enrollment did not reach a continueable state. Buttons=${JSON.stringify(buttonTexts)} Body=${JSON.stringify(body.slice(0, 2000))}`
  );
}

async function waitForTranscriptWindow(page, timeoutMs) {
  const started = Date.now();
  while ((Date.now() - started) < timeoutMs) {
    const snapshot = await page.evaluate(() => window.__audioEvalSnapshot());
    const turnWindow = snapshot.turnWindow || {};
    const transcripts = turnWindow.transcripts || [];
    const utteranceEnds = turnWindow.utteranceEnds || [];
    if (utteranceEnds.length > 0) {
      const lastUtteranceEndAt = utteranceEnds[utteranceEnds.length - 1].capturedAt;
      const transcriptsAfterLastEnd = transcripts.filter((entry) => entry.capturedAt >= lastUtteranceEndAt);
      if (transcriptsAfterLastEnd.length > 0) {
        const timestamps = [
          ...utteranceEnds.map((entry) => entry.capturedAt),
          ...transcriptsAfterLastEnd.map((entry) => entry.capturedAt),
        ].filter(Boolean);
        const lastActivityAt = timestamps.length ? Math.max(...timestamps) : null;
        if (lastActivityAt && (Date.now() - lastActivityAt) > 1500) {
          return turnWindow;
        }
      }
    } else if (transcripts.length > 0) {
      const lastTranscriptAt = transcripts[transcripts.length - 1].capturedAt;
      if ((Date.now() - lastTranscriptAt) > 1500) {
        return turnWindow;
      }
    }
    await page.waitForTimeout(150);
  }
  return await page.evaluate(() => window.__audioEvalSnapshot().turnWindow);
}

function normalizeText(value) {
  return String(value || "").replace(/\s+/g, " ").trim();
}

function tokenize(value) {
  return normalizeText(value).toLowerCase().match(/[a-z0-9]+(?:[.-][a-z0-9]+)?/g) || [];
}

function numberTokens(value) {
  return normalizeText(value).toLowerCase().match(/\d+(?:[.,]\d+)?/g) || [];
}

function levenshtein(ref, hyp) {
  const m = ref.length;
  const n = hyp.length;
  const dp = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0));
  for (let i = 0; i <= m; i += 1) dp[i][0] = i;
  for (let j = 0; j <= n; j += 1) dp[0][j] = j;
  for (let i = 1; i <= m; i += 1) {
    for (let j = 1; j <= n; j += 1) {
      if (ref[i - 1] === hyp[j - 1]) dp[i][j] = dp[i - 1][j - 1];
      else dp[i][j] = 1 + Math.min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1]);
    }
  }
  return dp[m][n];
}

function wordErrorRate(reference, hypothesis) {
  const ref = tokenize(reference);
  const hyp = tokenize(hypothesis);
  if (!ref.length) return hyp.length ? 1.0 : 0.0;
  return Number((levenshtein(ref, hyp) / ref.length).toFixed(4));
}

function edgeDrop(reference, hypothesis) {
  const ref = tokenize(reference);
  const hyp = tokenize(hypothesis);
  if (!ref.length) {
    return { leading_word_drop: false, trailing_word_drop: false, leading_drop_count: 0, trailing_drop_count: 0 };
  }
  const leading = !hyp.length || ref[0] !== hyp[0];
  const trailing = !hyp.length || ref[ref.length - 1] !== hyp[hyp.length - 1];
  return {
    leading_word_drop: leading,
    trailing_word_drop: trailing,
    leading_drop_count: leading ? 1 : 0,
    trailing_drop_count: trailing ? 1 : 0,
  };
}

function scoreTurn({ scenario, turn, observed }) {
  const transcripts = observed?.transcripts || [];
  const utteranceEnds = observed?.utteranceEnds || [];
  const audioChunkCount = Number(observed?.audioChunkCount || 0);
  const speakers = Array.from(new Set(transcripts.map((entry) => entry.speaker).filter(Boolean)));
  const observedSpeaker = speakers.length === 1 ? speakers[0] : (speakers.length > 1 ? "mixed" : null);
  const observedText = normalizeText(transcripts.map((entry) => entry.text).join(" "));
  const expectedText = turn.text;
  const timeout = transcripts.length === 0;
  const failure = classifyTurnFailure({
    transcripts,
    utteranceEnds,
    observedSpeaker,
    expectedSpeaker: turn.speaker,
    audioChunkCount,
  });
  const lastUtteranceEnd = utteranceEnds[utteranceEnds.length - 1];
  const firstTranscript = transcripts[0];
  const latencyMs = lastUtteranceEnd && firstTranscript ? Number((firstTranscript.capturedAt - lastUtteranceEnd.capturedAt).toFixed(2)) : null;
  const edge = edgeDrop(expectedText, observedText);
  const expectedNumbers = numberTokens(expectedText);
  const observedNumbers = numberTokens(observedText);
  const observedCounter = new Map();
  observedNumbers.forEach((number) => observedCounter.set(number, (observedCounter.get(number) || 0) + 1));
  const hits = [];
  const misses = [];
  expectedNumbers.forEach((number) => {
    const count = observedCounter.get(number) || 0;
    if (count > 0) {
      hits.push(number);
      observedCounter.set(number, count - 1);
    } else {
      misses.push(number);
    }
  });

  return {
    fixture_id: turn.fixture_id,
    scenario_id: scenario.id,
    voice_pair_id: scenario.voice_pair_id,
    condition: scenario.condition,
    expected_speaker: turn.speaker,
    observed_speaker: observedSpeaker,
    speaker_correct: observedSpeaker === turn.speaker,
    wrong_label: Boolean(observedSpeaker && observedSpeaker !== turn.speaker),
    missing_transcript: !observedText,
    timeout,
    failure_kind: failure.kind,
    failure_reason: failure.reason,
    expected_text: expectedText,
    observed_text: observedText,
    wer: wordErrorRate(expectedText, observedText),
    number_recall: {
      expected: expectedNumbers,
      observed: observedNumbers,
      hits,
      misses,
      recall: expectedNumbers.length ? Number((hits.length / expectedNumbers.length).toFixed(4)) : 1.0,
    },
    leading_word_drop: edge.leading_word_drop,
    trailing_word_drop: edge.trailing_word_drop,
    leading_drop_count: edge.leading_drop_count,
    trailing_drop_count: edge.trailing_drop_count,
    transcript_count: transcripts.length,
    latency_ms: latencyMs,
    speaker_confidence: null,
    stage_markers: observed?.wsEvents?.map((event) => event.type) || [],
    metadata: {
      condition_tags: turn.condition_tags || [],
      group: turn.group,
      transcript_payloads: transcripts,
      utterance_end_payloads: utteranceEnds,
      audio_chunk_count: audioChunkCount,
    },
  };
}

function classifyTurnFailure({ transcripts, utteranceEnds, observedSpeaker, expectedSpeaker, audioChunkCount = 0 }) {
  if (transcripts.length > 0) {
    if (observedSpeaker && observedSpeaker !== expectedSpeaker) {
      return { kind: "wrong_label", reason: `Observed speaker ${observedSpeaker} does not match expected ${expectedSpeaker}.` };
    }
    return { kind: null, reason: null };
  }
  if (utteranceEnds.length === 0) {
    if (audioChunkCount === 0) {
      return { kind: "vad_boundary_miss", reason: "Frontend capture never streamed AUDIO_CHUNK for this fixture." };
    }
    return { kind: "vad_boundary_miss", reason: "Frontend streamed audio but never emitted UTTERANCE_END for this fixture." };
  }
  return { kind: "pipeline_timeout", reason: "Frontend emitted UTTERANCE_END but no transcript arrived before timeout." };
}

function aggregateTurns(turns, { suite, runId, extra = {} }) {
  const total = turns.length;
  const speakerCorrect = turns.filter((turn) => turn.speaker_correct).length;
  const falseUserCount = turns.filter((turn) => turn.observed_speaker === "user" && turn.expected_speaker !== "user").length;
  const falseCounterpartyCount = turns.filter((turn) => turn.observed_speaker === "counterparty" && turn.expected_speaker !== "counterparty").length;
  const missingCount = turns.filter((turn) => turn.missing_transcript).length;
  const timeoutCount = turns.filter((turn) => turn.timeout).length;
  const failureKindCounts = {};
  for (const turn of turns) {
    const key = turn.failure_kind || "none";
    failureKindCounts[key] = (failureKindCounts[key] || 0) + 1;
  }
  const leadingDropCount = turns.filter((turn) => turn.leading_word_drop).length;
  const trailingDropCount = turns.filter((turn) => turn.trailing_word_drop).length;
  const latencies = turns.map((turn) => turn.latency_ms).filter((value) => value !== null);
  const wers = turns.map((turn) => turn.wer);

  const confusionMatrix = {};
  for (const turn of turns) {
    const expected = turn.expected_speaker;
    const observed = turn.observed_speaker || "missing";
    confusionMatrix[expected] ||= {};
    confusionMatrix[expected][observed] = (confusionMatrix[expected][observed] || 0) + 1;
  }

  const byCondition = {};
  for (const condition of new Set(turns.map((turn) => turn.condition))) {
    const conditionTurns = turns.filter((turn) => turn.condition === condition);
    byCondition[condition] = {
      turn_count: conditionTurns.length,
      speaker_accuracy: Number((conditionTurns.filter((turn) => turn.speaker_correct).length / Math.max(1, conditionTurns.length)).toFixed(4)),
      false_user_count: conditionTurns.filter((turn) => turn.observed_speaker === "user" && turn.expected_speaker !== "user").length,
      false_counterparty_count: conditionTurns.filter((turn) => turn.observed_speaker === "counterparty" && turn.expected_speaker !== "counterparty").length,
      missing_transcript_count: conditionTurns.filter((turn) => turn.missing_transcript).length,
      wer_mean: mean(conditionTurns.map((turn) => turn.wer)),
      p95_latency_ms: p95(conditionTurns.map((turn) => turn.latency_ms).filter((value) => value !== null)),
      leading_word_drop_count: conditionTurns.filter((turn) => turn.leading_word_drop).length,
      trailing_word_drop_count: conditionTurns.filter((turn) => turn.trailing_word_drop).length,
    };
  }

  return {
    suite,
    run_id: runId,
    turn_count: total,
    speaker_accuracy: Number((speakerCorrect / Math.max(1, total)).toFixed(4)),
    false_user_count: falseUserCount,
    false_counterparty_count: falseCounterpartyCount,
    wrong_label_count: turns.filter((turn) => turn.wrong_label).length,
    missing_transcript_count: missingCount,
    timeout_count: timeoutCount,
    failure_kind_counts: failureKindCounts,
    wer_mean: mean(wers),
    leading_word_drop_count: leadingDropCount,
    trailing_word_drop_count: trailingDropCount,
    latency_ms_mean: mean(latencies),
    latency_ms_p95: p95(latencies),
    confusion_matrix: confusionMatrix,
    by_condition: byCondition,
    pass: (
      Number((speakerCorrect / Math.max(1, total)).toFixed(4)) >= 0.99 &&
      falseUserCount === 0 &&
      falseCounterpartyCount === 0 &&
      (missingCount / Math.max(1, total)) < 0.01 &&
      (mean(wers) || 0) <= 0.10 &&
      (leadingDropCount / Math.max(1, total)) < 0.01 &&
      (trailingDropCount / Math.max(1, total)) < 0.01
    ),
    ...extra,
  };
}

function mean(values) {
  if (!values.length) return null;
  return Number((values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(3));
}

function p95(values) {
  if (!values.length) return null;
  const ordered = [...values].sort((a, b) => a - b);
  const idx = Math.max(0, Math.ceil(0.95 * ordered.length) - 1);
  return Number(ordered[idx].toFixed(3));
}

function buildScenarioReport({ runId, manifestId, scenario, turns, suite, events }) {
  return {
    suite,
    run_id: runId,
    manifest_id: manifestId,
    created_at_ms: Date.now(),
    scenario: {
      id: scenario.id,
      voice_pair_id: scenario.voice_pair_id,
      condition: scenario.condition,
      condition_tags: scenario.condition_tags,
    },
    summary: aggregateTurns(turns, { suite, runId }),
    turns,
    events,
  };
}

function buildAggregateReport({ runId, manifestId, suite, scenarios, turns }) {
  return {
    suite,
    run_id: runId,
    manifest_id: manifestId,
    created_at_ms: Date.now(),
    scenario_count: scenarios.length,
    scenarios,
    summary: aggregateTurns(turns, { suite, runId, extra: { report_count: scenarios.length } }),
    turns,
  };
}

function timestampRunId() {
  const now = new Date();
  const pad = (value) => String(value).padStart(2, "0");
  return `${now.getFullYear()}${pad(now.getMonth() + 1)}${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
}

function initAudioEvalScript() {
  const evalState = {
    transcripts: [],
    wsEvents: [],
    turnWindow: { transcripts: [], utteranceEnds: [], wsEvents: [], audioChunkCount: 0, audioChunkTimestamps: [] },
    mediaReady: false,
  };
  window.__audioEvalVadOptions = {
    positiveSpeechThreshold: 0.35,
    negativeSpeechThreshold: 0.2,
    redemptionFrames: 2,
    preSpeechPadFrames: 1,
    minSpeechFrames: 2,
  };

  const ensureMedia = async () => {
    if (window.__audioEvalMedia) {
      return window.__audioEvalMedia;
    }
    const ctx = new window.AudioContext({ sampleRate: 16000 });
    if (ctx.state === "suspended") {
      await ctx.resume();
    }
    const masterGain = ctx.createGain();
    masterGain.gain.value = 2.5;
    window.__audioEvalMedia = { ctx, masterGain, destinations: [] };
    evalState.mediaReady = true;
    return window.__audioEvalMedia;
  };

  navigator.mediaDevices.getUserMedia = async () => {
    const media = await ensureMedia();
    const destination = media.ctx.createMediaStreamDestination();
    media.masterGain.connect(destination);
    media.destinations.push(destination);
    return destination.stream;
  };

  window.__audioEvalPlayBase64 = async (base64Wav) => {
    const media = await ensureMedia();
    if (media.ctx.state === "suspended") {
      await media.ctx.resume();
    }
    const binary = Uint8Array.from(atob(base64Wav), (char) => char.charCodeAt(0));
    const arrayBuffer = binary.buffer.slice(binary.byteOffset, binary.byteOffset + binary.byteLength);
    const decoded = await media.ctx.decodeAudioData(arrayBuffer);
    const source = media.ctx.createBufferSource();
    source.buffer = decoded;
    source.connect(media.masterGain);
    return await new Promise((resolve) => {
      source.onended = () => resolve();
      source.start();
    });
  };

  window.__audioEvalClearTurnWindow = () => {
    evalState.turnWindow = { transcripts: [], utteranceEnds: [], wsEvents: [], audioChunkCount: 0, audioChunkTimestamps: [] };
  };

  window.__audioEvalSnapshot = () => JSON.parse(JSON.stringify(evalState));

  window.addEventListener("negotiation-transcript", (event) => {
    const detail = event.detail || {};
    const entry = {
      speaker: detail.speaker,
      text: detail.text,
      capturedAt: Date.now(),
    };
    evalState.transcripts.push(entry);
    evalState.turnWindow.transcripts.push(entry);
  });

  const originalSend = WebSocket.prototype.send;
  WebSocket.prototype.send = function patchedSend(data) {
    try {
      if (typeof data === "string") {
        const parsed = JSON.parse(data);
        if (parsed.type === "START_NEGOTIATION") {
          parsed.payload = { ...(parsed.payload || {}), audio_eval_only: true };
          data = JSON.stringify(parsed);
        }
        const entry = { type: parsed.type, payload: parsed.payload || {}, capturedAt: Date.now() };
        evalState.wsEvents.push(entry);
        evalState.turnWindow.wsEvents.push(entry);
        if (parsed.type === "UTTERANCE_END") {
          evalState.turnWindow.utteranceEnds.push(entry);
        }
      } else {
        evalState.turnWindow.audioChunkCount += 1;
        evalState.turnWindow.audioChunkTimestamps.push(Date.now());
      }
    } catch (_error) {
      // Ignore parse failures for binary or non-JSON data.
    }
    return originalSend.call(this, data);
  };
}
