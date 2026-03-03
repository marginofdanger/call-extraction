#!/usr/bin/env python3
"""Generate individual quarter detail HTML pages and a comparison page for any company.

Usage: python lib/generate_company.py TICKER
Reads config from companies/TICKER/config.yaml, guidance MD from companies/TICKER/guidance/,
and outputs HTML to companies/TICKER/quarters/ and companies/TICKER/comparison.html.
"""

import os
import re
import sys

import yaml

# Resolve paths relative to the project root (one level up from lib/)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)

# Add lib/ to path for parse_md import
sys.path.insert(0, SCRIPT_DIR)
from parse_md import md_inline, parse_md


def load_config(ticker):
    config_path = os.path.join(PROJECT_ROOT, 'companies', ticker, 'config.yaml')
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def company_dir(ticker):
    return os.path.join(PROJECT_ROOT, 'companies', ticker)


def guidance_file(ticker, quarter_id):
    return os.path.join(company_dir(ticker), 'guidance', f'{quarter_id}_guidance.md')


def extract_metrics(parsed, config):
    """Extract tracked metrics from parsed MD using patterns from config.

    When a section_pattern matches a level-2 (##) section, also searches
    subsequent level-3 (###) subsections for the item_pattern.
    """
    tracked = config.get('tracked_metrics', {})
    m = {}
    sections = parsed['sections']

    for key, spec in tracked.items():
        section_pat = spec.get('section_pattern', '')
        item_pat = spec.get('item_pattern', '')
        extract_mode = spec.get('extract', '')

        for i, sec in enumerate(sections):
            t = sec['title']
            if not re.search(section_pat, t, re.I):
                continue

            # Build list: this section + child subsections (level 3)
            to_search = [sec]
            if sec.get('level', 2) == 2:
                for j in range(i + 1, len(sections)):
                    if sections[j].get('level', 2) == 2:
                        break
                    to_search.append(sections[j])

            # Special: extract from section title suffix (e.g., "Quarterly Guidance (Q1 2026)")
            if extract_mode == 'section_suffix':
                suffix = re.sub(r'^.*?(?:\()', '', t)
                suffix = suffix.rstrip(')')
                if suffix != t:
                    m[key] = suffix.strip()
                else:
                    match = re.search(section_pat, t, re.I)
                    if match:
                        remaining = t[match.end():].strip().strip('()')
                        if remaining:
                            m[key] = remaining
                break

            if not item_pat:
                continue

            found = False
            for search_sec in to_search:
                for item in search_sec['items']:
                    if re.match(item_pat, item, re.I):
                        val = re.sub(r'^\*\*.*?\*\*\s*', '', item).strip()
                        m[key] = val
                        found = True
                        break
                if found:
                    break

            if key in m:
                break

    return m


def parse_midpoint_dollars(s):
    """Parse dollar-billion midpoint from string like '$34.6B-$35.8B'."""
    if not s:
        return None
    match = re.search(r'\$?([\d.]+)\s*B.*?\$?([\d.]+)\s*B', s)
    if match:
        return (float(match.group(1)) + float(match.group(2))) / 2
    return None


def parse_midpoint_pct(s):
    """Parse percentage midpoint from string like '63%-65%'."""
    if not s:
        return None
    match = re.search(r'([\d.]+)\s*%.*?([\d.]+)\s*%', s)
    if match:
        return (float(match.group(1)) + float(match.group(2))) / 2
    return None


def simplify_for_card(val):
    """Simplify metric value for concise card display — strip verbose detail."""
    if not val:
        return val
    # Remove all parenthetical content (driver explanations, QoQ/YoY context)
    simplified = re.sub(r'\s*\([^)]*\)', '', val).strip()
    # If that removed everything meaningful, fall back to original
    if not simplified or len(simplified) < 3:
        return val
    return simplified.rstrip(',').strip()


