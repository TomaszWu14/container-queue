// CSS landingu (port „Kolejka Landing v2”) — zescopowany pod `.kolejka-landing`.
export const STYLE = `
.kolejka-landing{
  --bg:#060c18;--bg2:#04070f;--card:#111c30;--panel:#0c1526;--panel2:#13203a;
  --line:#2b426a;--line2:#3d5a8c;--text:#ffffff;--muted:#b6c6dc;--faint:#7e93b0;
  --blue:#4f93ff;--cyan:#22d3ee;--green:#22e39b;--amber:#ffb020;--red:#ff5470;
  --mono:'JetBrains Mono',ui-monospace,Consolas,monospace;
  --r-sm:9px;--r-md:12px;--r-lg:16px;
  position:relative;min-height:100vh;scroll-behavior:smooth;margin:0;
  font-family:'Inter',system-ui,-apple-system,sans-serif;background:var(--bg);color:var(--text);
  overflow-x:hidden;-webkit-font-smoothing:antialiased;
}
.kolejka-landing *{box-sizing:border-box;}
.kolejka-landing a{color:inherit;text-decoration:none;}
.kolejka-landing ::selection{background:rgba(59,130,246,.35);}
.kolejka-landing::before{content:"";position:fixed;inset:0;z-index:0;pointer-events:none;
  background:
    radial-gradient(1100px 560px at 82% -6%,rgba(6,182,212,.10),transparent 60%),
    radial-gradient(1000px 540px at 8% 2%,rgba(59,130,246,.12),transparent 60%),
    linear-gradient(transparent 96%,rgba(42,63,99,.45) 96%) 0 0/100% 46px,
    linear-gradient(90deg,transparent 96%,rgba(42,63,99,.45) 96%) 0 0/46px 100%;
  mask:linear-gradient(180deg,#000,#000 62%,transparent 100%);}
.kolejka-landing .wrap{max-width:1280px;margin:0 auto;padding:0 32px;}
.kolejka-landing .eyebrow{font-size:12px;font-weight:700;letter-spacing:.16em;text-transform:uppercase;color:var(--cyan);}
.kolejka-landing nav{position:sticky;top:0;z-index:60;display:flex;align-items:center;gap:16px;padding:14px 32px;
  backdrop-filter:blur(12px);background:rgba(11,17,32,.72);border-bottom:1px solid var(--line);}
.kolejka-landing .brand{display:flex;align-items:center;gap:11px;font-weight:800;}
.kolejka-landing .brand .logo{width:34px;height:34px;border-radius:var(--r-sm);display:grid;place-items:center;
  background:linear-gradient(135deg,var(--blue),var(--cyan));box-shadow:0 6px 18px rgba(6,182,212,.35);}
.kolejka-landing .brand small{display:block;font-weight:500;font-size:11px;color:var(--muted);letter-spacing:.14em;text-transform:uppercase;}
.kolejka-landing .navlinks{display:flex;gap:4px;margin-left:22px;}
.kolejka-landing .navlinks a{padding:8px 13px;border-radius:8px;font-size:14px;color:var(--muted);font-weight:500;transition:.15s;}
.kolejka-landing .navlinks a:hover{color:var(--text);background:rgba(42,63,99,.5);}
.kolejka-landing .navcta{margin-left:auto;display:flex;gap:10px;}
.kolejka-landing .btn{font-family:inherit;font-size:14px;font-weight:600;cursor:pointer;padding:10px 20px;border-radius:var(--r-sm);border:1px solid transparent;transition:.15s;white-space:nowrap;}
.kolejka-landing .btn-ghost{background:transparent;border-color:var(--line2);color:var(--text);}
.kolejka-landing .btn-ghost:hover{border-color:var(--cyan);color:#fff;}
.kolejka-landing .btn-primary{background:linear-gradient(135deg,var(--blue),var(--cyan));color:#04121f;box-shadow:0 8px 22px rgba(6,182,212,.30);}
.kolejka-landing .btn-primary:hover{filter:brightness(1.08);transform:translateY(-1px);box-shadow:0 12px 28px rgba(6,182,212,.42);}
.kolejka-landing .btn-primary:active{transform:translateY(0);}
.kolejka-landing .hero{position:relative;z-index:1;padding:60px 0 30px;}
.kolejka-landing .hero-top{display:grid;grid-template-columns:1.02fr 1fr;gap:46px;align-items:center;}
.kolejka-landing .badge{display:inline-flex;align-items:center;gap:8px;font-size:12px;font-weight:600;color:var(--cyan);
  background:rgba(6,182,212,.10);border:1px solid rgba(6,182,212,.28);padding:6px 13px;border-radius:999px;margin-bottom:22px;}
.kolejka-landing .badge .live{width:7px;height:7px;border-radius:50%;background:var(--green);animation:kl-live 1.8s infinite;}
@keyframes kl-live{0%{box-shadow:0 0 0 0 rgba(16,185,129,.6);}70%{box-shadow:0 0 0 8px rgba(16,185,129,0);}100%{box-shadow:0 0 0 0 rgba(16,185,129,0);}}
.kolejka-landing h1{font-size:clamp(2.2rem,4.3vw,3.4rem);line-height:1.06;font-weight:900;margin:0 0 20px;letter-spacing:-.02em;}
.kolejka-landing h1 .grad{background:linear-gradient(120deg,var(--blue),var(--cyan) 72%);-webkit-background-clip:text;background-clip:text;color:transparent;}
.kolejka-landing .subtitle{font-size:17px;color:var(--muted);min-height:3em;max-width:40ch;line-height:1.55;margin-bottom:0;}
.kolejka-landing .subtitle .cursor{display:inline-block;width:2px;height:1.05em;background:var(--cyan);vertical-align:-2px;margin-left:2px;animation:kl-blink 1s steps(1) infinite;}
@keyframes kl-blink{50%{opacity:0;}}
.kolejka-landing .hero-cta{display:flex;gap:14px;margin-top:30px;flex-wrap:wrap;}
.kolejka-landing .stats{display:flex;gap:32px;margin-top:22px;flex-wrap:wrap;}
.kolejka-landing .stat .num{font-family:var(--mono);font-size:29px;font-weight:700;color:#fff;}
.kolejka-landing .stat .num .u{font-size:15px;color:var(--cyan);}
.kolejka-landing .stat .lbl{font-size:12px;color:var(--faint);text-transform:uppercase;letter-spacing:.1em;margin-top:2px;}
.kolejka-landing .panel{background:linear-gradient(180deg,var(--panel),var(--bg2));border:1px solid var(--line);border-radius:var(--r-lg);box-shadow:0 24px 60px rgba(0,0,0,.45);}
.kolejka-landing .dash{padding:16px;}
.kolejka-landing .dash-head{display:flex;align-items:center;justify-content:space-between;padding:2px 6px 12px;}
.kolejka-landing .dash-head .t{font-size:13px;font-weight:600;}
.kolejka-landing .bell-wrap{position:relative;width:30px;height:30px;border-radius:8px;display:grid;place-items:center;background:rgba(42,63,99,.5);}
.kolejka-landing .bell-wrap .bdg{position:absolute;top:2px;right:2px;min-width:15px;height:15px;padding:0 3px;border-radius:9px;background:var(--red);color:#fff;font-size:10px;font-weight:700;display:grid;place-items:center;animation:kl-live 1.6s infinite;}
.kolejka-landing .stage{transition:.3s;}
.kolejka-landing .stagebox{fill:var(--panel2);stroke:var(--line2);stroke-width:1.5;transition:.3s;}
.kolejka-landing .stage.active .stagebox{stroke:var(--cyan);fill:#0e2233;filter:drop-shadow(0 0 6px rgba(6,182,212,.5));}
.kolejka-landing .stage .sl{font:600 10px 'Inter';fill:var(--muted);transition:.3s;}
.kolejka-landing .stage.active .sl{fill:#fff;}
.kolejka-landing .stage .si{stroke:var(--faint);transition:.3s;}
.kolejka-landing .stage.active .si{stroke:var(--cyan);}
.kolejka-landing .flowline{fill:none;stroke:var(--line2);stroke-width:2.2;}
.kolejka-landing .flowline-dlt{fill:none;stroke:url(#kl-fg);stroke-width:2.4;stroke-linecap:round;transition:stroke-dashoffset .1s linear;}
.kolejka-landing .gps{fill:var(--cyan);}
.kolejka-landing .gps-ring{fill:none;stroke:var(--cyan);animation:kl-gpspulse 1.6s ease-out infinite;}
@keyframes kl-gpspulse{0%{r:4;opacity:.8;}70%{r:16;opacity:0;}100%{opacity:0;}}
.kolejka-landing .ctr .body{stroke:#04121f;stroke-width:1;}
.kolejka-landing .ctr text{font:700 8px var(--mono);fill:#04121f;}
.kolejka-landing .drow{display:grid;grid-template-columns:1.1fr 1fr;gap:12px;margin-top:12px;}
.kolejka-landing .w{background:var(--bg2);border:1px solid var(--line);border-radius:var(--r-md);padding:12px 13px;min-width:0;}
.kolejka-landing .w .wl{font-size:10px;text-transform:uppercase;letter-spacing:.1em;color:var(--faint);}
.kolejka-landing .cal{display:grid;grid-template-columns:repeat(7,1fr);gap:4px;margin-top:9px;}
.kolejka-landing .cal .d{aspect-ratio:1;border-radius:5px;background:#0a1424;border:1px solid var(--line);position:relative;overflow:hidden;}
.kolejka-landing .cal .d.has::after{content:"";position:absolute;left:2px;right:2px;bottom:2px;height:3px;border-radius:2px;background:var(--blue);transform:scaleX(0);transform-origin:left;animation:kl-slotin .5s forwards;}
.kolejka-landing .cal .d.full::after{background:var(--amber);}
.kolejka-landing .cal .d.over::after{background:var(--red);}
@keyframes kl-slotin{to{transform:scaleX(1);}}
.kolejka-landing .kpis{display:flex;flex-direction:column;gap:9px;}
.kolejka-landing .kpi{display:flex;align-items:baseline;justify-content:space-between;}
.kolejka-landing .kpi .v{font-family:var(--mono);font-weight:700;font-size:17px;}
.kolejka-landing .tl{margin-top:12px;background:var(--bg2);border:1px solid var(--line);border-radius:var(--r-md);padding:11px 13px;}
.kolejka-landing .tl .ev{display:flex;align-items:center;gap:9px;font-size:12px;color:var(--muted);padding:5px 0;opacity:0;transform:translateX(-8px);}
.kolejka-landing .tl .ev.show{opacity:1;transform:none;transition:.4s;}
.kolejka-landing .tl .ev i{width:8px;height:8px;border-radius:50%;flex:none;}
.kolejka-landing .tl .ev time{margin-left:auto;font-family:var(--mono);font-size:11px;color:var(--faint);}
.kolejka-landing section{position:relative;z-index:1;}
.kolejka-landing .sec{padding:70px 0;}
.kolejka-landing .sec-head{text-align:center;max-width:660px;margin:0 auto 44px;}
.kolejka-landing .sec-head h2{font-size:clamp(1.7rem,3vw,2.4rem);font-weight:800;margin:12px 0;letter-spacing:-.01em;}
.kolejka-landing .sec-head p{color:var(--muted);font-size:16px;line-height:1.55;}
.kolejka-landing .cards{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;}
.kolejka-landing .card{background:linear-gradient(180deg,var(--panel),var(--bg2));border:1px solid var(--line);border-radius:var(--r-lg);padding:26px 22px;
  opacity:0;transform:translateY(26px);transition:opacity .6s cubic-bezier(.2,.7,.2,1),transform .6s cubic-bezier(.2,.7,.2,1),border-color .2s;}
.kolejka-landing .card.in{opacity:1;transform:none;}
.kolejka-landing .card:hover{border-color:var(--line2);transform:translateY(-4px);}
.kolejka-landing .ico{width:52px;height:52px;border-radius:13px;display:grid;place-items:center;margin-bottom:18px;transition:.25s;position:relative;
  background:rgba(59,130,246,.10);border:1px solid rgba(59,130,246,.22);}
.kolejka-landing .ico svg{width:26px;height:26px;}
.kolejka-landing .card h3{font-size:17px;font-weight:700;margin:0 0 8px;}
.kolejka-landing .card p{color:var(--muted);font-size:14px;line-height:1.55;margin:0;}
.kolejka-landing .tags{display:flex;flex-wrap:wrap;gap:6px;margin-top:14px;}
.kolejka-landing .tag{font-size:11px;font-weight:600;color:var(--muted);background:rgba(42,63,99,.4);border:1px solid var(--line);border-radius:999px;padding:4px 9px;}
.kolejka-landing .slot-anim rect.s{opacity:0;animation:none;}
.kolejka-landing .card.in .slot-anim rect.s{animation:kl-slotpop 2.2s infinite;}
.kolejka-landing .card.in .slot-anim rect.s:nth-of-type(2){animation-delay:.4s;}
.kolejka-landing .card.in .slot-anim rect.s:nth-of-type(3){animation-delay:.8s;}
@keyframes kl-slotpop{0%,80%,100%{opacity:0;}10%,60%{opacity:1;}}
.kolejka-landing .gpsdot{animation:kl-gpsblink 1.4s infinite;}
@keyframes kl-gpsblink{0%,100%{opacity:1;}50%{opacity:.25;}}
.kolejka-landing .card.in .orbit{transform-origin:12px 12px;animation:kl-spin 3s linear infinite;}
@keyframes kl-spin{to{transform:rotate(360deg);}}
.kolejka-landing .bell{transform-origin:top center;}
.kolejka-landing .card:hover .bell{animation:kl-ring .7s ease;}
@keyframes kl-ring{0%,100%{transform:rotate(0);}20%{transform:rotate(14deg);}40%{transform:rotate(-11deg);}60%{transform:rotate(7deg);}80%{transform:rotate(-4deg);}}
.kolejka-landing .card.in .barsvg rect{transform-origin:bottom;animation:kl-grow 1.8s ease-in-out infinite alternate;}
.kolejka-landing .card.in .barsvg rect:nth-of-type(2){animation-delay:.25s;}
.kolejka-landing .card.in .barsvg rect:nth-of-type(3){animation-delay:.5s;}
.kolejka-landing .card.in .barsvg rect:nth-of-type(4){animation-delay:.75s;}
@keyframes kl-grow{from{transform:scaleY(.5);}to{transform:scaleY(1);}}
.kolejka-landing .steps{display:grid;grid-template-columns:repeat(3,1fr);gap:22px;counter-reset:st;}
.kolejka-landing .step{background:linear-gradient(180deg,var(--panel),var(--bg2));border:1px solid var(--line);border-radius:var(--r-lg);padding:28px 24px;position:relative;
  opacity:0;transform:translateY(24px);transition:.6s cubic-bezier(.2,.7,.2,1);}
.kolejka-landing .step.in{opacity:1;transform:none;}
.kolejka-landing .step .n{counter-increment:st;font-family:var(--mono);font-size:13px;font-weight:700;color:var(--cyan);
  width:38px;height:38px;border-radius:10px;display:grid;place-items:center;background:rgba(6,182,212,.10);border:1px solid rgba(6,182,212,.25);margin-bottom:16px;}
.kolejka-landing .step .n::before{content:"0" counter(st);}
.kolejka-landing .step h4{margin:0 0 8px;font-size:17px;font-weight:700;}
.kolejka-landing .step p{margin:0;color:var(--muted);font-size:14px;line-height:1.55;}
.kolejka-landing .chips{display:flex;flex-wrap:wrap;gap:7px;margin-top:15px;}
.kolejka-landing .chip{font-size:12px;font-weight:600;padding:5px 11px;border-radius:999px;opacity:0;transform:scale(.85);}
.kolejka-landing .step.in .chip{animation:kl-chipin .5s forwards;}
.kolejka-landing .step.in .chip:nth-child(2){animation-delay:.15s;}
.kolejka-landing .step.in .chip:nth-child(3){animation-delay:.3s;}
@keyframes kl-chipin{to{opacity:1;transform:none;}}
.kolejka-landing .chip.b{color:var(--blue);background:rgba(59,130,246,.12);border:1px solid rgba(59,130,246,.3);}
.kolejka-landing .chip.c{color:var(--cyan);background:rgba(6,182,212,.12);border:1px solid rgba(6,182,212,.3);}
.kolejka-landing .chip.g{color:var(--green);background:rgba(16,185,129,.12);border:1px solid rgba(16,185,129,.3);}
.kolejka-landing .tenant{background:linear-gradient(180deg,var(--panel),var(--bg2));border:1px solid var(--line);border-radius:var(--r-lg);padding:24px;max-width:1000px;margin:0 auto;}
.kolejka-landing .tenant-tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:18px;}
.kolejka-landing .ttab{display:flex;align-items:center;gap:9px;padding:9px 15px;border-radius:12px;cursor:pointer;font-weight:600;font-size:14px;
  background:var(--bg2);border:1.5px solid var(--line);color:var(--muted);transition:.18s;}
.kolejka-landing .ttab .avatar{width:22px;height:22px;border-radius:6px;display:grid;place-items:center;font-size:11px;font-weight:800;color:#04121f;}
.kolejka-landing .ttab.active{color:#fff;background:#0e1c30;}
.kolejka-landing .ttab .role{font-size:11px;font-weight:500;color:var(--faint);}
.kolejka-landing .tenant-body{border:1px solid var(--line);border-radius:var(--r-md);background:var(--bg2);padding:20px;min-height:170px;position:relative;overflow:hidden;}
.kolejka-landing .tpane{display:none;animation:kl-fadein .35s ease;}
.kolejka-landing .tpane.active{display:block;}
@keyframes kl-fadein{from{opacity:0;transform:translateY(8px);}to{opacity:1;transform:none;}}
.kolejka-landing .tpane-head{display:flex;align-items:center;gap:12px;margin-bottom:16px;}
.kolejka-landing .tpane-head .lg{width:40px;height:40px;border-radius:10px;display:grid;place-items:center;font-weight:800;color:#04121f;}
.kolejka-landing .tpane-head .role-badge{margin-left:auto;font-size:11px;font-weight:600;padding:5px 11px;border-radius:999px;background:rgba(42,63,99,.5);border:1px solid var(--line);color:var(--muted);}
.kolejka-landing .tmetrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;}
.kolejka-landing .tm{background:var(--panel);border:1px solid var(--line);border-radius:var(--r-md);padding:13px;}
.kolejka-landing .tm .l{font-size:10px;text-transform:uppercase;letter-spacing:.09em;color:var(--faint);}
.kolejka-landing .tm .v{font-family:var(--mono);font-weight:700;font-size:20px;margin-top:5px;}
.kolejka-landing .iso-note{display:flex;align-items:center;gap:8px;margin-top:15px;font-size:12px;color:var(--muted);}
.kolejka-landing .iso-note svg{width:15px;height:15px;flex:none;}
.kolejka-landing footer{position:relative;z-index:1;border-top:1px solid var(--line);padding:40px 32px;text-align:center;}
.kolejka-landing footer .fl{font-size:18px;font-weight:700;max-width:560px;margin:0 auto 10px;}
.kolejka-landing footer .fs{color:var(--faint);font-size:13px;}
.kolejka-landing .tooltip{position:fixed;z-index:90;pointer-events:none;opacity:0;transform:translateY(4px);transition:.12s;background:#04101f;border:1px solid var(--line2);border-radius:9px;padding:9px 12px;font-size:12px;box-shadow:0 12px 30px rgba(0,0,0,.5);}
.kolejka-landing .tooltip.on{opacity:1;transform:none;}
.kolejka-landing .tooltip .id{font-family:var(--mono);font-weight:700;color:#fff;}
.kolejka-landing .tooltip .st{display:flex;align-items:center;gap:7px;margin-top:5px;color:var(--muted);}
.kolejka-landing .tooltip .st i{width:8px;height:8px;border-radius:50%;}
@media(max-width:980px){
  .kolejka-landing .hero-top{grid-template-columns:1fr;gap:34px;}
  .kolejka-landing .cards,.kolejka-landing .steps{grid-template-columns:repeat(2,1fr);}
  .kolejka-landing .navlinks{display:none;}
  .kolejka-landing .tmetrics{grid-template-columns:repeat(2,1fr);}
}
@media(max-width:560px){
  .kolejka-landing .wrap{padding:0 18px;} .kolejka-landing nav{padding:12px 18px;}
  .kolejka-landing .cards,.kolejka-landing .steps{grid-template-columns:1fr;} .kolejka-landing .drow{grid-template-columns:1fr;}
  .kolejka-landing .stats{gap:20px;}
}
@media(prefers-reduced-motion:reduce){.kolejka-landing *{animation-duration:.001ms!important;}}
`
