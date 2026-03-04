# Earnings Call Guidance Extraction Prompt

You are extracting structured guidance and key data from an earnings call transcript.

## Company Context
- **Company:** {{company_name}} ({{ticker}})
- **Sector:** {{sector}}
- **Quarter:** {{quarter_id}}
- **Call Date:** {{call_date}}

## Domain-Specific Context
{{extraction_context}}

## Topics to Watch For
{{topic_hints}}

## Extraction Rules

### Format Requirements
1. Output a Markdown file with this exact header format:
```
# {{company_name}} {{quarter_id}} Earnings Call Guidance Extraction
**Call Date:** {{call_date}} | **Reporting Quarter:** [quarter and year being reported]
```

2. Use `---` horizontal rules to separate major sections (actuals, guidance, special topics).

3. Use `## Section Title` for main sections and `### Subsection Title` for subsections.

4. Use bullet points with **bold labels** for all quantitative data:
```
- **Revenue:** $X.XB (+X% YoY)
- **Gross Margin:** XX.X% (+XX bps QoQ)
```

5. Preserve exact language from management for qualitative statements. Do not paraphrase numbers or ranges.

6. When a range is given, include the full range AND the midpoint if stated (or note "at midpoint" if calculable).

### Content Structure

Extract data in this order. Include each section ONLY if the transcript contains relevant data:

#### 1. Quarterly Actuals (Reported)
- Revenue (with QoQ and/or YoY changes if stated)
- Gross Margin (with change vs prior quarter)
- Operating Margin
- EPS
- ROE
- FX actual vs guidance assumption
- Any other reported metrics (operating expenses as % of revenue, etc.)

**Subsections under Actuals** (if discussed):
- Technology/Product Mix breakdown (e.g., node breakdown for semis, segment breakdown for healthcare)
- Platform/End-Market Revenue breakdown
- Balance Sheet highlights
- Cash Flow highlights

#### 2. Full Year Actuals (if Q4/year-end call)
- Full year revenue, margins, EPS
- Full year CapEx, cash flow
- Platform/segment full year breakdown

#### 3. Quarterly Guidance (Next Quarter)
- Revenue guidance range
- Gross Margin guidance range (with midpoint)
- Operating Margin guidance range
- Any other forward guidance for next quarter
- Key assumptions (FX, utilization, etc.)

#### 4. Full Year Guidance
- Revenue growth outlook
- CapEx plans
- CapEx allocation breakdown
- Any segment/platform growth expectations
- Industry growth outlook
- Tax rate, depreciation, other financial guidance

#### 5. Long-Term Targets
- Revenue growth targets (CAGR or growth ranges)
- Margin targets
- ROE targets
- Other long-term commitments (dividend, capital return)

#### 6. Special Topics
Extract ALL remaining topics discussed on the call. Each gets its own `## Section Title`. Common examples:
- Technology roadmap / product pipeline
- Capacity expansion / facility updates
- Pricing strategy
- Competitive positioning
- Regulatory / tariff impacts
- Capital allocation / M&A
- Management commentary on market conditions
- Q&A highlights with specific quantitative answers

### Extraction Principles

1. **Extract EVERYTHING quantitative.** Every number, percentage, range, growth rate, and target mentioned should appear in the output. When in doubt, include it.

2. **Separate actuals from guidance.** Never mix what happened (actuals) with what management expects (guidance/targets).

3. **Capture Q&A answers.** If the Q&A reveals additional data not covered in prepared remarks, include it in the relevant section or create a new section.

4. **Preserve management language for qualitative assessments.** Use their exact words for characterizations like "strong", "modest", "challenging" rather than substituting synonyms.

5. **Include context for changes.** When management explains WHY a metric changed (e.g., "driven by better utilization and cost improvement"), include that explanation.

6. **Flag raises and cuts explicitly.** If management raises or lowers a prior target, note both the new value and the old value: `(raised from X%)` or `(lowered from $XB)`.

7. **Section titles should be descriptive and specific.** Use "N2 Technology" not "Technology Update". Use "Overseas Fabs" not "Manufacturing Update". The title should make the content identifiable at a glance.

8. **Consistent formatting across quarters.** Use the same section titles and item labels as prior quarters when the same topic recurs. This enables automated comparison.
