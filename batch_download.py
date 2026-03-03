#!/usr/bin/env python3
"""Batch download TSMC transcripts given a file of signed PDF URLs.
Input: urls.txt with lines of format: QUARTER|FULL_URL
"""
import PyPDF2, requests, os, sys

TRANSCRIPTS_DIR = r'C:\Users\AdrianOw\projects\Call-extraction\transcripts'
os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)

def download_and_parse(quarter, url):
    pdf_path = os.path.join(TRANSCRIPTS_DIR, f'TSMC_{quarter}_transcript.pdf')
    txt_path = os.path.join(TRANSCRIPTS_DIR, f'TSMC_{quarter}_transcript.txt')

    if os.path.exists(txt_path) and os.path.getsize(txt_path) > 1000:
        print(f'  {quarter}: already exists ({os.path.getsize(txt_path)} chars), skipping')
        return True

    r = requests.get(url, timeout=30)
    if r.status_code != 200:
        print(f'  {quarter}: ERROR HTTP {r.status_code}')
        return False

    with open(pdf_path, 'wb') as f:
        f.write(r.content)

    reader = PyPDF2.PdfReader(pdf_path)
    full_text = ''
    for page in reader.pages:
        full_text += page.extract_text() + '\n'

    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(full_text)
    print(f'  {quarter}: {len(reader.pages)} pages, {len(full_text)} chars, {len(r.content)} bytes')
    return True

if __name__ == '__main__':
    urls_file = sys.argv[1] if len(sys.argv) > 1 else 'urls.txt'
    with open(urls_file) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            quarter, url = line.split('|', 1)
            download_and_parse(quarter, url)
    print('Done!')
