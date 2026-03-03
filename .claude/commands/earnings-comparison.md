# Earnings Comparison Analysis Generator

Generate an editorial 16-quarter guidance evolution analysis for a company. This produces a hand-crafted, analytical HTML page — not a mechanical table dump.

**Argument:** `$ARGUMENTS` (ticker symbol, e.g., TSM, META, HCA)

## Reference

The gold standard is `TSMC_16Q_Guidance_Comparison.html` in the project root. Read it if you need to see the exact format, CSS, and editorial quality. Your output must match that level of polish.

## Step 1: Load Context

1. Parse the ticker from `$ARGUMENTS`.
2. Read `companies/{{TICKER}}/config.yaml` to get:
   - `company.name`, `company.ticker`, `company.sector`
   - `branding.primary`, `branding.dark`, `branding.accent` (CSS colors)
   - `quarters` list (IDs and call dates)
   - `extraction_context` (domain knowledge)
   - `topic_hints` (key topics to track)
   - `tracked_metrics` (key metrics and their labels)
3. Read ALL guidance MD files from `companies/{{TICKER}}/guidance/` (Q1_2022 through Q4_2025 — all 16 quarters).

## Step 2: Analyze the Data

Before writing any HTML, analyze across all 16 quarters:

### A. Identify Guidance Metrics
Find metrics that appear with numerical ranges across multiple quarters (e.g., revenue guidance, expense guidance, margin guidance, CapEx). For each:
- Track the range and midpoint each quarter
- Note whether raised, lowered, maintained, or newly introduced
- Calculate sequential changes (% or absolute)

### B. Identify Recurring Operational Metrics
Find KPIs reported most quarters (e.g., DAP, ad impressions, operating margin, admissions growth). These become their own table sections.

### C. Identify Intermittent / Evolving Disclosures
These are the most analytically interesting — topics that appear, evolve, or disappear over time:
- New strategic initiatives (AI strategy, new products, M&A)
- Headwinds/tailwinds that emerge and evolve (regulatory, macro, competitive)
- Technology/product roadmaps that progress quarter by quarter
- One-time events and their aftermath (restructuring, disasters, lawsuits)
- Long-term targets that get raised/lowered/reaffirmed

For each, trace the narrative arc across all quarters where it appears.

### D. Identify Key Takeaways
What are the 8-12 most important storylines from the full 16-quarter arc?

## Step 3: Design Section Layout

Based on your analysis, design 15-25 topical sections. Follow this ordering:

1. **Core guidance metrics first** (revenue guidance, margin guidance, expense guidance, CapEx guidance — whatever the company guides on)
2. **Full-year guidance evolution** (how annual guidance was raised/lowered through the year)
3. **Key operational metrics** (volume, engagement, pricing, margins)
4. **Intermittent strategic disclosures** (AI, new products, regulatory, restructuring, M&A, technology roadmap)
5. **Long-term targets** (multi-year growth targets, margin targets)
6. **Industry/macro context** (if relevant)
7. **Capital allocation** (buybacks, dividends, debt, CapEx allocation)
8. **Key Takeaways** (always the final section)

Each section should have its own table with columns appropriate to the data. Not every section needs the same column structure.

## Step 4: Generate the HTML

Write the output to `companies/{{TICKER}}/comparison.html`.

### HTML Structure

Use the exact same CSS framework as the TSMC reference. Replace CSS custom properties with company branding:

```css
:root {
  --company-primary: {{branding.primary}};  /* replaces --tsmc-red */
  --company-dark: {{branding.dark}};        /* replaces --tsmc-dark */
  --company-accent: {{branding.accent}};    /* replaces --tsmc-accent */
  --green: #27ae60;
  --red: #e74c3c;
  --amber: #f39c12;
  --blue: #2980b9;
  --light-bg: #f8f9fa;
  --border: #dee2e6;
  --text: #2c3e50;
  --text-muted: #6c757d;
}
```

