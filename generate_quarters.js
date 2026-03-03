const fs = require('fs');
const path = require('path');

const BASE = 'C:/Users/AdrianOw/Call-extraction';
const OUT = path.join(BASE, 'quarters');

const QUARTERS = [
  'Q1_2022','Q2_2022','Q3_2022','Q4_2022',
  'Q1_2023','Q2_2023','Q3_2023','Q4_2023',
  'Q1_2024','Q2_2024','Q3_2024','Q4_2024',
  'Q1_2025','Q2_2025','Q3_2025','Q4_2025',
];

// Map quarter key to filename
function mdFile(q) {
  return path.join(BASE, `TSMC_${q}_guidance.md`);
}

// Parse a markdown file into structured data
function parseMD(filepath) {
  const raw = fs.readFileSync(filepath, 'utf-8');
  const lines = raw.split('\n');

  let callDate = '';
  let reportingQuarter = '';
  let title = '';
  const sections = [];
  let currentSection = null;

  for (const line of lines) {
    // Title
    if (line.startsWith('# TSMC')) {
      title = line.replace(/^#\s*/, '').trim();
      continue;
    }
    // Metadata line
    if (line.startsWith('**Call Date:**')) {
      const m = line.match(/\*\*Call Date:\*\*\s*(.+?)\s*\|\s*\*\*Reporting Quarter:\*\*\s*(.+)/);
      if (m) {
        callDate = m[1].trim();
        reportingQuarter = m[2].trim();
      }
      continue;
    }
    // Horizontal rule
    if (line.trim() === '---') continue;
    // Section header
    if (line.startsWith('## ')) {
      currentSection = { title: line.replace(/^##\s*/, '').trim(), items: [] };
      sections.push(currentSection);
      continue;
    }
    // Bullet items
    if (line.startsWith('- ') && currentSection) {
      currentSection.items.push(line.replace(/^-\s*/, '').trim());
      continue;
    }
    // Continuation lines (non-empty, non-header, part of current section)
    if (line.trim() && currentSection && !line.startsWith('#')) {
      // Append to last item or add as standalone text
      if (currentSection.items.length > 0) {
        currentSection.items[currentSection.items.length - 1] += ' ' + line.trim();
      } else {
        currentSection.items.push(line.trim());
      }
    }
  }

  return { title, callDate, reportingQuarter, sections };
}

// Extract key metrics from parsed data
function extractMetrics(parsed) {
  const metrics = {};

  for (const sec of parsed.sections) {
    const t = sec.title.toLowerCase();

    // Quarterly guidance section — extract revenue, GM, OM
    if (t.startsWith('quarterly guidance')) {
      for (const item of sec.items) {
        if (item.match(/^\*\*Revenue:?\*\*/i)) {
          metrics.revenue = item.replace(/^\*\*Revenue:?\*\*\s*/i, '').trim();
        }
        if (item.match(/^\*\*Gross Margin:?\*\*/i)) {
          metrics.gm = item.replace(/^\*\*Gross Margin:?\*\*\s*/i, '').trim();
        }
        if (item.match(/^\*\*Operating Margin:?\*\*/i)) {
          metrics.om = item.replace(/^\*\*Operating Margin:?\*\*\s*/i, '').trim();
        }
      }
      metrics.guidanceFor = sec.title.replace(/Quarterly Guidance\s*/, '').replace(/[()]/g, '').trim();
    }

    // Full year guidance
    if (t.includes('full year') && t.includes('guidance')) {
      for (const item of sec.items) {
        if (item.match(/^\*\*Revenue growth:?\*\*/i) || item.match(/^\*\*Revenue:?\*\*/i)) {
          metrics.fyRevenue = item.replace(/^\*\*Revenue( growth)?:?\*\*\s*/i, '').trim();
        }
        if (item.match(/^\*\*CapEx:?\*\*/i)) {
          metrics.capex = item.replace(/^\*\*CapEx:?\*\*\s*/i, '').trim();
        }
      }
    }

    // Full year actuals
    if (t.includes('full year') && t.includes('actuals')) {
      for (const item of sec.items) {
        if (item.match(/^\*\*Revenue:?\*\*/i)) {
          metrics.fyActualRevenue = item.replace(/^\*\*Revenue:?\*\*\s*/i, '').trim();
        }
        if (item.match(/^\*\*Gross Margin:?\*\*/i)) {
          metrics.fyActualGM = item.replace(/^\*\*Gross Margin:?\*\*\s*/i, '').trim();
        }
        if (item.match(/^\*\*CapEx:?\*\*/i)) {
          metrics.fyActualCapex = item.replace(/^\*\*CapEx:?\*\*\s*/i, '').trim();
        }
      }
    }

    // Long-term targets
    if (t.includes('long-term')) {
      for (const item of sec.items) {
        if (item.match(/^\*\*Revenue CAGR:?\*\*/i)) {
          metrics.ltCAGR = item.replace(/^\*\*Revenue CAGR:?\*\*\s*/i, '').trim();
        }
        if (item.match(/^\*\*Gross Margin:?\*\*/i)) {
          metrics.ltGM = item.replace(/^\*\*Gross Margin:?\*\*\s*/i, '').trim();
        }
      }
    }

    // AI demand
    if (t.includes('ai')) {
      for (const item of sec.items) {
        if (item.match(/^\*\*AI revenue (share|CAGR):?\*\*/i)) {
          if (item.toLowerCase().includes('cagr')) {
            metrics.aiCAGR = item.replace(/^\*\*AI revenue CAGR:?\*\*\s*/i, '').trim();
          } else {
            metrics.aiShare = item.replace(/^\*\*AI revenue share:?\*\*\s*/i, '').trim();
          }
        }
        if (item.match(/^\*\*AI (accelerator )?revenue (2024|2025|CAGR):?\*\*/i)) {
          const clean = item.replace(/^\*\*.*?\*\*\s*/, '').trim();
          if (item.toLowerCase().includes('cagr')) {
            metrics.aiCAGR = clean;
          }
        }
      }
    }
  }

  return metrics;
}

// Convert markdown-style bold/italic in a string to HTML
function mdInline(text) {
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>')
    .replace(/~(\d+)/g, '~$1');
}

// Generate "What Changed" items by comparing current vs prior metrics
function generateChanges(current, prior, currentParsed, priorParsed) {
  const changes = [];

  if (!prior) {
    changes.push({ type: 'new', text: 'First quarter in our tracking series (Q1 2022)' });
    return changes;
  }

  // Compare quarterly revenue guidance midpoints
  function parseMidpoint(range) {
    if (!range) return null;
    const m = range.match(/\$?([\d.]+)B.*\$?([\d.]+)B/);
    if (m) return (parseFloat(m[1]) + parseFloat(m[2])) / 2;
    return null;
  }

  const curRev = parseMidpoint(current.revenue);
  const prevRev = parseMidpoint(prior.revenue);
  if (curRev && prevRev) {
    const delta = ((curRev - prevRev) / prevRev * 100).toFixed(1);
    if (Math.abs(delta) > 0.5) {
      changes.push({
        type: delta > 0 ? 'raised' : 'lowered',
        text: `Next-Q revenue guidance midpoint ${delta > 0 ? 'up' : 'down'} ${Math.abs(delta)}% vs prior quarter ($${curRev.toFixed(1)}B vs $${prevRev.toFixed(1)}B)`
      });
    }
  }

  // Compare GM midpoints
  function parseGMMidpoint(gm) {
    if (!gm) return null;
    const m = gm.match(/([\d.]+)%.*?([\d.]+)%/);
    if (m) return (parseFloat(m[1]) + parseFloat(m[2])) / 2;
    return null;
  }
  const curGM = parseGMMidpoint(current.gm);
  const prevGM = parseGMMidpoint(prior.gm);
  if (curGM && prevGM) {
    const delta = (curGM - prevGM).toFixed(1);
    if (Math.abs(delta) > 0.1) {
      changes.push({
        type: delta > 0 ? 'raised' : 'lowered',
        text: `GM guidance midpoint ${delta > 0 ? 'up' : 'down'} ${Math.abs(delta)} ppts (${curGM.toFixed(1)}% vs ${prevGM.toFixed(1)}%)`
      });
    }
  }

  // Compare CapEx
  if (current.capex && prior.capex && current.capex !== prior.capex) {
    changes.push({ type: 'changed', text: `CapEx guidance: ${current.capex} (prior: ${prior.capex})` });
  }

  // Compare LT GM target
  if (current.ltGM && prior.ltGM && current.ltGM !== prior.ltGM) {
    changes.push({ type: 'raised', text: `LT Gross Margin target changed: ${current.ltGM} (was: ${prior.ltGM})` });
  }

  // Compare LT CAGR
  if (current.ltCAGR && prior.ltCAGR && current.ltCAGR !== prior.ltCAGR) {
    changes.push({ type: 'changed', text: `LT Revenue CAGR updated: ${current.ltCAGR} (was: ${prior.ltCAGR})` });
  }

  // Compare FY revenue guidance
  if (current.fyRevenue && prior.fyRevenue && current.fyRevenue !== prior.fyRevenue) {
    changes.push({ type: 'changed', text: `Full-year revenue growth guidance: ${current.fyRevenue} (was: ${prior.fyRevenue})` });
  }

  // Check for new sections that didn't exist in prior
  const priorTitles = new Set(priorParsed.sections.map(s => s.title.toLowerCase()));
  for (const sec of currentParsed.sections) {
    const t = sec.title.toLowerCase();
    // Check for truly new topics
    if (t.includes('a16') && !priorTitles.has(t)) {
      let found = false;
      for (const pt of priorTitles) { if (pt.includes('a16')) found = true; }
      if (!found) changes.push({ type: 'new', text: `NEW: ${sec.title} first disclosed this quarter` });
    }
    if (t.includes('tariff') && !priorTitles.has(t)) {
      changes.push({ type: 'new', text: `NEW: Tariff impact discussion added` });
    }
    if (t.includes('ai demand') && !priorTitles.has(t)) {
      let found = false;
      for (const pt of priorTitles) { if (pt.includes('ai')) found = true; }
      if (!found) changes.push({ type: 'new', text: `NEW: AI demand emerges as a major theme` });
    }
    if (t.includes('actuals') && !priorTitles.has(t)) {
      let found = false;
      for (const pt of priorTitles) { if (pt.includes('actuals')) found = true; }
      if (!found) changes.push({ type: 'new', text: `Full-year actuals reported this quarter` });
    }
    if (t.includes('electricity') && !priorTitles.has(t)) {
      changes.push({ type: 'new', text: `NEW: Electricity cost impact quantified` });
    }
    if (t.includes('power supply') && !priorTitles.has(t)) {
      changes.push({ type: 'new', text: `NEW: Power supply assessment added` });
    }
  }

  if (changes.length === 0) {
    changes.push({ type: 'maintained', text: 'Key metrics largely maintained from prior quarter' });
  }

  return changes;
}

// Pretty label for quarter key
function qLabel(q) {
  const [qn, year] = q.split('_');
  return `${qn} ${year}`;
}

// Short nav label
function qShort(q) {
  const [qn, year] = q.split('_');
  return `${qn.replace('Q','')}Q${year.slice(2)}`;
}

// Quarter key for data-q attribute (matching main HTML)
function qDataAttr(q) {
  const [qn, year] = q.split('_');
  return `${qn.toLowerCase()}-${year.slice(2)}`;
}

function generateHTML(qKey, idx) {
  const parsed = parseMD(mdFile(qKey));
  const metrics = extractMetrics(parsed);
  const prevKey = idx > 0 ? QUARTERS[idx - 1] : null;
  const nextKey = idx < QUARTERS.length - 1 ? QUARTERS[idx + 1] : null;

  let priorParsed = null;
  let priorMetrics = null;
  if (prevKey) {
    priorParsed = parseMD(mdFile(prevKey));
    priorMetrics = extractMetrics(priorParsed);
  }

  const changes = generateChanges(metrics, priorMetrics, parsed, priorParsed || { sections: [] });

  // Build HTML
  let html = `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TSMC ${qLabel(qKey)} Earnings Call Detail</title>
<style>
  :root {
    --tsmc-red: #c0392b;
    --tsmc-dark: #1a1a2e;
    --tsmc-accent: #16213e;
    --green: #27ae60;
    --red: #e74c3c;
    --amber: #f39c12;
    --blue: #2980b9;
    --light-bg: #f8f9fa;
    --border: #dee2e6;
    --text: #2c3e50;
    --text-muted: #6c757d;
  }

  * { margin: 0; padding: 0; box-sizing: border-box; }

  body {
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
    color: var(--text);
    background: #fff;
    line-height: 1.6;
    max-width: 1000px;
    margin: 0 auto;
    padding: 0 24px 80px;
  }

  /* Header */
  .header {
    background: linear-gradient(135deg, var(--tsmc-dark), var(--tsmc-accent));
    color: #fff;
    padding: 40px 40px 32px;
    margin: 0 -24px 0;
    border-bottom: 4px solid var(--tsmc-red);
  }
  .header h1 {
    font-size: 2rem;
    font-weight: 700;
    margin-bottom: 6px;
    letter-spacing: -0.5px;
  }
  .header .meta {
    font-size: 0.95rem;
    opacity: 0.85;
    font-weight: 300;
  }
  .header .meta span { margin-right: 24px; }

  /* Navigation bar */
  .nav-bar {
    background: var(--tsmc-accent);
    margin: 0 -24px 32px;
    padding: 12px 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 8px;
  }
  .nav-bar a {
    color: #fff;
    text-decoration: none;
    font-size: 0.85rem;
    font-weight: 600;
    padding: 5px 14px;
    border-radius: 4px;
    border: 1px solid rgba(255,255,255,0.2);
    background: rgba(255,255,255,0.08);
    transition: all 0.15s;
  }
  .nav-bar a:hover { background: rgba(255,255,255,0.2); }
  .nav-bar a.disabled {
    opacity: 0.3;
    pointer-events: none;
  }
  .nav-center {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
    justify-content: center;
  }
  .nav-center a.qbtn {
    padding: 3px 8px;
    font-size: 0.72rem;
    font-weight: 600;
    border: 1px solid rgba(255,255,255,0.15);
    background: rgba(255,255,255,0.06);
  }
  .nav-center a.qbtn.current {
    background: var(--tsmc-red);
    border-color: var(--tsmc-red);
  }
  .nav-center a.qbtn:hover { background: rgba(255,255,255,0.2); }
  .nav-back {
    background: rgba(255,255,255,0.15) !important;
    border-color: rgba(255,255,255,0.35) !important;
  }

  /* Key Metrics Card */
  .metrics-card {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 16px;
    margin-bottom: 28px;
  }
  .metric {
    background: var(--light-bg);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 16px 20px;
    position: relative;
  }
  .metric-label {
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-muted);
    font-weight: 600;
    margin-bottom: 4px;
  }
  .metric-value {
    font-size: 1.3rem;
    font-weight: 700;
    color: var(--tsmc-dark);
  }
  .metric-delta {
    font-size: 0.78rem;
    margin-top: 4px;
    font-weight: 600;
  }
  .delta-up { color: var(--green); }
  .delta-down { color: var(--red); }
  .delta-flat { color: var(--text-muted); }

  /* What Changed Box */
  .changes-box {
    background: linear-gradient(135deg, #fef9e7, #fdebd0);
    border-left: 5px solid var(--amber);
    border-radius: 0 8px 8px 0;
    padding: 20px 24px;
    margin-bottom: 32px;
  }
  .changes-box h3 {
    font-size: 1rem;
    color: var(--tsmc-dark);
    margin-bottom: 10px;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .changes-box ul {
    list-style: none;
    padding: 0;
  }
  .changes-box li {
    padding: 5px 0;
    font-size: 0.9rem;
    display: flex;
    align-items: flex-start;
    gap: 8px;
  }
  .change-tag {
    display: inline-block;
    padding: 1px 8px;
    border-radius: 4px;
    font-size: 0.72rem;
    font-weight: 700;
    flex-shrink: 0;
    text-transform: uppercase;
    letter-spacing: 0.3px;
  }
  .ct-raised { background: #d5f5e3; color: #1e8449; }
  .ct-lowered { background: #fadbd8; color: #c0392b; }
  .ct-changed { background: #d6eaf8; color: #2471a3; }
  .ct-new { background: #e8daef; color: #6c3483; }
  .ct-maintained { background: #fdebd0; color: #b9770e; }

  /* Content Sections */
  .content-section {
    background: #fff;
    border: 1px solid var(--border);
    border-radius: 8px;
    margin-bottom: 20px;
    overflow: hidden;
  }
  .content-section h3 {
    background: var(--tsmc-accent);
    color: #fff;
    padding: 10px 18px;
    font-size: 0.92rem;
    font-weight: 600;
    letter-spacing: 0.3px;
  }
  .content-section ul {
    padding: 14px 18px 14px 36px;
    margin: 0;
  }
  .content-section li {
    padding: 3px 0;
    font-size: 0.88rem;
    line-height: 1.55;
  }
  .content-section li strong { color: var(--tsmc-dark); }

  /* Prior Quarter Reference */
  .prior-ref {
    border: 1px solid var(--border);
    border-radius: 8px;
    margin-top: 40px;
    overflow: hidden;
  }
  .prior-ref-header {
    background: var(--light-bg);
    padding: 12px 18px;
    font-size: 0.9rem;
    font-weight: 700;
    color: var(--tsmc-dark);
    border-bottom: 1px solid var(--border);
    cursor: pointer;
    user-select: none;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .prior-ref-header:hover { background: #eef2f7; }
  .prior-ref-body {
    padding: 18px;
    display: none;
  }
  .prior-ref-body.open { display: block; }
  .prior-ref-body .metric-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px;
    margin-bottom: 16px;
  }
  .prior-mini {
    background: var(--light-bg);
    padding: 10px 14px;
    border-radius: 6px;
    border: 1px solid var(--border);
  }
  .prior-mini .pm-label {
    font-size: 0.72rem;
    text-transform: uppercase;
    color: var(--text-muted);
    font-weight: 600;
  }
  .prior-mini .pm-value {
    font-size: 1rem;
    font-weight: 700;
    color: var(--tsmc-dark);
  }

  /* Footer nav */
  .footer-nav {
    display: flex;
    justify-content: space-between;
    margin-top: 40px;
    padding-top: 20px;
    border-top: 2px solid var(--border);
  }
  .footer-nav a {
    color: var(--blue);
    text-decoration: none;
    font-weight: 600;
    font-size: 0.9rem;
  }
  .footer-nav a:hover { text-decoration: underline; }

  @media (max-width: 768px) {
    .header h1 { font-size: 1.5rem; }
    .metrics-card { grid-template-columns: 1fr 1fr; }
    .nav-center { display: none; }
    body { padding: 0 16px 60px; }
    .header { margin: 0 -16px 0; padding: 28px 24px 20px; }
    .nav-bar { margin: 0 -16px 24px; }
  }

  @media print {
    .nav-bar { display: none; }
    .header { background: #333; }
  }
</style>
</head>
<body>
`;

  // Header
  html += `<div class="header">
  <h1>TSMC ${qLabel(qKey)} Earnings Call</h1>
  <div class="meta">
    <span>Call Date: ${parsed.callDate}</span>
    <span>Reporting: ${parsed.reportingQuarter}</span>
  </div>
</div>\n`;

  // Navigation bar
  html += `<div class="nav-bar">\n`;
  if (prevKey) {
    html += `  <a href="${prevKey}.html">&larr; ${qLabel(prevKey)}</a>\n`;
  } else {
    html += `  <a class="disabled">&larr; Prev</a>\n`;
  }

  html += `  <div class="nav-center">\n`;
  html += `    <a href="../TSMC_16Q_Guidance_Comparison.html" class="nav-back">Overview</a>\n`;
  for (const q of QUARTERS) {
    const cls = q === qKey ? ' current' : '';
    html += `    <a href="${q}.html" class="qbtn${cls}">${qShort(q)}</a>\n`;
  }
  html += `  </div>\n`;

  if (nextKey) {
    html += `  <a href="${nextKey}.html">${qLabel(nextKey)} &rarr;</a>\n`;
  } else {
    html += `  <a class="disabled">Next &rarr;</a>\n`;
  }
  html += `</div>\n\n`;

  // Key Metrics Card
  html += `<div class="metrics-card">\n`;

  function addMetric(label, value, priorValue) {
    if (!value) return;
    html += `  <div class="metric">\n`;
    html += `    <div class="metric-label">${label}</div>\n`;
    html += `    <div class="metric-value">${mdInline(value)}</div>\n`;
    if (priorValue && priorValue !== value) {
      html += `    <div class="metric-delta delta-flat">Prior: ${mdInline(priorValue)}</div>\n`;
    }
    html += `  </div>\n`;
  }

  if (metrics.guidanceFor) {
    html += `  <div class="metric" style="grid-column: 1 / -1; background: linear-gradient(135deg, var(--tsmc-dark), var(--tsmc-accent)); color: #fff; border: none;">
    <div class="metric-label" style="color: rgba(255,255,255,0.7);">Guidance For</div>
    <div class="metric-value" style="color: #fff;">${metrics.guidanceFor}</div>
  </div>\n`;
  }

  addMetric('Next-Q Revenue', metrics.revenue, priorMetrics?.revenue);
  addMetric('Next-Q Gross Margin', metrics.gm, priorMetrics?.gm);
  addMetric('Next-Q Operating Margin', metrics.om, priorMetrics?.om);
  if (metrics.fyRevenue) addMetric('FY Revenue Growth', metrics.fyRevenue, priorMetrics?.fyRevenue);
  if (metrics.capex) addMetric('CapEx', metrics.capex, priorMetrics?.capex);
  if (metrics.ltGM) addMetric('LT Gross Margin Target', metrics.ltGM, priorMetrics?.ltGM);

  html += `</div>\n\n`;

  // What Changed box
  html += `<div class="changes-box">\n`;
  html += `  <h3>${prevKey ? `What Changed vs ${qLabel(prevKey)}` : 'Context'}</h3>\n`;
  html += `  <ul>\n`;
  for (const c of changes) {
    const tagClass = `ct-${c.type}`;
    const tagLabel = c.type.charAt(0).toUpperCase() + c.type.slice(1);
    html += `    <li><span class="change-tag ${tagClass}">${tagLabel}</span> ${mdInline(c.text)}</li>\n`;
  }
  html += `  </ul>\n`;
  html += `</div>\n\n`;

  // Full Guidance Content — each section from the MD file
  html += `<!-- Full Guidance Content -->\n`;
  for (const sec of parsed.sections) {
    html += `<div class="content-section">\n`;
    html += `  <h3>${sec.title}</h3>\n`;
    if (sec.items.length > 0) {
      html += `  <ul>\n`;
      for (const item of sec.items) {
        html += `    <li>${mdInline(item)}</li>\n`;
      }
      html += `  </ul>\n`;
    }
    html += `</div>\n`;
  }

  // Prior Quarter Reference (collapsible)
  if (prevKey && priorParsed) {
    html += `\n<div class="prior-ref" id="priorRef">\n`;
    html += `  <div class="prior-ref-header" onclick="document.getElementById('priorBody').classList.toggle('open'); this.querySelector('.arrow').textContent = document.getElementById('priorBody').classList.contains('open') ? '&#9650;' : '&#9660;';">
    Prior Quarter Reference: ${qLabel(prevKey)}
    <span class="arrow">&#9660;</span>
  </div>\n`;
    html += `  <div class="prior-ref-body" id="priorBody">\n`;

    // Key metrics grid
    html += `    <div class="metric-grid">\n`;
    if (priorMetrics.revenue) {
      html += `      <div class="prior-mini"><div class="pm-label">Revenue Guidance</div><div class="pm-value">${mdInline(priorMetrics.revenue)}</div></div>\n`;
    }
    if (priorMetrics.gm) {
      html += `      <div class="prior-mini"><div class="pm-label">GM Guidance</div><div class="pm-value">${mdInline(priorMetrics.gm)}</div></div>\n`;
    }
    if (priorMetrics.om) {
      html += `      <div class="prior-mini"><div class="pm-label">OM Guidance</div><div class="pm-value">${mdInline(priorMetrics.om)}</div></div>\n`;
    }
    if (priorMetrics.capex) {
      html += `      <div class="prior-mini"><div class="pm-label">CapEx</div><div class="pm-value">${mdInline(priorMetrics.capex)}</div></div>\n`;
    }
    if (priorMetrics.fyRevenue) {
      html += `      <div class="prior-mini"><div class="pm-label">FY Revenue</div><div class="pm-value">${mdInline(priorMetrics.fyRevenue)}</div></div>\n`;
    }
    if (priorMetrics.ltGM) {
      html += `      <div class="prior-mini"><div class="pm-label">LT GM Target</div><div class="pm-value">${mdInline(priorMetrics.ltGM)}</div></div>\n`;
    }
    html += `    </div>\n`;
    html += `    <p style="font-size:0.82rem; color:var(--text-muted); margin-top:8px;"><a href="${prevKey}.html" style="color:var(--blue);">View full ${qLabel(prevKey)} detail &rarr;</a></p>\n`;
    html += `  </div>\n`;
    html += `</div>\n`;
  }

  // Footer navigation
  html += `\n<div class="footer-nav">\n`;
  if (prevKey) {
    html += `  <a href="${prevKey}.html">&larr; ${qLabel(prevKey)}</a>\n`;
  } else {
    html += `  <span></span>\n`;
  }
  html += `  <a href="../TSMC_16Q_Guidance_Comparison.html">Back to Overview</a>\n`;
  if (nextKey) {
    html += `  <a href="${nextKey}.html">${qLabel(nextKey)} &rarr;</a>\n`;
  } else {
    html += `  <span></span>\n`;
  }
  html += `</div>\n`;

  html += `\n</body>\n</html>`;

  return html;
}

// Generate all 16 pages
for (let i = 0; i < QUARTERS.length; i++) {
  const q = QUARTERS[i];
  const htmlContent = generateHTML(q, i);
  const outPath = path.join(OUT, `${q}.html`);
  fs.writeFileSync(outPath, htmlContent, 'utf-8');
  console.log(`Generated: ${outPath}`);
}

console.log('\nAll 16 quarter pages generated successfully.');