def generate_changes(cur, prior, cur_parsed, prior_parsed, config, quarter_idx=0):
    """Generate list of changes between current and prior quarter."""
    changes = []
    if not prior:
        changes.append({'type': 'new', 'text': 'First quarter in our tracking series'})
        return changes

    tracked = config.get('tracked_metrics', {})

    for key, spec in tracked.items():
        comparison = spec.get('comparison', '')
        label = spec.get('label', key)
        cur_val = cur.get(key)
        prev_val = prior.get(key)

        if not cur_val or not prev_val:
            continue

        if comparison == 'midpoint_pct':
            fmt = spec.get('midpoint_format', '')
            if fmt == 'dollar_billions':
                cur_mid = parse_midpoint_dollars(cur_val)
                prev_mid = parse_midpoint_dollars(prev_val)
            elif fmt == 'percentage':
                cur_mid = parse_midpoint_pct(cur_val)
                prev_mid = parse_midpoint_pct(prev_val)
            else:
                continue

            if cur_mid and prev_mid:
                delta = (cur_mid - prev_mid) / prev_mid * 100
                if abs(delta) > 0.5:
                    direction = 'up' if delta > 0 else 'down'
                    if fmt == 'dollar_billions':
                        changes.append({
                            'type': 'raised' if delta > 0 else 'lowered',
                            'text': f'{label} midpoint {direction} {abs(delta):.1f}% vs prior quarter (${cur_mid:.1f}B vs ${prev_mid:.1f}B)',
                        })
                    else:
                        changes.append({
                            'type': 'raised' if delta > 0 else 'lowered',
                            'text': f'{label} midpoint {direction} {abs(delta):.1f}% vs prior quarter ({cur_mid:.1f}% vs {prev_mid:.1f}%)',
                        })

        elif comparison == 'midpoint_delta':
            fmt = spec.get('midpoint_format', '')
            if fmt == 'percentage':
                cur_mid = parse_midpoint_pct(cur_val)
                prev_mid = parse_midpoint_pct(prev_val)
            else:
                continue

            if cur_mid and prev_mid:
                delta = cur_mid - prev_mid
                if abs(delta) > 0.1:
                    direction = 'up' if delta > 0 else 'down'
                    changes.append({
                        'type': 'raised' if delta > 0 else 'lowered',
                        'text': f'{label} midpoint {direction} {abs(delta):.1f} ppts ({cur_mid:.1f}% vs {prev_mid:.1f}%)',
                    })

        elif comparison == 'text_diff':
            if cur_val != prev_val:
                changes.append({
                    'type': 'changed',
                    'text': f'{label}: {cur_val} (prior: {prev_val})',
                })

    # New section detection from config
    new_section_keywords = config.get('new_section_keywords', [])
    prior_titles = set(s['title'].lower() for s in prior_parsed['sections'])
    flagged = set()

    for sec in cur_parsed['sections']:
        t = sec['title'].lower()
        for kw in new_section_keywords:
            pattern = kw['pattern']
            kw_label = kw['label']
            first_only = kw.get('first_only', False)
            max_idx = kw.get('max_quarter_idx')
            flag_key = pattern.lower()

            if flag_key in flagged:
                continue
            if not re.search(pattern, t, re.I):
                continue
            if any(re.search(pattern, pt, re.I) for pt in prior_titles):
                continue
            if first_only and max_idx is not None and quarter_idx > max_idx:
                continue

            flagged.add(flag_key)
            changes.append({'type': 'new', 'text': f'NEW: {kw_label}'})

    if not changes:
        changes.append({'type': 'maintained', 'text': 'Key metrics largely maintained from prior quarter'})

    return changes


def q_label(q):
    """Convert Q1_2022 -> 'Q1 2022'."""
    qn, year = q.split('_')
    return f'{qn} {year}'


def q_short(q):
    """Convert Q1_2022 -> '1Q22'."""
    qn, year = q.split('_')
    return f"{qn.replace('Q', '')}Q{year[2:]}"


