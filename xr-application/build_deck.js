const pptxgen = require("pptxgenjs");
const p = new pptxgen();
p.defineLayout({ name: "W", width: 13.333, height: 7.5 });
p.layout = "W";

// ---- Palette: Midnight + Gold (mirrors the app's dark/gold UI) ----
const BG     = "0A0E1A";  // near-black navy
const CARD   = "161B2E";
const CARD2  = "1E2440";
const GOLD   = "F5B301";
const GOLDB  = "FFC53D";
const CYAN   = "22D3EE";
const TXT    = "F4F6FB";
const MUTE   = "9AA3B8";
const GREEN  = "34D399";
const CORAL  = "F87171";
const LINE   = "2A3150";

const HF = "Trebuchet MS";   // header font
const BF = "Calibri";        // body font
const A   = "assets/";

const W = 13.333, H = 7.5;
const M = 0.6;               // margin

// helpers --------------------------------------------------------------
function bg(s, color) { s.background = { color }; }
function chip(s, x, y, w, txt, fill, color) {
  s.addShape("roundRect", { x, y, w, h: 0.34, rectRadius: 0.17, fill: { color: fill } });
  s.addText(txt, { x, y, w, h: 0.34, align: "center", valign: "middle",
    fontFace: HF, fontSize: 11, bold: true, color, charSpacing: 1 });
}
function footer(s, n) {
  s.addText("Balaastratech  ·  AI Negotiation Copilot", { x: M, y: H-0.45, w: 7, h: 0.3,
    fontFace: BF, fontSize: 9, color: MUTE, align: "left" });
  s.addText("Android XR Developer Catalyst — May 2026", { x: W-4.6, y: H-0.45, w: 4, h: 0.3,
    fontFace: BF, fontSize: 9, color: MUTE, align: "right" });
  s.addText(String(n), { x: W-0.55, y: H-0.45, w: 0.3, h: 0.3,
    fontFace: BF, fontSize: 9, color: GOLD, align: "right", bold: true });
}

// ===================================================================
// SLIDE 1 — TITLE
// ===================================================================
let s = p.addSlide(); bg(s, BG);
// faint right-side accent block
s.addShape("rect", { x: 0, y: 0, w: 0.18, h: H, fill: { color: GOLD } });
s.addShape("roundRect", { x: W-4.9, y: 0.7, w: 4.3, h: 6.1, rectRadius: 0.12,
  fill: { color: CARD }, line: { color: LINE, width: 1 } });
// brand
s.addText("BALAASTRATECH", { x: M, y: 0.85, w: 7, h: 0.4, fontFace: HF, fontSize: 15,
  bold: true, color: GOLD, charSpacing: 3 });
// title
s.addText([
  { text: "AI Negotiation", options: { breakLine: true } },
  { text: "Copilot", options: { breakLine: true, color: GOLDB } },
  { text: "for Android XR", options: {} },
], { x: M, y: 2.0, w: 7.4, h: 2.6, fontFace: HF, fontSize: 48, bold: true, color: TXT, lineSpacingMultiple: 0.98 });
// tagline
s.addText("A real-time coaching agent on your glasses — it listens to a live negotiation and surfaces the next move on your lens, hands-free, eyes-up.",
  { x: M, y: 4.75, w: 7.0, h: 1.0, fontFace: BF, fontSize: 16, color: MUTE, lineSpacingMultiple: 1.1 });
chip(s, M, 6.05, 2.2, "POWERED BY GEMINI LIVE", CARD2, GOLDB);
chip(s, M+2.4, 6.05, 2.4, "DISPLAY & AUDIO GLASSES", CARD2, CYAN);

// right card: the live coaching line (real product copy)
s.addText("LIVE ON SCREEN NOW →", { x: W-4.6, y: 1.05, w: 3.7, h: 0.3, fontFace: HF,
  fontSize: 11, bold: true, color: MUTE, charSpacing: 1 });
s.addShape("roundRect", { x: W-4.6, y: 1.5, w: 3.7, h: 2.0, rectRadius: 0.1, fill: { color: CARD2 } });
s.addText("AI ADVISOR", { x: W-4.45, y: 1.65, w: 3, h: 0.3, fontFace: HF, fontSize: 10, bold: true, color: GOLD });
s.addText("“Counter their offer of $500 with a price closer to your target, such as $700.”",
  { x: W-4.45, y: 2.0, w: 3.4, h: 1.4, fontFace: BF, fontSize: 15, italic: true, color: TXT, lineSpacingMultiple: 1.05, valign: "top" });