### Required HTML Components

Every comparison page MUST include:

1. **Header** with company name, subtitle, quarter range
2. **Quarter navigation bar** — links to individual quarter HTML pages in `quarters/` directory, grouped by year (most recent first)
3. **Table of Contents** — numbered links to each section
4. **Sections** — each with:
   - Numbered heading with colored circle badge
   - Table with company-accent-colored header row
   - Year divider rows (`.year-divider`) separating data by year
   - Color-coded rows: `.raised` (green background), `.lowered` (red background)
   - Tags: `.tag-raised`, `.tag-lowered`, `.tag-maintained`, `.tag-new`
   - Color-coded values: `.pos` (green text), `.neg` (red text), `.bold`
   - `.muted` for "Not discussed" or missing data
   - **Insight box** after the table (not required for every section, but for most)
5. **Key Takeaways** — numbered insight cards (8-12 items)
6. **Footer** with data source attribution

### Table Design Principles

- **Group unchanged periods**: If guidance was the same for 4 consecutive quarters, show one row: "Apr '22 – Jan '23" instead of 4 identical rows
- **Year divider rows** separate data chronologically and can have contextual labels (e.g., "2024 — AI ACCELERATION", "2023 — YEAR OF EFFICIENCY")
- **Every quarter should appear** in guidance tables, even if guidance wasn't given that quarter (show the row with "Maintained" or "Not discussed")
- **Commentary column** for qualitative context (e.g., "Strong customer engagement", "First quantification")
- **Show the direction**: Use arrows, tags (Raised/Lowered/Maintained), and color coding to make trends immediately scannable

### Insight Boxes

After most tables, include an insight box:
```html
<div class="insight"><strong>Key Insight:</strong> [1-3 sentence analytical observation about the trend shown in the table]</div>
```

Insight boxes should highlight: inflection points, the overall arc, surprising changes, and what the data implies for the future.

### Key Takeaways Section

The final section should have 8-12 takeaway cards:
```html
<div class="takeaway">
  <div class="takeaway-num">1</div>
  <div class="takeaway-text"><strong>[Bold headline.]</strong> [Supporting detail with specific numbers.]</div>
</div>
```

Each takeaway should reference specific data points from the analysis.

## Editorial Quality Standards

- **Be specific**: Use exact numbers, ranges, and percentages from the guidance files. Never vague.
- **Show evolution**: The value of this page is seeing HOW things changed quarter to quarter. Always show the prior value when something changes.
- **Note the narrative**: Management's language matters. "Reaffirmed" vs "maintained" vs "on track" vs "raised" convey different signals.
- **Highlight inflection points**: Where did the story change? When did a new theme emerge? When was guidance first quantified?
- **Use "Not discussed" intentionally**: Showing when a topic was absent is as important as showing when it was present (e.g., AI wasn't discussed in 2022 for TSMC).
- **Year divider labels should tell a story**: "2023 — YEAR OF EFFICIENCY" or "2024 — AI ACCELERATION" — these contextualize the data.
- **Cross-reference**: Insight boxes should connect themes (e.g., "CapEx increase driven by AI infrastructure demand discussed in Section 6").

## Step 5: Verify

After generating, report:
- Total number of sections
- Total lines of HTML
- Any quarters with sparse data (may indicate extraction gaps)
- Suggest the user open the file in a browser to review

## Important Notes

- This is an EDITORIAL analysis. You are an analyst writing a research document, not a script generating tables.
- Read the TSMC reference (`TSMC_16Q_Guidance_Comparison.html`) if you haven't seen it — it defines the quality bar.
- The output should be a SINGLE self-contained HTML file with inline CSS.
- Every table cell value must come from the actual guidance MD files — never fabricate data.
- The individual quarter detail pages (in `quarters/`) are generated separately by `/earnings-generate`. This command only generates the comparison/overview page.