def build_css(config):
    """Build CSS with company-specific branding colors."""
    branding = config.get('branding', {})
    primary = branding.get('primary', '#c0392b')
    dark = branding.get('dark', '#1a1a2e')
    accent = branding.get('accent', '#16213e')

    return f""":root {{
    --company-primary: {primary};
    --company-dark: {dark};
    --company-accent: {accent};
    --green: #27ae60;
    --red: #e74c3c;
    --amber: #f39c12;
    --blue: #2980b9;
    --light-bg: #f8f9fa;
    --border: #dee2e6;
    --text: #2c3e50;
    --text-muted: #6c757d;
  }}

  * {{ margin: 0; padding: 0; box-sizing: border-box; }}

  body {{
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
    color: var(--text);
    background: #fff;
    line-height: 1.6;
    max-width: 1000px;
    margin: 0 auto;
    padding: 0 24px 80px;
  }}

  .header {{
    background: linear-gradient(135deg, var(--company-dark), var(--company-accent));
    color: #fff;
    padding: 40px 40px 32px;
    margin: 0 -24px 0;
    border-bottom: 4px solid var(--company-primary);
  }}
  .header h1 {{
    font-size: 2rem;
    font-weight: 700;
    margin-bottom: 6px;
    letter-spacing: -0.5px;
  }}
  .header .meta {{
    font-size: 0.95rem;
    opacity: 0.85;
    font-weight: 300;
  }}
  .header .meta span {{ margin-right: 24px; }}

  .nav-bar {{
    background: var(--company-accent);
    margin: 0 -24px 32px;
    padding: 12px 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 8px;
  }}
  .nav-bar a {{
    color: #fff;
    text-decoration: none;
    font-size: 0.85rem;
    font-weight: 600;
    padding: 5px 14px;
    border-radius: 4px;
    border: 1px solid rgba(255,255,255,0.2);
    background: rgba(255,255,255,0.08);
    transition: all 0.15s;
  }}
  .nav-bar a:hover {{ background: rgba(255,255,255,0.2); }}
  .nav-bar a.disabled {{
    opacity: 0.3;
    pointer-events: none;
  }}
  .nav-center {{
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
    justify-content: center;
  }}
  .nav-center a.qbtn {{
    padding: 3px 8px;
    font-size: 0.72rem;
    font-weight: 600;
    border: 1px solid rgba(255,255,255,0.15);
    background: rgba(255,255,255,0.06);
  }}
  .nav-center a.qbtn.current {{
    background: var(--company-primary);
    border-color: var(--company-primary);
  }}
  .nav-center a.qbtn:hover {{ background: rgba(255,255,255,0.2); }}
  .nav-back {{
    background: rgba(255,255,255,0.15) !important;
    border-color: rgba(255,255,255,0.35) !important;
  }}

  .metrics-card {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
    gap: 10px;
    margin-bottom: 24px;
  }}
  .metric {{
    background: var(--light-bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 10px 14px;
  }}
  .metric-label {{
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--text-muted);
    font-weight: 600;
    margin-bottom: 2px;
  }}
  .metric-value {{
    font-size: 0.92rem;
    font-weight: 700;
    color: var(--company-dark);
  }}
  .metric-delta {{
    font-size: 0.72rem;
    margin-top: 2px;
    font-weight: 600;
  }}
  .delta-up {{ color: var(--green); }}
  .delta-down {{ color: var(--red); }}
  .delta-flat {{ color: var(--text-muted); }}

  .changes-box {{
    background: linear-gradient(135deg, #fef9e7, #fdebd0);
    border-left: 5px solid var(--amber);
    border-radius: 0 8px 8px 0;
    padding: 20px 24px;
    margin-bottom: 32px;
  }}
  .changes-box h3 {{
    font-size: 1rem;
    color: var(--company-dark);
    margin-bottom: 10px;
  }}
  .changes-box ul {{ list-style: none; padding: 0; }}
  .changes-box li {{
    padding: 5px 0;
    font-size: 0.9rem;
    display: flex;
    align-items: flex-start;
    gap: 8px;
  }}
  .change-tag {{
    display: inline-block;
    padding: 1px 8px;
    border-radius: 4px;
    font-size: 0.72rem;
    font-weight: 700;
    flex-shrink: 0;
    text-transform: uppercase;
    letter-spacing: 0.3px;
  }}
  .ct-raised {{ background: #d5f5e3; color: #1e8449; }}
  .ct-lowered {{ background: #fadbd8; color: #c0392b; }}
  .ct-changed {{ background: #d6eaf8; color: #2471a3; }}
  .ct-new {{ background: #e8daef; color: #6c3483; }}
  .ct-maintained {{ background: #fdebd0; color: #b9770e; }}

  .content-section {{
    background: #fff;
    border: 1px solid var(--border);
    border-radius: 8px;
    margin-bottom: 20px;
    overflow: hidden;
  }}
  .content-section h3 {{
    background: var(--company-accent);
    color: #fff;
    padding: 10px 18px;
    font-size: 0.92rem;
    font-weight: 600;
    letter-spacing: 0.3px;
  }}
  .content-section ul {{
    padding: 14px 18px 14px 36px;
    margin: 0;
  }}
  .content-section li {{
    padding: 3px 0;
    font-size: 0.88rem;
    line-height: 1.55;
  }}
  .content-section li strong {{ color: var(--company-dark); }}

  .prior-ref {{
    border: 1px solid var(--border);
    border-radius: 8px;
    margin-top: 40px;
    overflow: hidden;
  }}
  .prior-ref-header {{
    background: var(--light-bg);
    padding: 12px 18px;
    font-size: 0.9rem;
    font-weight: 700;
    color: var(--company-dark);
    border-bottom: 1px solid var(--border);
    cursor: pointer;
    user-select: none;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}
  .prior-ref-header:hover {{ background: #eef2f7; }}
  .prior-ref-body {{ padding: 18px; display: none; }}
  .prior-ref-body.open {{ display: block; }}
  .prior-ref-body .metric-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px;
    margin-bottom: 16px;
  }}
  .prior-mini {{
    background: var(--light-bg);
    padding: 10px 14px;
    border-radius: 6px;
    border: 1px solid var(--border);
  }}
  .prior-mini .pm-label {{
    font-size: 0.72rem;
    text-transform: uppercase;
    color: var(--text-muted);
    font-weight: 600;
  }}
  .prior-mini .pm-value {{
    font-size: 1rem;
    font-weight: 700;
    color: var(--company-dark);
  }}

  .footer-nav {{
    display: flex;
    justify-content: space-between;
    margin-top: 40px;
    padding-top: 20px;
    border-top: 2px solid var(--border);
  }}
  .footer-nav a {{
    color: var(--blue);
    text-decoration: none;
    font-weight: 600;
    font-size: 0.9rem;
  }}
  .footer-nav a:hover {{ text-decoration: underline; }}

  /* Comparison page styles */
  .toc {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-bottom: 32px;
    padding: 20px;
    background: var(--light-bg);
    border-radius: 8px;
    border: 1px solid var(--border);
  }}
  .toc a {{
    color: var(--blue);
    text-decoration: none;
    font-size: 0.9rem;
    padding: 4px 0;
  }}
  .toc a:hover {{ text-decoration: underline; }}

  .comp-section {{
    margin-bottom: 40px;
  }}
  .comp-section h2 {{
    font-size: 1.2rem;
    color: var(--company-dark);
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 2px solid var(--company-primary);
  }}

  .comp-table {{
    width: 100%;
    border-collapse: collapse;
    margin-bottom: 16px;
    font-size: 0.85rem;
  }}
  .comp-table th {{
    background: var(--company-accent);
    color: #fff;
    padding: 8px 12px;
    text-align: left;
    font-weight: 600;
  }}
  .comp-table td {{
    padding: 8px 12px;
    border-bottom: 1px solid var(--border);
  }}
  .comp-table tr:nth-child(even) {{ background: var(--light-bg); }}
  .comp-table tr:hover {{ background: #e8f4fd; }}

  @media (max-width: 768px) {{
    .header h1 {{ font-size: 1.5rem; }}
    .metrics-card {{ grid-template-columns: 1fr 1fr; gap: 8px; }}
    .nav-center {{ display: none; }}
    body {{ padding: 0 16px 60px; }}
    .header {{ margin: 0 -16px 0; padding: 28px 24px 20px; }}
    .nav-bar {{ margin: 0 -16px 24px; }}
    .toc {{ grid-template-columns: 1fr; }}
    .comp-table {{ font-size: 0.78rem; }}
    .comp-table th, .comp-table td {{ padding: 6px 8px; }}
  }}

  @media print {{
    .nav-bar {{ display: none; }}
    .header {{ background: #333; }}
  }}"""