// mini stats
const ms = [["$600–800", "market range, auto-researched"], ["<1s", "coaching latency"], ["Deployed", "live on Google Cloud Run"]];
let yy = 3.75;
ms.forEach(([a,b]) => {
  s.addText(a, { x: W-4.6, y: yy, w: 1.7, h: 0.45, fontFace: HF, fontSize: 20, bold: true, color: GOLDB });
  s.addText(b, { x: W-2.85, y: yy+0.04, w: 2.0, h: 0.5, fontFace: BF, fontSize: 10.5, color: MUTE, valign: "middle" });
  yy += 0.74;
});
footer(s, 1);

// ===================================================================
// SLIDE 2 — THE PROBLEM
// ===================================================================
s = p.addSlide(); bg(s, BG);
s.addText("The problem", { x: M, y: 0.55, w: 8, h: 0.7, fontFace: HF, fontSize: 34, bold: true, color: TXT });
s.addText("High-stakes conversations demand your full attention — exactly when you most need help.",
  { x: M, y: 1.32, w: 11.5, h: 0.5, fontFace: BF, fontSize: 15, color: MUTE });

const probs = [
  ["You can't look away", "Salary talks, deals, big purchases — glancing at a phone breaks eye contact and signals weakness. The help has nowhere to live.", CORAL],
  ["Information arrives too late", "The right counter-offer or market price is useless after the moment has passed. Negotiation is real-time or it's nothing.", GOLDB],
  ["Most people negotiate blind", "Without prep or live data, people leave money on the table on the most expensive decisions of their lives.", CYAN],
];
let px = M, pw = (W - 2*M - 2*0.4) / 3;
probs.forEach(([t, d, c], i) => {
  const x = M + i*(pw+0.4);
  s.addShape("roundRect", { x, y: 2.2, w: pw, h: 3.9, rectRadius: 0.1, fill: { color: CARD }, line: { color: LINE, width: 1 } });
  s.addShape("roundRect", { x: x+0.35, y: 2.55, w: 0.65, h: 0.65, rectRadius: 0.12, fill: { color: CARD2 } });
  s.addText(String(i+1), { x: x+0.35, y: 2.55, w: 0.65, h: 0.65, align: "center", valign: "middle", fontFace: HF, fontSize: 24, bold: true, color: c });
  s.addText(t, { x: x+0.35, y: 3.45, w: pw-0.7, h: 0.9, fontFace: HF, fontSize: 19, bold: true, color: TXT, valign: "top", lineSpacingMultiple: 0.95 });
  s.addText(d, { x: x+0.35, y: 4.45, w: pw-0.7, h: 1.5, fontFace: BF, fontSize: 13, color: MUTE, valign: "top", lineSpacingMultiple: 1.08 });
});
s.addText("On glasses, the advisor finally has a home: in your field of view, the instant it matters.",
  { x: M, y: 6.35, w: 11.5, h: 0.5, fontFace: BF, fontSize: 15, italic: true, color: GOLDB, align: "center" });
footer(s, 2);

// ===================================================================
// SLIDE 3 — THE SOLUTION (hero screenshot)
// ===================================================================
s = p.addSlide(); bg(s, BG);
s.addText("The solution — working today", { x: M, y: 0.5, w: 9, h: 0.7, fontFace: HF, fontSize: 32, bold: true, color: TXT });
s.addText("Our live web/desktop app already does the hard part: listen, understand, and coach in real time. XR is the natural home for it.",
  { x: M, y: 1.22, w: 11.8, h: 0.5, fontFace: BF, fontSize: 14, color: MUTE });
// screenshot framed
const iw = 11.9, ih = iw * 819/1878; // 5.19
s.addShape("roundRect", { x: (W-iw)/2-0.06, y: 1.85-0.06, w: iw+0.12, h: ih+0.12, rectRadius: 0.08, fill: { color: CARD }, line: { color: GOLD, width: 1.25 } });
s.addImage({ path: A+"shot1.png", x: (W-iw)/2, y: 1.85, w: iw, h: ih });
s.addText("Live session: selling an iPhone 14 Pro Max. The copilot extracts item, prices & sentiment, flags the $500-vs-$800 leverage gap, pulls market data, and says “counter at ~$700” — instantly.",
  { x: M, y: 1.85+ih+0.12, w: 12.1, h: 0.5, fontFace: BF, fontSize: 11.5, italic: true, color: MUTE, align: "center" });
footer(s, 3);

// ===================================================================
// SLIDE 4 — WHY GLASSES / ANDROID XR
// ===================================================================
s = p.addSlide(); bg(s, BG);
s.addText("Why Android XR — why glasses", { x: M, y: 0.55, w: 9, h: 0.7, fontFace: HF, fontSize: 32, bold: true, color: TXT });
s.addText("This is a glanceable, hands-free, conversational utility — the exact profile Google describes for Display & Audio glasses.",
  { x: M, y: 1.3, w: 7.0, h: 1.0, fontFace: BF, fontSize: 14.5, color: MUTE, lineSpacingMultiple: 1.1 });

