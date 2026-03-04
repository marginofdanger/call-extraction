#!/usr/bin/env python3
"""Generic markdown parser for earnings call guidance files."""

import re


def parse_md(filepath):
    """Parse a guidance markdown file into structured data.

    Returns dict with: title, call_date, reporting_quarter, sections (list of {title, items}).
    """
    with open(filepath, 'r', encoding='utf-8') as f:
        raw = f.read()
    lines = raw.split('\n')
    call_date = ''
    reporting_quarter = ''
    title = ''
    sections = []
    current = None

    for line in lines:
        if line.startswith('# ') and not line.startswith('## '):
            title = line.lstrip('# ').strip()
            continue
        if line.startswith('**Call Date:**'):
            m = re.match(
                r'\*\*Call Date:\*\*\s*(.+?)\s*\|\s*\*\*Reporting Quarter:\*\*\s*(.+)',
                line,
            )
            if m:
                call_date = m.group(1).strip()
                reporting_quarter = m.group(2).strip()
            continue
        if line.strip() == '---':
            continue
        if line.startswith('## '):
            current = {'title': line.lstrip('# ').strip(), 'items': [], 'level': 2}
            sections.append(current)
            continue
        if line.startswith('### ') and current is not None:
            # Subsection becomes its own section for display
            current = {'title': line.lstrip('# ').strip(), 'items': [], 'level': 3}
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

    return {
        'title': title,
        'call_date': call_date,
        'reporting_quarter': reporting_quarter,
        'sections': sections,
    }


def md_inline(text):
    """Convert inline markdown (bold, italic, code) to HTML."""
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    return text