def generate_quarter_html(ticker, q_key, idx, quarters, config):
    """Generate a single quarter detail HTML page."""
    parsed = parse_md(guidance_file(ticker, q_key))
    metrics = extract_metrics(parsed, config)

    prev_key = quarters[idx - 1] if idx > 0 else None
    next_key = quarters[idx + 1] if idx < len(quarters) - 1 else None

    prior_parsed = parse_md(guidance_file(ticker, prev_key)) if prev_key else None
    prior_metrics = extract_metrics(prior_parsed, config) if prior_parsed else None

    changes = generate_changes(
        metrics, prior_metrics, parsed,
        prior_parsed or {'sections': []},
        config, quarter_idx=idx,
    )

    company_name = config['company']['name']
    ticker_label = config['company']['ticker']
    tracked = config.get('tracked_metrics', {})

    lines = []
    def w(s=''):
        lines.append(s)

    css = build_css(config)

    w('<!DOCTYPE html>')
    w('<html lang="en">')
    w('<head>')
    w('<meta charset="UTF-8">')
    w('<meta name="viewport" content="width=device-width, initial-scale=1.0">')
    w(f'<title>{ticker_label} {q_label(q_key)} Earnings Call Detail</title>')
    w(f'<style>\n{css}\n</style>')
    w('</head>')
    w('<body>')
    w()

    # Header
    w('<div class="header">')
    w(f'  <h1>{ticker_label} {q_label(q_key)} Earnings Call</h1>')
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
    w(f'    <a href="../comparison.html" class="nav-back">Overview</a>')
    w(f'    <a href="../results.html" class="nav-back">Results</a>')
    for q in reversed(quarters):
        cls = ' current' if q == q_key else ''
        w(f'    <a href="{q}.html" class="qbtn{cls}">{q_short(q)}</a>')
    w('  </div>')

    if next_key:
        w(f'  <a href="{next_key}.html">{q_label(next_key)} &rarr;</a>')
    else:
        w('  <a class="disabled">Next &rarr;</a>')
    w('</div>')
    w()

    # What Changed box (above metrics card)
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

    # Key Metrics Card
    w('<div class="metrics-card">')

    # Render metrics in config order
    for key, spec in tracked.items():
        val = metrics.get(key)
        if not val:
            continue

        label = spec.get('label', key)
        display = spec.get('display', 'card')

        if display == 'banner':
            w(f'  <div class="metric" style="grid-column: 1 / -1; background: linear-gradient(135deg, var(--company-dark), var(--company-accent)); color: #fff; border: none; padding: 8px 14px;">')
            w(f'    <div class="metric-label" style="color: rgba(255,255,255,0.7);">{label}</div>')
            w(f'    <div class="metric-value" style="color: #fff; font-size: 1rem;">{simplify_for_card(val)}</div>')
            w(f'  </div>')
        else:
            w(f'  <div class="metric">')
            w(f'    <div class="metric-label">{label}</div>')
            w(f'    <div class="metric-value">{md_inline(simplify_for_card(val))}</div>')
            if prior_metrics and prior_metrics.get(key) and prior_metrics[key] != val:
                w(f'    <div class="metric-delta delta-flat">Prior: {md_inline(simplify_for_card(prior_metrics[key]))}</div>')
            w(f'  </div>')

    w('</div>')
    w()

    # Full Guidance Content — guidance/outlook sections first, then actuals, then special topics
    def section_sort_key(sec):
        t = sec['title'].lower()
        if any(kw in t for kw in ['guidance', 'outlook', 'long-term', 'preliminary']):
            return 0  # Guidance first
        if any(kw in t for kw in ['actuals', 'reported', 'full year 20']):
            return 2  # Actuals after guidance
        return 1  # Special topics in between

    sorted_sections = sorted(parsed['sections'], key=section_sort_key)

    w('<!-- Full Guidance Content -->')
    for sec in sorted_sections:
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

        for key, spec in tracked.items():
            if spec.get('display') == 'banner':
                continue
            val = prior_metrics.get(key) if prior_metrics else None
            if val:
                label = spec.get('label', key)
                w(f'      <div class="prior-mini"><div class="pm-label">{label}</div><div class="pm-value">{md_inline(val)}</div></div>')

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
    w(f'  <a href="../comparison.html">Back to Overview</a>')
    if next_key:
        w(f'  <a href="{next_key}.html">{q_label(next_key)} &rarr;</a>')
    else:
        w('  <span></span>')
    w('</div>')

    w()
    w('</body>')
    w('</html>')

    return '\n'.join(lines)


