#!/usr/bin/env python3
"""Download earnings call transcript PDFs from BamSEC and convert to text.

Reads BamSEC transcript IDs from company config.yaml.

Usage:
  python download_transcript.py TICKER QUARTER SIGNED_PDF_URL
  python download_transcript.py TSM Q4_2025 https://...

The script downloads the PDF and extracts text using PyPDF2,
saving both to companies/TICKER/transcripts/.
"""

import os
import sys

import PyPDF2
import requests
import yaml

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = SCRIPT_DIR


def load_config(ticker):
    config_path = os.path.join(PROJECT_ROOT, 'companies', ticker, 'config.yaml')
    if not os.path.exists(config_path):
        print(f'Error: Config not found at {config_path}')
        print(f'Run /earnings-setup {ticker} first.')
        sys.exit(1)
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def get_transcript_id(config, quarter):
    for q in config.get('quarters', []):
        if q['id'] == quarter:
            return q.get('bamsec_id', '')
    return ''


def download_pdf(ticker, quarter, signed_url):
    """Download PDF and extract text to companies/TICKER/transcripts/."""
    transcripts_dir = os.path.join(PROJECT_ROOT, 'companies', ticker, 'transcripts')
    os.makedirs(transcripts_dir, exist_ok=True)

    pdf_path = os.path.join(transcripts_dir, f'{ticker}_{quarter}_transcript.pdf')
    txt_path = os.path.join(transcripts_dir, f'{ticker}_{quarter}_transcript.txt')

    # Download PDF
    r = requests.get(signed_url, timeout=30)
    if r.status_code != 200:
        print(f'  ERROR: HTTP {r.status_code}')
        return False

    with open(pdf_path, 'wb') as f:
        f.write(r.content)
    print(f'  PDF: {len(r.content)} bytes -> {pdf_path}')

    # Extract text
    reader = PyPDF2.PdfReader(pdf_path)
    full_text = ''
    for page in reader.pages:
        full_text += page.extract_text() + '\n'

    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(full_text)
    print(f'  TXT: {len(full_text)} chars, {len(reader.pages)} pages -> {txt_path}')
    return True


if __name__ == '__main__':
    if len(sys.argv) == 4:
        ticker = sys.argv[1].upper()
        quarter = sys.argv[2]
        url = sys.argv[3]

        config = load_config(ticker)
        transcript_id = get_transcript_id(config, quarter)
        print(f'Downloading {ticker} {quarter}...')
        if transcript_id:
            print(f'  BamSEC ID: {transcript_id}')
        download_pdf(ticker, quarter, url)
    else:
        print('Usage: python download_transcript.py TICKER QUARTER SIGNED_PDF_URL')
        print('Example: python download_transcript.py TSM Q4_2025 https://...')
        print()
        # If ticker provided, list available quarters
        if len(sys.argv) == 2:
            ticker = sys.argv[1].upper()
            config = load_config(ticker)
            quarters = [q['id'] for q in config.get('quarters', [])]
            print(f'Quarters for {ticker}: {", ".join(quarters)}')
