const pptxgen = require("pptxgenjs");
const p = new pptxgen();
p.defineLayout({ name: "W", width: 13.333, height: 7.5 });
p.layout = "W";

const BG="0A0E1A", CARD="161B2E", CARD2="1E2440", GOLD="F5B301", GOLDB="FFC53D",
  CYAN="22D3EE", TXT="F4F6FB", MUTE="9AA3B8", GREEN="34D399", LINE="2A3150";
const HF="Trebuchet MS", BF="Calibri", A="assets/";
const W=13.333, H=7.5, M=0.55;

let s=p.addSlide(); s.background={color:BG};
s.addShape("rect",{x:0,y:0,w:W,h:0.12,fill:{color:GOLD}});

// Header
s.addText("BALAASTRATECH",{x:M,y:0.35,w:7,h:0.35,fontFace:HF,fontSize:13,bold:true,color:GOLD,charSpacing:3});
s.addText("AI Negotiation Copilot — One-Page Brief",{x:M,y:0.68,w:9,h:0.6,fontFace:HF,fontSize:27,bold:true,color:TXT});
s.addText("Android XR Developer Catalyst Program",{x:W-4.7,y:0.45,w:4.15,h:0.35,fontFace:BF,fontSize:12,color:MUTE,align:"right"});
s.addText("Form factor: Display & Audio glasses",{x:W-4.7,y:0.78,w:4.15,h:0.3,fontFace:BF,fontSize:11,color:CYAN,align:"right"});
s.addText("Stack: Android + Jetpack Compose (XR SDK)",{x:W-4.7,y:1.05,w:4.15,h:0.3,fontFace:BF,fontSize:11,color:GOLDB,align:"right"});

// one-line pitch band
s.addShape("roundRect",{x:M,y:1.5,w:W-2*M,h:0.7,rectRadius:0.08,fill:{color:CARD2}});
s.addText([{text:"What it is:  ",options:{bold:true,color:GOLDB}},{text:"A real-time coaching agent on your glasses. It listens to a live, in-person negotiation and surfaces the next move on your lens — hands-free, eyes-up, in under a second.",options:{color:TXT}}],
  {x:M+0.3,y:1.5,w:W-2*M-0.6,h:0.7,fontFace:BF,fontSize:13.5,valign:"middle",lineSpacingMultiple:1.05});

// LEFT column ----------------------------------------------------------
const lx=M, lw=6.0, ly=2.45;
function sec(x,y,w,title){ s.addText(title,{x,y,w,h:0.3,fontFace:HF,fontSize:13,bold:true,color:GOLD,charSpacing:1}); }

sec(lx,ly,lw,"THE PROBLEM");
s.addText([
  {text:"You can't look at a phone mid-negotiation — it breaks eye contact and signals weakness.",options:{breakLine:true,bullet:{indent:14}}},
  {text:"The right counter-offer or market price is worthless after the moment passes.",options:{breakLine:true,bullet:{indent:14}}},
  {text:"Most people negotiate blind on their most expensive decisions.",options:{bullet:{indent:14}}},
],{x:lx,y:ly+0.32,w:lw,h:1.4,fontFace:BF,fontSize:12.5,color:TXT,lineSpacingMultiple:1.12});

sec(lx,ly+1.85,lw,"WHY GLASSES (FORM-FACTOR FIT)");
s.addText([
  {text:"Glanceable & hands-free — coaching lives in your field of view.",options:{breakLine:true,bullet:{indent:14}}},
  {text:"Real-time & ambient — cards appear the instant leverage shifts.",options:{breakLine:true,bullet:{indent:14}}},
  {text:"Voice-first — “Ask AI” by voice, spoken guidance back.",options:{bullet:{indent:14}}},
],{x:lx,y:ly+2.17,w:lw,h:1.3,fontFace:BF,fontSize:12.5,color:TXT,lineSpacingMultiple:1.12});