def generate_comparison_html(ticker, quarters, config):
    """Generate the comparison overview page."""
    company_name = config['company']['name']
    ticker_label = config['company']['ticker']
    tracked = config.get('tracked_metrics', {})
    comp_sections = config.get('comparison_sections', [])

    # Load all quarter data
    all_data = {}
    for q in quarters:
        fpath = guidance_file(ticker, q)
        if os.path.exists(fpath):
            parsed = parse_md(fpath)
            metrics = extract_metrics(parsed, config)
            all_data[q] = {'parsed': parsed, 'metrics': metrics}

    css = build_css(config)

    lines = []
    def w(s=''):
        lines.append(s)

    w('<!DOCTYPE html>')
    w('<html lang="en">')
    w('<head>')
    w('<meta charset="UTF-8">')
    w('<meta name="viewport" content="width=device-width, initial-scale=1.0">')
    w(f'<title>{ticker_label} Guidance Evolution — {len(quarters)}-Quarter Comparison</title>')
    w(f'<style>\n{css}\n</style>')
    w('</head>')
    w('<body>')
    w()

    # Header
    w('<div class="header">')
    w(f'  <h1>{ticker_label} Guidance Evolution</h1>')
    w(f'  <div class="meta">')
    w(f'    <span>{len(quarters)}-Quarter Comparison</span>')
    w(f'    <span>{company_name}</span>')
    w(f'  </div>')
    w('</div>')

    # Nav bar with quarter links
    w('<div class="nav-bar">')
    w('  <div class="nav-center">')
    for q in reversed(quarters):
        w(f'    <a href="quarters/{q}.html" class="qbtn">{q_short(q)}</a>')
    w('  </div>')
    w('</div>')
    w()

    # Table of Contents
    if comp_sections:
        w('<div class="toc">')
        for i, sec in enumerate(comp_sections):
            anchor = f'section-{i}'
            w(f'  <a href="#{anchor}">{i + 1}. {sec["title"]}</a>')
        w('</div>')
        w()

    # Comparison sections
    for i, sec in enumerate(comp_sections):
        anchor = f'section-{i}'
        w(f'<div class="comp-section" id="{anchor}">')
        w(f'  <h2>{i + 1}. {sec["title"]}</h2>')

        columns = sec.get('columns', [])
        metric_keys = sec.get('metrics', [])
        single_key = sec.get('metric_key', '')

        if single_key:
            metric_keys = [single_key]

        w('  <table class="comp-table">')
        w('    <thead><tr>')
        for col in columns:
            w(f'      <th>{col}</th>')
        w('    </tr></thead>')
        w('    <tbody>')

        for q in quarters:
            data = all_data.get(q, {})
            metrics = data.get('metrics', {})

            w('    <tr>')
            w(f'      <td><a href="quarters/{q}.html" style="color:var(--blue);text-decoration:none;">{q_label(q)}</a></td>')

            if single_key:
                val = metrics.get(single_key, '—')
                w(f'      <td>{md_inline(val) if val != "—" else val}</td>')

                # Midpoint column if applicable
                spec = tracked.get(single_key, {})
                comparison = spec.get('comparison', '')
                fmt = spec.get('midpoint_format', '')

                if 'Midpoint' in columns:
                    if fmt == 'dollar_billions':
                        mid = parse_midpoint_dollars(val) if val != '—' else None
                        w(f'      <td>{f"${mid:.1f}B" if mid else "—"}</td>')
                    elif fmt == 'percentage':
                        mid = parse_midpoint_pct(val) if val != '—' else None
                        w(f'      <td>{f"{mid:.1f}%" if mid else "—"}</td>')
                    else:
                        w('      <td>—</td>')

                if 'vs Prior' in columns:
                    q_idx = quarters.index(q)
                    if q_idx > 0:
                        prev_q = quarters[q_idx - 1]
                        prev_data = all_data.get(prev_q, {})
                        prev_val = prev_data.get('metrics', {}).get(single_key, '')

                        if val != '—' and prev_val:
                            if comparison == 'midpoint_pct' and fmt == 'dollar_billions':
                                cur_mid = parse_midpoint_dollars(val)
                                prev_mid = parse_midpoint_dollars(prev_val)
                                if cur_mid and prev_mid:
                                    delta = (cur_mid - prev_mid) / prev_mid * 100
                                    color = 'var(--green)' if delta > 0 else 'var(--red)' if delta < 0 else 'var(--text-muted)'
                                    w(f'      <td style="color:{color};font-weight:600;">{delta:+.1f}%</td>')
                                else:
                                    w('      <td>—</td>')
                            elif comparison in ('midpoint_delta', 'midpoint_pct') and fmt == 'percentage':
                                cur_mid = parse_midpoint_pct(val)
                                prev_mid = parse_midpoint_pct(prev_val)
                                if cur_mid and prev_mid:
                                    delta = cur_mid - prev_mid
                                    color = 'var(--green)' if delta > 0 else 'var(--red)' if delta < 0 else 'var(--text-muted)'
                                    w(f'      <td style="color:{color};font-weight:600;">{delta:+.1f} ppts</td>')
                                else:
                                    w('      <td>—</td>')
                            else:
                                w(f'      <td>{"Changed" if val != prev_val else "—"}</td>')
                        else:
                            w('      <td>—</td>')
                    else:
                        w('      <td>—</td>')
            else:
                # Multiple metrics in one row
                for mk in metric_keys:
                    val = metrics.get(mk, '—')
                    w(f'      <td>{md_inline(val) if val != "—" else val}</td>')

            w('    </tr>')

        w('    </tbody>')
        w('  </table>')
        w('</div>')
        w()

    w('</body>')
    w('</html>')

    return '\n'.join(lines)


