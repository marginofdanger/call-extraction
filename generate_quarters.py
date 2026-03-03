#!/usr/bin/env python3
"""Generate 16 individual quarter detail HTML pages for TSMC earnings calls."""

import os
import re

BASE = r'C:\Users\AdrianOw\projects\Call-extraction'
OUT = os.path.join(BASE, 'quarters')
os.makedirs(OUT, exist_ok=True)

QUARTERS = [
    'Q1_2022','Q2_2022','Q3_2022','Q4_2022',
    'Q1_2023','Q2_2023','Q3_2023','Q4_2023',
    'Q1_2024','Q2_2024','Q3_2024','Q4_2024',
    'Q1_2025','Q2_2025','Q3_2025','Q4_2025',
]

def md_file(q):
    return os.path.join(BASE, f'TSMC_{q}_guidance.md')

def parse_md(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        raw = f.read()
    lines = raw.split('\n')
    call_date = ''
    reporting_quarter = ''
    title = ''
    sections = []
    current = None

    for line in lines:
        if line.startswith('# TSMC'):
            title = line.lstrip('# ').strip()
            continue
        if line.startswith('**Call Date:**'):
            m = re.match(r'\*\*Call Date:\*\*\s*(.+?)\s*\|\s*\*\*Reporting Quarter:\*\*\s*(.+)', line)
            if m:
                call_date = m.group(1).strip()
                reporting_quarter = m.group(2).strip()
            continue
        if line.strip() == '---':
            continue
        if line.startswith('## '):
            current = {'title': line.lstrip('# ').strip(), 'items': []}
            sections.append(current)
            continue
        if line.startswith('- ') and current is not None:
            current['items'].append(line[2:].strip())
            continue
        if line.strip() and current is not None and not line.startswith('#'):
            if current['items']:
                current['items'][-1] += ' ' + line.strip()
            else:
                current['items'].append(line.strip())

    return {'title': title, 'call_date': call_date, 'reporting_quarter': reporting_quarter, 'sections': sections}

def extract_metrics(parsed):
    m = {}
    for sec in parsed['sections']:
        t = sec['title'].lower()

        if t.startswith('quarterly guidance'):
            for item in sec['items']:
                if re.match(r'\*\*Revenue:?\*\*', item, re.I):
                    m['revenue'] = re.sub(r'^\*\*Revenue:?\*\*\s*', '', item, flags=re.I).strip()
                if re.match(r'\*\*Gross Margin:?\*\*', item, re.I):
                    m['gm'] = re.sub(r'^\*\*Gross Margin:?\*\*\s*', '', item, flags=re.I).strip()
                if re.match(r'\*\*Operating Margin:?\*\*', item, re.I):
                    m['om'] = re.sub(r'^\*\*Operating Margin:?\*\*\s*', '', item, flags=re.I).strip()
            guidance_for = re.sub(r'Quarterly Guidance\s*', '', sec['title']).strip('() ')
            m['guidance_for'] = guidance_for

        if 'full year' in t and 'guidance' in t:
            for item in sec['items']:
                if re.match(r'\*\*Revenue( growth)?:?\*\*', item, re.I):
                    m['fy_revenue'] = re.sub(r'^\*\*Revenue( growth)?:?\*\*\s*', '', item, flags=re.I).strip()
                if re.match(r'\*\*CapEx:?\*\*', item, re.I):
                    m['capex'] = re.sub(r'^\*\*CapEx:?\*\*\s*', '', item, flags=re.I).strip()

        if 'full year' in t and 'actuals' in t:
            for item in sec['items']:
                if re.match(r'\*\*Revenue:?\*\*', item, re.I):
                    m['fy_actual_revenue'] = re.sub(r'^\*\*Revenue:?\*\*\s*', '', item, flags=re.I).strip()
                if re.match(r'\*\*Gross Margin:?\*\*', item, re.I):
                    m['fy_actual_gm'] = re.sub(r'^\*\*Gross Margin:?\*\*\s*', '', item, flags=re.I).strip()
                if re.match(r'\*\*CapEx:?\*\*', item, re.I):
                    m['fy_actual_capex'] = re.sub(r'^\*\*CapEx:?\*\*\s*', '', item, flags=re.I).strip()

        if 'long-term' in t:
            for item in sec['items']:
                if re.match(r'\*\*Revenue CAGR:?\*\*', item, re.I):
                    m['lt_cagr'] = re.sub(r'^\*\*Revenue CAGR:?\*\*\s*', '', item, flags=re.I).strip()
                if re.match(r'\*\*Gross Margin:?\*\*', item, re.I):
                    m['lt_gm'] = re.sub(r'^\*\*Gross Margin:?\*\*\s*', '', item, flags=re.I).strip()

        if 'ai' in t:
            for item in sec['items']:
                il = item.lower()
                if 'ai revenue cagr' in il or 'ai accelerator revenue cagr' in il:
                    m['ai_cagr'] = re.sub(r'^\*\*.*?\*\*\s*', '', item).strip()
                elif 'ai revenue share' in il:
                    m['ai_share'] = re.sub(r'^\*\*.*?\*\*\s*', '', item).strip()

    return m

def md_inline(text):
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    return text

def parse_midpoint(s):
    if not s:
        return None
    match = re.search(r'\$?([\d.]+)B.*?\$?([\d.]+)B', s)
    if match:
        return (float(match.group(1)) + float(match.group(2))) / 2
    return None

def parse_gm_midpoint(s):
    if not s:
        return None
    match = re.search(r'([\d.]+)%.*?([\d.]+)%', s)
    if match:
        return (float(match.group(1)) + float(match.group(2))) / 2
    return None

def generate_changes(cur, prior, cur_parsed, prior_parsed, quarter_idx=0):
    changes = []
    if not prior:
        changes.append({'type': 'new', 'text': 'First quarter in our tracking series (Q1 2022)'})
        return changes

    # Revenue midpoint comparison
    cur_rev = parse_midpoint(cur.get('revenue'))
    prev_rev = parse_midpoint(prior.get('revenue'))
    if cur_rev and prev_rev:
        delta = (cur_rev - prev_rev) / prev_rev * 100
        if abs(delta) > 0.5:
            direction = 'up' if delta > 0 else 'down'
            changes.append({
                'type': 'raised' if delta > 0 else 'lowered',
                'text': f'Next-Q revenue guidance midpoint {direction} {abs(delta):.1f}% vs prior quarter (${cur_rev:.1f}B vs ${prev_rev:.1f}B)'
            })

    # GM midpoint comparison
    cur_gm = parse_gm_midpoint(cur.get('gm'))
    prev_gm = parse_gm_midpoint(prior.get('gm'))
    if cur_gm and prev_gm:
        delta = cur_gm - prev_gm
        if abs(delta) > 0.1:
            direction = 'up' if delta > 0 else 'down'
            changes.append({
                'type': 'raised' if delta > 0 else 'lowered',
                'text': f'GM guidance midpoint {direction} {abs(delta):.1f} ppts ({cur_gm:.1f}% vs {prev_gm:.1f}%)'
            })

    # CapEx comparison
    if cur.get('capex') and prior.get('capex') and cur['capex'] != prior['capex']:
        changes.append({'type': 'changed', 'text': f"CapEx guidance: {cur['capex']} (prior: {prior['capex']})"})

    # LT GM target
    if cur.get('lt_gm') and prior.get('lt_gm') and cur['lt_gm'] != prior['lt_gm']:
        changes.append({'type': 'raised', 'text': f"LT Gross Margin target changed: {cur['lt_gm']} (was: {prior['lt_gm']})"})

    # LT CAGR
    if cur.get('lt_cagr') and prior.get('lt_cagr') and cur['lt_cagr'] != prior['lt_cagr']:
        changes.append({'type': 'changed', 'text': f"LT Revenue CAGR updated: {cur['lt_cagr']} (was: {prior['lt_cagr']})"})

    # FY revenue guidance
    if cur.get('fy_revenue') and prior.get('fy_revenue') and cur['fy_revenue'] != prior['fy_revenue']:
        changes.append({'type': 'changed', 'text': f"Full-year revenue growth guidance: {cur['fy_revenue']} (was: {prior['fy_revenue']})"})

    # New sections check — track what we've already flagged to avoid duplicates
    prior_titles = set(s['title'].lower() for s in prior_parsed['sections'])
    flagged = set()
    for sec in cur_parsed['sections']:
        t = sec['title'].lower()
        if 'a16' in t and not any('a16' in pt for pt in prior_titles) and 'a16' not in flagged:
            flagged.add('a16')
            changes.append({'type': 'new', 'text': f"NEW: {sec['title']} first disclosed this quarter"})
        if 'tariff' in t and not any('tariff' in pt for pt in prior_titles) and 'tariff' not in flagged:
            flagged.add('tariff')
            changes.append({'type': 'new', 'text': 'NEW: Tariff impact discussion added'})
        # Only flag AI as truly "new" for the very first dedicated AI section (Q1 2023)
        # Not when a dedicated section reappears after being absent from the prior quarter
        if ('ai demand' in t or 'ai / generative ai' in t) and 'ai' not in flagged:
            # Check if AI was EVER discussed before (not just in the immediately prior quarter)
            is_first_ever_ai = (quarter_idx <= 4)  # Only Q1-Q4 2022 and Q1 2023 could be first
            if is_first_ever_ai and not any('ai' in pt for pt in prior_titles):
                flagged.add('ai')
                changes.append({'type': 'new', 'text': 'NEW: AI demand emerges as a discussion theme'})
        if 'actuals' in t and not any('actuals' in pt for pt in prior_titles) and 'actuals' not in flagged:
            flagged.add('actuals')
            changes.append({'type': 'new', 'text': 'Full-year actuals reported this quarter'})
        if 'electricity' in t and not any('electricity' in pt for pt in prior_titles) and 'electricity' not in flagged:
            flagged.add('electricity')
            changes.append({'type': 'new', 'text': 'NEW: Electricity cost impact quantified'})
        if 'power supply' in t and not any('power supply' in pt for pt in prior_titles) and 'power' not in flagged:
            flagged.add('power')
            changes.append({'type': 'new', 'text': 'NEW: Power supply assessment added'})
        if 'four growth' in t and not any('four growth' in pt for pt in prior_titles) and 'four_growth' not in flagged:
            flagged.add('four_growth')
            changes.append({'type': 'new', 'text': 'NEW: Four Growth Platforms framework introduced'})

    if not changes:
        changes.append({'type': 'maintained', 'text': 'Key metrics largely maintained from prior quarter'})

    return changes

def q_label(q):
    qn, year = q.split('_')
    return f'{qn} {year}'

def q_short(q):
    qn, year = q.split('_')
    return f"{qn.replace('Q','')}Q{year[2:]}"

CSS = """:root {
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

  .metrics-card {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 10px;
    margin-bottom: 24px;
  }
  .metric {
    background: var(--light-bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px 14px;
  }
  .metric-label {
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-muted);
    font-weight: 600;
    margin-bottom: 2px;
  }
  .metric-value {
    font-size: 0.92rem;
    font-weight: 700;
    color: var(--tsmc-dark);
  }
  .metric-delta {
    font-size: 0.72rem;
    margin-top: 2px;
    font-weight: 600;
  }
  .delta-up { color: var(--green); }
  .delta-down { color: var(--red); }
  .delta-flat { color: var(--text-muted); }

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
  }
  .changes-box ul { list-style: none; padding: 0; }
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
  .prior-ref-body { padding: 18px; display: none; }
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
    .metrics-card { grid-template-columns: 1fr 1fr; gap: 8px; }
    .nav-center { display: none; }
    body { padding: 0 16px 60px; }
    .header { margin: 0 -16px 0; padding: 28px 24px 20px; }
    .nav-bar { margin: 0 -16px 24px; }
  }

  @media print {
    .nav-bar { display: none; }
    .header { background: #333; }
  }"""

def generate_html(q_key, idx):
    parsed = parse_md(md_file(q_key))
    metrics = extract_metrics(parsed)
    prev_key = QUARTERS[idx - 1] if idx > 0 else None
    next_key = QUARTERS[idx + 1] if idx < len(QUARTERS) - 1 else None

    prior_parsed = parse_md(md_file(prev_key)) if prev_key else None
    prior_metrics = extract_metrics(prior_parsed) if prior_parsed else None

    changes = generate_changes(metrics, prior_metrics, parsed, prior_parsed or {'sections': []}, quarter_idx=idx)

    lines = []
    def w(s=''):
        lines.append(s)

    w('<!DOCTYPE html>')
    w('<html lang="en">')
    w('<head>')
    w('<meta charset="UTF-8">')
    w('<meta name="viewport" content="width=device-width, initial-scale=1.0">')
    w(f'<title>TSMC {q_label(q_key)} Earnings Call Detail</title>')
    w(f'<style>\n{CSS}\n</style>')
    w('</head>')
    w('<body>')
    w()

    # Header
    w('<div class="header">')
    w(f'  <h1>TSMC {q_label(q_key)} Earnings Call</h1>')
    w(f'  <div class="meta">')
    w(f'    <span>Call Date: {parsed["call_date"]}</span>')
    w(f'    <span>Reporting: {parsed["reporting_quarter"]}</span>')
    w(f'  </div>')
    w('</div>')

    # Nav bar
    w('<div class="nav-bar">')
    if prev_key:
        w(f'  <a href="{prev_key}.html">&larr; {q_label(prev_key)}</a>')
    else:
        w('  <a class="disabled">&larr; Prev</a>')

    w('  <div class="nav-center">')
    w('    <a href="../TSMC_16Q_Guidance_Comparison.html" class="nav-back">Overview</a>')
    for q in reversed(QUARTERS):
        cls = ' current' if q == q_key else ''
        w(f'    <a href="{q}.html" class="qbtn{cls}">{q_short(q)}</a>')
    w('  </div>')

    if next_key:
        w(f'  <a href="{next_key}.html">{q_label(next_key)} &rarr;</a>')
    else:
        w('  <a class="disabled">Next &rarr;</a>')
    w('</div>')
    w()

    # Key Metrics Card
    w('<div class="metrics-card">')

    if metrics.get('guidance_for'):
        w(f'  <div class="metric" style="grid-column: 1 / -1; background: linear-gradient(135deg, var(--tsmc-dark), var(--tsmc-accent)); color: #fff; border: none; padding: 8px 14px;">')
        w(f'    <div class="metric-label" style="color: rgba(255,255,255,0.7);">Guidance For</div>')
        w(f'    <div class="metric-value" style="color: #fff; font-size: 1rem;">{metrics["guidance_for"]}</div>')
        w(f'  </div>')

    def add_metric(label, key, prior_key=None):
        val = metrics.get(key)
        if not val:
            return
        w(f'  <div class="metric">')
        w(f'    <div class="metric-label">{label}</div>')
        w(f'    <div class="metric-value">{md_inline(val)}</div>')
        if prior_metrics and prior_key and prior_metrics.get(prior_key) and prior_metrics[prior_key] != val:
            w(f'    <div class="metric-delta delta-flat">Prior: {md_inline(prior_metrics[prior_key])}</div>')
        w(f'  </div>')

    add_metric('Next-Q Revenue', 'revenue', 'revenue')
    add_metric('Next-Q Gross Margin', 'gm', 'gm')
    add_metric('Next-Q Operating Margin', 'om', 'om')
    add_metric('FY Revenue Growth', 'fy_revenue', 'fy_revenue')
    add_metric('CapEx', 'capex', 'capex')
    add_metric('LT Gross Margin Target', 'lt_gm', 'lt_gm')

    w('</div>')
    w()

    # What Changed box
    w('<div class="changes-box">')
    if prev_key:
        w(f'  <h3>What Changed vs {q_label(prev_key)}</h3>')
    else:
        w(f'  <h3>Context</h3>')
    w('  <ul>')
    for c in changes:
        tag_cls = f"ct-{c['type']}"
        tag_label = c['type'].capitalize()
        w(f'    <li><span class="change-tag {tag_cls}">{tag_label}</span> {md_inline(c["text"])}</li>')
    w('  </ul>')
    w('</div>')
    w()

    # Full Guidance Content
    w('<!-- Full Guidance Content -->')
    for sec in parsed['sections']:
        w('<div class="content-section">')
        w(f'  <h3>{sec["title"]}</h3>')
        if sec['items']:
            w('  <ul>')
            for item in sec['items']:
                w(f'    <li>{md_inline(item)}</li>')
            w('  </ul>')
        w('</div>')

    # Prior Quarter Reference
    if prev_key and prior_parsed:
        w()
        w('<div class="prior-ref" id="priorRef">')
        w(f'  <div class="prior-ref-header" onclick="var b=document.getElementById(\'priorBody\');b.classList.toggle(\'open\');this.querySelector(\'.arrow\').innerHTML=b.classList.contains(\'open\')?\'&#9650;\':\'&#9660;\';">')
        w(f'    Prior Quarter Reference: {q_label(prev_key)}')
        w('    <span class="arrow">&#9660;</span>')
        w('  </div>')
        w('  <div class="prior-ref-body" id="priorBody">')
        w('    <div class="metric-grid">')

        def add_prior_mini(label, key):
            val = prior_metrics.get(key)
            if val:
                w(f'      <div class="prior-mini"><div class="pm-label">{label}</div><div class="pm-value">{md_inline(val)}</div></div>')

        add_prior_mini('Revenue Guidance', 'revenue')
        add_prior_mini('GM Guidance', 'gm')
        add_prior_mini('OM Guidance', 'om')
        add_prior_mini('CapEx', 'capex')
        add_prior_mini('FY Revenue', 'fy_revenue')
        add_prior_mini('LT GM Target', 'lt_gm')

        w('    </div>')
        w(f'    <p style="font-size:0.82rem;color:var(--text-muted);margin-top:8px;"><a href="{prev_key}.html" style="color:var(--blue);">View full {q_label(prev_key)} detail &rarr;</a></p>')
        w('  </div>')
        w('</div>')

    # Footer navigation
    w()
    w('<div class="footer-nav">')
    if prev_key:
        w(f'  <a href="{prev_key}.html">&larr; {q_label(prev_key)}</a>')
    else:
        w('  <span></span>')
    w('  <a href="../TSMC_16Q_Guidance_Comparison.html">Back to Overview</a>')
    if next_key:
        w(f'  <a href="{next_key}.html">{q_label(next_key)} &rarr;</a>')
    else:
        w('  <span></span>')
    w('</div>')

    w()
    w('</body>')
    w('</html>')

    return '\n'.join(lines)

# Generate all 16 pages
for i, q in enumerate(QUARTERS):
    html = generate_html(q, i)
    out_path = os.path.join(OUT, f'{q}.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f'Generated: {out_path}')

print('\nAll 16 quarter pages generated successfully.')