const fits = [
  ["Eyes-up & hands-free", "Coaching on the lens; no phone, no broken eye contact."],
  ["Real-time & ambient", "Sub-second cards appear the moment leverage shifts."],
  ["Voice-first", "“Ask AI” by voice; spoken guidance back."],
  ["All-day contextual", "From a car lot to a boardroom — always ready."],
];
let fy = 2.5;
fits.forEach(([t, d]) => {
  s.addShape("roundRect", { x: M, y: fy, w: 0.38, h: 0.38, rectRadius: 0.19, fill: { color: GOLD } });
  s.addText("✓", { x: M, y: fy, w: 0.38, h: 0.38, align: "center", valign: "middle", fontFace: HF, fontSize: 15, bold: true, color: BG });
  s.addText(t, { x: M+0.6, y: fy-0.04, w: 6.2, h: 0.4, fontFace: HF, fontSize: 16, bold: true, color: TXT });
  s.addText(d, { x: M+0.6, y: fy+0.34, w: 6.2, h: 0.5, fontFace: BF, fontSize: 12.5, color: MUTE });
  fy += 1.02;
});

// Glasses lens mockup (right)
const gx = 7.9, gy = 2.1, gw = 4.8, gh = 4.4;
s.addShape("roundRect", { x: gx, y: gy, w: gw, h: gh, rectRadius: 0.14, fill: { color: "05070F" }, line: { color: LINE, width: 1 } });
s.addText("ON THE LENS", { x: gx, y: gy+0.2, w: gw, h: 0.3, align: "center", fontFace: HF, fontSize: 11, bold: true, color: MUTE, charSpacing: 2 });
// HUD card
s.addShape("roundRect", { x: gx+0.5, y: gy+0.85, w: gw-1.0, h: 1.55, rectRadius: 0.1, fill: { color: CARD2 }, line: { color: GOLD, width: 1 } });
s.addText("● AI ADVISOR", { x: gx+0.7, y: gy+1.0, w: gw-1.4, h: 0.3, fontFace: HF, fontSize: 10, bold: true, color: GOLDB });
s.addText("Counter their $500 with a price closer to your target — try $700.",
  { x: gx+0.7, y: gy+1.32, w: gw-1.4, h: 1.0, fontFace: BF, fontSize: 14.5, color: TXT, valign: "top", lineSpacingMultiple: 1.05 });
// intel pills
chip(s, gx+0.5, gy+2.6, 1.9, "MARKET  $600–$800", CARD, CYAN);
chip(s, gx+2.5, gy+2.6, 1.8, "SENTIMENT  NEUTRAL", CARD, GREEN);
chip(s, gx+0.5, gy+3.05, 1.9, "LEVERAGE  HIGH", CARD, GOLDB);
chip(s, gx+2.5, gy+3.05, 1.8, "TACTIC  BATNA", CARD, GOLD);
s.addText("Mock — glanceable HUD concept built from the live product UI",
  { x: gx, y: gy+gh-0.45, w: gw, h: 0.3, align: "center", fontFace: BF, fontSize: 9.5, italic: true, color: MUTE });
footer(s, 4);

// ===================================================================
// SLIDE 5 — TECH & TRACTION
// ===================================================================
s = p.addSlide(); bg(s, BG);
s.addText("Built on Gemini — already deployed", { x: M, y: 0.5, w: 9.5, h: 0.7, fontFace: HF, fontSize: 30, bold: true, color: TXT });
s.addText("A production multimodal agent on Google's own stack. The XR client reuses this backend unchanged.",
  { x: M, y: 1.22, w: 11.8, h: 0.5, fontFace: BF, fontSize: 14, color: MUTE });

// left: architecture rows
const arch = [
  ["Gemini Live API", "Real-time native-audio voice — listens & speaks back", GOLDB],
  ["Gemini Flash · ListenerAgent", "Background extraction: prices, sentiment, leverage", CYAN],
  ["Google Search grounding", "Live market data ($600–$800 range, auto-pulled)", GREEN],
  ["FastAPI + WebSockets", "16 kHz PCM streaming, sub-second round-trip", GOLD],
];
let ay = 2.1;
arch.forEach(([t, d, c]) => {
  s.addShape("roundRect", { x: M, y: ay, w: 6.4, h: 0.95, rectRadius: 0.08, fill: { color: CARD }, line: { color: LINE, width: 1 } });
  s.addShape("rect", { x: M, y: ay, w: 0.09, h: 0.95, fill: { color: c } });
  s.addText(t, { x: M+0.3, y: ay+0.12, w: 6, h: 0.35, fontFace: HF, fontSize: 15, bold: true, color: TXT });
  s.addText(d, { x: M+0.3, y: ay+0.5, w: 6, h: 0.35, fontFace: BF, fontSize: 12, color: MUTE });
  ay += 1.08;
});

