#!/usr/bin/env python3
"""Batch EDGAR download for all companies, run sequentially with delays.

Downloads exhibits, parses tables (including Workiva hidden text),
fetches XBRL data, and downloads images from supplements.

Usage: python batch_edgar.py
"""

import os
import sys
import time

from edgar_download import (
    EdgarClient,
    download_exhibit_images,
    load_config,
    process_ticker,
)

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
SKIP_TICKERS = {"APO", "APP"}  # Already complete with images
DELAY_BETWEEN_TICKERS = 15  # seconds


def download_images_for_ticker(ticker):
    """Download all images referenced in exhibit HTM files for a ticker."""
    config = load_config(ticker)
    cik = config.get("company", {}).get("edgar_cik", "")
    if not cik:
        return 0

    client = EdgarClient()
    edgar_dir = os.path.join(PROJECT_ROOT, "companies", ticker, "edgar")
    if not os.path.isdir(edgar_dir):
        return 0

    total = 0
    for q in config.get("quarters", []):
        qid = q["id"]
        acc = q.get("edgar_8k_accession", "")
        if not acc:
            continue

        for suffix in ("press_release", "supplement"):
            fpath = os.path.join(edgar_dir, f"{qid}_{suffix}.htm")
            if os.path.exists(fpath):
                count = download_exhibit_images(client, cik, acc, fpath)
                if count:
                    print(f"    {qid} {suffix}: {count} image(s)")
                    total += count

    return total


def main():
    companies_dir = os.path.join(PROJECT_ROOT, "companies")
    tickers = sorted(
        d for d in os.listdir(companies_dir)
        if os.path.exists(os.path.join(companies_dir, d, "config.yaml"))
        and d not in SKIP_TICKERS
    )

    print(f"Processing {len(tickers)} tickers: {', '.join(tickers)}")
    print(f"Delay between tickers: {DELAY_BETWEEN_TICKERS}s")
    print()

    results = {}
    for i, ticker in enumerate(tickers):
        if i > 0:
            print(f"\n--- Waiting {DELAY_BETWEEN_TICKERS}s before next ticker ---\n")
            time.sleep(DELAY_BETWEEN_TICKERS)

        try:
            process_ticker(ticker)

            # Download images after exhibits are downloaded
            print(f"\n  Downloading images for {ticker}...")
            img_count = download_images_for_ticker(ticker)
            if img_count:
                print(f"  Total images: {img_count}")
            else:
                print(f"  No images to download")

            results[ticker] = "OK"
        except Exception as e:
            print(f"  ERROR processing {ticker}: {e}")
            results[ticker] = f"ERROR: {e}"

    # Final summary
    print(f"\n{'='*60}")
    print("BATCH EDGAR DOWNLOAD COMPLETE")
    print(f"{'='*60}")
    for ticker, status in sorted(results.items()):
        print(f"  {ticker}: {status}")


if __name__ == "__main__":
    main()
