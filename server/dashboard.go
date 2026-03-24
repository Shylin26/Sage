package main

import (
	"fmt"
	"strings"
)

func renderDashboard(b *Briefing) string {
	if b == nil {
		return renderEmpty()
	}

	var actionsHTML strings.Builder
	for _, line := range strings.Split(b.Actions, "\n") {
		line = strings.TrimSpace(line)
		if line != "" {
			actionsHTML.WriteString("<li>" + line + "</li>")
		}
	}

	return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SAGE</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
       background:#0f0f0f;color:#e8e8e8;min-height:100vh;padding:2rem}
  .container{max-width:720px;margin:0 auto}
  .header{border-bottom:1px solid #2a2a2a;padding-bottom:1rem;margin-bottom:2rem}
  .header h1{font-size:1.1rem;font-weight:600;letter-spacing:.12em;color:#888}
  .header .date{font-size:.85rem;color:#555;margin-top:.25rem}
  .hook{font-size:1.25rem;font-weight:500;line-height:1.6;color:#f0f0f0;margin-bottom:2rem}
  .section{margin-bottom:1.75rem}
  .section h2{font-size:.72rem;font-weight:600;letter-spacing:.14em;
              color:#555;text-transform:uppercase;margin-bottom:.75rem}
  .section p{font-size:.95rem;line-height:1.7;color:#bbb}
  .actions li{font-size:.95rem;line-height:1.7;color:#bbb;
              padding:.4rem 0;border-bottom:1px solid #1e1e1e;list-style:none}
  .actions li::before{content:"→ ";color:#444}
  .financial{background:#161616;border:1px solid #2a2a2a;
             border-radius:8px;padding:1rem 1.25rem}
  .financial p{font-size:.9rem;color:#aaa;line-height:1.6}
  .close{font-size:.95rem;color:#666;font-style:italic;
         border-top:1px solid #1e1e1e;padding-top:1.5rem;margin-top:1rem}
  .badge{display:inline-block;background:#1a1a1a;border:1px solid #2a2a2a;
         border-radius:4px;padding:.2rem .6rem;font-size:.72rem;color:#555;
         margin-left:.5rem;font-family:monospace}
  .run-btn{display:inline-block;margin-top:2rem;padding:.5rem 1.25rem;
           background:#1e1e1e;border:1px solid #333;border-radius:6px;
           color:#888;font-size:.8rem;cursor:pointer;text-decoration:none}
  .run-btn:hover{background:#252525;color:#bbb}
  .meta{font-size:.75rem;color:#3a3a3a;margin-top:.5rem}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <h1>SAGE <span class="badge">Go</span></h1>
    <div class="date">` + b.Date + ` &nbsp;·&nbsp; ` + fmt.Sprintf("%d", b.SignalCount) + ` signals</div>
  </div>
  <div class="hook">` + b.Hook + `</div>
  <div class="section">
    <h2>Situation</h2>
    <p>` + b.Situation + `</p>
  </div>
  <div class="section">
    <h2>Action Items</h2>
    <ul class="actions">` + actionsHTML.String() + `</ul>
  </div>
  <div class="section">
    <h2>Financial Pulse</h2>
    <div class="financial"><p>` + b.Financial + `</p></div>
  </div>
  <div class="close">` + b.Close + `</div>
  <div>
    <a class="run-btn" href="#" onclick="runPipeline()">↻ Run briefing now</a>
    <div class="meta" id="status"></div>
  </div>
</div>
<script>
async function runPipeline() {
  document.getElementById('status').textContent = 'Running pipeline...';
  const r = await fetch('/api/briefing/run', {method:'POST'});
  const d = await r.json();
  document.getElementById('status').textContent = 'Started at ' + d.time;
  setTimeout(() => location.reload(), 8000);
}
</script>
</body></html>`
}

func renderEmpty() string {
	return `<!DOCTYPE html>
<html><head><title>SAGE</title>
<style>body{background:#0f0f0f;color:#555;font-family:monospace;
display:flex;align-items:center;justify-content:center;height:100vh}</style>
</head><body>
<div style="text-align:center">
  <div style="font-size:1.1rem;color:#888;margin-bottom:1rem">SAGE</div>
  <div>No briefing yet.</div>
  <div style="margin-top:1rem">
    <a href="#" onclick="run()" style="color:#555;font-size:.85rem">Run pipeline now →</a>
  </div>
</div>
<script>
async function run(){
  await fetch('/api/briefing/run',{method:'POST'});
  setTimeout(()=>location.reload(),8000);
}
</script></body></html>`
}
