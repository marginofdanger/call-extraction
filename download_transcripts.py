#!/usr/bin/env python3
"""Download all 16 TSMC earnings call transcript PDFs from BamSEC and convert to text.

Requires: Chrome with Claude-in-Chrome extension connected (for authenticated PDF URL retrieval).
This script navigates to each transcript, clicks the PDF button, captures the signed URL,
downloads the PDF, and extracts text using PyPDF2.
"""

import PyPDF2
import requests
import os
import sys

TRANSCRIPTS_DIR = r'C:\Users\AdrianOw\projects\Call-extraction\transcripts'
os.makedirs(TRANSCRIPTS_DIR, exist_ok=True)

# Quarter -> BamSEC transcript ID mapping
QUARTERS = {
    'Q4_2025': 'fcede2c4-3aa4-47aa-88e3-a2665176b8b4',
    'Q3_2025': '7de565b8-dca8-47eb-b882-8ae1e734d3ae',
    'Q2_2025': '3df54427-a429-4374-bb7b-22f0f6abab41',
    'Q1_2025': '5a1e416a-d755-4a66-ab26-99b6ed70d029',
    'Q4_2024': 'f3430ef3-20f1-4aba-9d54-0d0b6884e013',
    'Q3_2024': '5a6139b0-3bad-4788-90df-52fe5d4b1259',
    'Q2_2024': 'ab974356-9233-4415-9150-83a5bed5e77c',
    'Q1_2024': '60a0e27e-92eb-4e8f-9c14-dcec322a72af',
    'Q4_2023': '54fd1ab4-8dce-4c8c-9e83-add442e68d49',
    'Q3_2023': 'b9b11f9c-27a5-4b73-b316-f978834e453e',
    'Q2_2023': 'acabde37-b881-43b2-8d84-ccaceecee42a',
    'Q1_2023': '59218aae-b119-496d-8ff1-c6dd96740f02',
    'Q4_2022': 'ef9a588a-a98b-4c44-9dab-902169818205',
    'Q3_2022': 'ac29d73e-fb06-4822-9c8e-02e7062875a2',
    'Q2_2022': '5c6260c8-7957-4398-81cd-e3b7f681d119',
    'Q1_2022': '8ceb2f84-f4b7-446e-9c86-5459c3d338a3',
}


def download_pdf(quarter, transcript_id, signed_url):
    """Download PDF and extract text."""
    pdf_path = os.path.join(TRANSCRIPTS_DIR, f'TSMC_{quarter}_transcript.pdf')
    txt_path = os.path.join(TRANSCRIPTS_DIR, f'TSMC_{quarter}_transcript.txt')

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
    # When called with a signed URL and quarter, download that one
    if len(sys.argv) == 3:
        quarter = sys.argv[1]
        url = sys.argv[2]
        print(f'Downloading {quarter}...')
        download_pdf(quarter, QUARTERS.get(quarter, ''), url)
    else:
        print('Usage: python download_transcripts.py <QUARTER> <SIGNED_PDF_URL>')
        print('Quarters:', ', '.join(QUARTERS.keys()))