sec(lx,ly+3.55,lw,"TECH — BUILT ON GEMINI, ALREADY DEPLOYED");
s.addText([
  {text:"Gemini Live API — real-time native-audio voice.",options:{breakLine:true,bullet:{indent:14}}},
  {text:"Gemini Flash ListenerAgent — extracts prices, sentiment, leverage.",options:{breakLine:true,bullet:{indent:14}}},
  {text:"Google Search grounding + FastAPI/WebSockets, live on Google Cloud Run.",options:{bullet:{indent:14}}},
],{x:lx,y:ly+3.87,w:lw,h:1.2,fontFace:BF,fontSize:12.5,color:TXT,lineSpacingMultiple:1.12});

// RIGHT column ---------------------------------------------------------
const rx=6.95, rw=W-M-rx;
// screenshot
const iw=rw, ih=iw*819/1878;
s.addShape("roundRect",{x:rx-0.05,y:2.45-0.05,w:iw+0.1,h:ih+0.1,rectRadius:0.06,fill:{color:CARD},line:{color:GOLD,width:1}});
s.addImage({path:A+"shot1.png",x:rx,y:2.45,w:iw,h:ih});
s.addText("Live session: the copilot extracts context, flags the $500-vs-$800 gap, pulls market data, and says “counter at ~$700.”",
  {x:rx,y:2.45+ih+0.06,w:rw,h:0.4,fontFace:BF,fontSize:10,italic:true,color:MUTE,align:"center"});

// traction stats row
const sy=2.45+ih+0.6;
const stats=[["<1s","coaching latency"],["$600–800","auto-researched"],["Deployed","Cloud Run, live"]];
let sx=rx; const sw=(rw-2*0.2)/3;
stats.forEach(([a,b])=>{
  s.addShape("roundRect",{x:sx,y:sy,w:sw,h:0.95,rectRadius:0.08,fill:{color:CARD},line:{color:LINE,width:1}});
  s.addText(a,{x:sx,y:sy+0.1,w:sw,h:0.45,align:"center",fontFace:HF,fontSize:19,bold:true,color:GOLDB});
  s.addText(b,{x:sx,y:sy+0.55,w:sw,h:0.32,align:"center",fontFace:BF,fontSize:10,color:MUTE});
  sx+=sw+0.2;
});

// ROADMAP + ASK band (bottom full width) ------------------------------
const by=6.35;
s.addShape("roundRect",{x:M,y:by,w:W-2*M,h:0.92,rectRadius:0.1,fill:{color:CARD2},line:{color:GOLD,width:1}});
s.addText([{text:"ROADMAP  ",options:{bold:true,color:GOLD}},
  {text:"0–2 mo port to Jetpack XR · 2–4 mo on-glasses audio + voice · 4–8 mo dev-kit testing · 8–12 mo Play (Mar 2027).",options:{color:TXT}}],
  {x:M+0.3,y:by+0.1,w:W-2*M-0.6,h:0.35,fontFace:BF,fontSize:11.5,valign:"middle"});
s.addText([{text:"THE ASK  ",options:{bold:true,color:GOLD}},
  {text:"Display & Audio glasses dev kit · Jetpack XR SDK technical support · grant for ~3–4 months to port & harden the native client.",options:{color:TXT}}],
  {x:M+0.3,y:by+0.5,w:W-2*M-0.6,h:0.35,fontFace:BF,fontSize:11.5,valign:"middle"});

// links footer
s.addText([{text:"Live app: ",options:{color:MUTE}},
  {text:"negotiation-frontend-219079068693.us-central1.run.app",options:{color:CYAN}},
  {text:"      Health: ",options:{color:MUTE}},
  {text:"…run.app/health",options:{color:CYAN}}],
  {x:M,y:7.18,w:W-2*M,h:0.28,fontFace:BF,fontSize:10,align:"left"});

p.writeFile({fileName:"Balaastratech_OnePager_AndroidXR.pptx"}).then(f=>console.log("WROTE",f));