def main():
    if len(sys.argv) < 2:
        print('Usage: python lib/generate_company.py TICKER')
        print('Example: python lib/generate_company.py TSM')
        sys.exit(1)

    ticker = sys.argv[1].upper()
    config = load_config(ticker)

    quarters = [q['id'] for q in config['quarters']]
    out_dir = os.path.join(company_dir(ticker), 'quarters')
    os.makedirs(out_dir, exist_ok=True)

    # Check which guidance files exist
    available = []
    missing = []
    for q in quarters:
        fpath = guidance_file(ticker, q)
        if os.path.exists(fpath):
            available.append(q)
        else:
            missing.append(q)

    if missing:
        print(f'Note: Missing guidance files for: {", ".join(missing)}')
        print(f'Generating pages for {len(available)} available quarters.')

    if not available:
        print('Error: No guidance files found. Run /earnings-extract first.')
        sys.exit(1)

    # Generate quarter detail pages
    for i, q in enumerate(available):
        # Use index within the available list for prev/next navigation
        html = generate_quarter_html(ticker, q, i, available, config)
        out_path = os.path.join(out_dir, f'{q}.html')
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(html)
        print(f'Generated: {out_path}')

    # Generate comparison page (skip if editorial version exists)
    comp_path = os.path.join(company_dir(ticker), 'comparison.html')
    if os.path.exists(comp_path) and '--force-comparison' not in sys.argv:
        print(f'Skipped: {comp_path} (already exists; use --force-comparison to overwrite)')
    else:
        comp_html = generate_comparison_html(ticker, available, config)
        with open(comp_path, 'w', encoding='utf-8') as f:
            f.write(comp_html)
        print(f'Generated: {comp_path}')

    print(f'\nAll {len(available)} quarter pages generated for {ticker}.')


if __name__ == '__main__':
    main()
