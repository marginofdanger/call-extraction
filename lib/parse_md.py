#!/usr/bin/env python3
"""Generic markdown parser for earnings call guidance files."""

import re


def parse_md(filepath):
    """Parse a guidance markdown file into structured data.

    Returns dict with: title, call_date, reporting_quarter, sections (list of {title, items}).
    Items are either plain text strings or HTML table strings (starting with '<table').
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        raw = f.read()
    lines = raw.split('\n')
    call_date = ''
    reporting_quarter = ''
    title = ''
    sections = []
    current = None

    i = 0
    while i < len(lines):
        line = lines[i]

        if line.startswith('# ') and not line.startswith('## '):
            title = line.lstrip('# ').strip()
            i += 1
            continue
        if line.startswith('**Call Date:**'):
            m = re.match(
                r'\*\*Call Date:\*\*\s*(.+?)\s*\|\s*\*\*Reporting Quarter:\*\*\s*(.+)',
                line,
            )
            if m:
                call_date = m.group(1).strip()
                reporting_quarter = m.group(2).strip()
            i += 1
            continue
        if line.strip() == '---':
            i += 1
            continue
        if line.startswith('## '):
            sec_title = _clean_section_title(line.lstrip('# ').strip())
            current = {'title': sec_title, 'items': [], 'level': 2}
            sections.append(current)
            i += 1
            continue
        if line.startswith('### ') and current is not None:
            sec_title = _clean_section_title(line.lstrip('# ').strip())
            current = {'title': sec_title, 'items': [], 'level': 3}
            sections.append(current)
            i += 1
            continue

        # Detect markdown table blocks (lines starting with |)
        if line.strip().startswith('|') and current is not None:
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i])
                i += 1
            html = _md_table_to_html(table_lines)
            if html:
                current['items'].append(html)
            continue

        if line.startswith('- ') and current is not None:
            current['items'].append(line[2:].strip())
            i += 1
            continue
        if line.strip() and current is not None and not line.startswith('#'):
            if current['items']:
                current['items'][-1] += ' ' + line.strip()
            else:
                current['items'].append(line.strip())
        i += 1

    return {
        'title': title,
        'call_date': call_date,
        'reporting_quarter': reporting_quarter,
        'sections': sections,
    }


def _clean_section_title(title):
    """Clean section titles: strip 'On ' prefix from Q&A-style headers."""
    # Match "On [Topic] (Analyst Name, ...)" pattern common in Q&A sections
    if re.match(r'^On\s+[A-Z]', title):
        return title[3:]
    return title


def _md_table_to_html(table_lines):
    """Convert markdown pipe-table lines to an HTML <table> string."""
    if len(table_lines) < 2:
        return None

    rows = []
    for line in table_lines:
        stripped = line.strip().strip('|')
        # Skip separator lines like |---|---|
        if re.match(r'^[\s\-:|]+$', stripped):
            continue
        cells = [c.strip() for c in stripped.split('|')]
        rows.append(cells)

    if not rows:
        return None

    html = ['<table class="md-table">']
    # First row is header
    html.append('<thead><tr>')
    for cell in rows[0]:
        html.append(f'<th>{md_inline(cell)}</th>')
    html.append('</tr></thead>')

    # Remaining rows are data
    if len(rows) > 1:
        html.append('<tbody>')
        for row in rows[1:]:
            html.append('<tr>')
            for cell in row:
                html.append(f'<td>{md_inline(cell)}</td>')
            html.append('</tr>')
        html.append('</tbody>')

    html.append('</table>')
    return ''.join(html)


def md_inline(text):
    """Convert inline markdown (bold, italic, code) to HTML."""
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    return text