// right: real intel screenshot + traction
const cw = 5.0, ch = cw * 735/823;
s.addShape("roundRect", { x: 7.3-0.05, y: 2.1-0.05, w: cw+0.1, h: ch+0.1, rectRadius: 0.06, fill: { color: CARD }, line: { color: GOLD, width: 1 } });
s.addImage({ path: A+"context.png", x: 7.3, y: 2.1, w: cw, h: ch });
s.addText("Real output: auto-built negotiation context — item, prices, leverage points & researched market tactics.",
  { x: 7.3, y: 2.1+ch+0.08, w: cw, h: 0.6, fontFace: BF, fontSize: 10.5, italic: true, color: MUTE, align: "center", lineSpacingMultiple: 1.0 });
footer(s, 5);

// ===================================================================
// SLIDE 6 — ROADMAP & THE ASK
// ===================================================================
s = p.addSlide(); bg(s, BG);
s.addText("Roadmap to Play — and the ask", { x: M, y: 0.5, w: 10, h: 0.7, fontFace: HF, fontSize: 30, bold: true, color: TXT });
s.addText("Native Kotlin + Jetpack Compose client on the Jetpack XR SDK, reusing our deployed cloud backend.",
  { x: M, y: 1.22, w: 11.8, h: 0.5, fontFace: BF, fontSize: 14, color: MUTE });

const road = [
  ["0–2 mo", "Port WebSocket audio client to native Jetpack XR; coaching cards on lens", GOLDB],
  ["2–4 mo", "On-glasses mic capture + voice “Ask AI”; latency tuning for the HUD", CYAN],
  ["4–8 mo", "Closed testing on dev-kit hardware; ambient-listening consent UX", GREEN],
  ["8–12 mo", "Android XR closed/open testing track → Play, target Mar 2027", GOLD],
];
let rx = M, rcw = (W - 2*M - 3*0.35) / 4;
road.forEach(([t, d, c], i) => {
  const x = M + i*(rcw+0.35);
  s.addShape("roundRect", { x, y: 2.1, w: rcw, h: 2.35, rectRadius: 0.1, fill: { color: CARD }, line: { color: LINE, width: 1 } });
  s.addShape("roundRect", { x: x+0.25, y: 2.32, w: 1.5, h: 0.42, rectRadius: 0.21, fill: { color: c } });
  s.addText(t, { x: x+0.25, y: 2.32, w: 1.5, h: 0.42, align: "center", valign: "middle", fontFace: HF, fontSize: 13, bold: true, color: BG });
  s.addText(d, { x: x+0.25, y: 2.95, w: rcw-0.5, h: 1.4, fontFace: BF, fontSize: 12, color: TXT, valign: "top", lineSpacingMultiple: 1.08 });
});

// The ask
s.addShape("roundRect", { x: M, y: 4.85, w: W-2*M, h: 1.9, rectRadius: 0.12, fill: { color: CARD2 }, line: { color: GOLD, width: 1.25 } });
s.addText("THE ASK", { x: M+0.4, y: 5.1, w: 3, h: 0.35, fontFace: HF, fontSize: 13, bold: true, color: GOLD, charSpacing: 2 });
const asks = [
  ["Dev kit", "Display & Audio glasses hardware (shipping to eligible region)"],
  ["Tech support", "Jetpack XR SDK guidance for low-latency on-glasses audio"],
  ["Grant", "~3–4 mo focused engineering to port & harden the native client"],
];
let axx = M+0.4;
const aw = (W-2*M-0.8-2*0.4)/3;
asks.forEach(([t, d], i) => {
  const x = M+0.4 + i*(aw+0.4);
  s.addText(t, { x, y: 5.5, w: aw, h: 0.35, fontFace: HF, fontSize: 16, bold: true, color: GOLDB });
  s.addText(d, { x, y: 5.88, w: aw, h: 0.8, fontFace: BF, fontSize: 12, color: TXT, valign: "top", lineSpacingMultiple: 1.05 });
});
footer(s, 6);

p.writeFile({ fileName: "Balaastratech_AI_Negotiation_Copilot_AndroidXR.pptx" }).then(f => console.log("WROTE", f));
