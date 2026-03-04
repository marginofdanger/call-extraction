# Earnings Call Setup

Set up a new company for earnings call extraction. The user provides a ticker symbol as the argument.

**Argument:** `$ARGUMENTS` (ticker symbol, e.g., NVDA, HCA, JPM)

## Instructions

1. **Parse the ticker** from `$ARGUMENTS`. If empty, ask the user for a ticker.

2. **Check if the company already exists** at `companies/{{TICKER}}/config.yaml`. If it does, tell the user and ask if they want to regenerate.

3. **Ask the user for company details:**
   - Full company name
   - Sector (offer common choices: Semiconductors, Healthcare, Insurance, Banking, SaaS, Automotive, Alt Assets, or custom)
   - Branding colors (primary + dark + accent) — suggest defaults based on company/sector
   - Fiscal year type: calendar or offset (and if offset, which month ends the fiscal year)
   - Which quarters to track (suggest recent 8-16 quarters)

4. **Generate `companies/{{TICKER}}/config.yaml`** using the reference config at `companies/TSM/config.yaml` as the schema template.

   Include sector-appropriate `tracked_metrics`. Here are templates by sector:

   **Semiconductors** (TSM, NVDA, AVGO):
   - revenue, gm, om, capex, fy_revenue, lt_gm, lt_cagr
   - Segment/product revenue breakdown, technology roadmap metrics

   **Healthcare / Hospitals** (HCA):
   - revenue, adjusted_ebitda, adjusted_ebitda_margin, same_facility_revenue_growth
   - Admissions, revenue_per_admission, payer_mix, capex
   - Same-facility metrics are critical for hospitals

   **Health Insurance** (UNH):
   - revenue, medical_care_ratio (MLR), operating_cost_ratio, adjusted_eps
   - Membership/enrollment, premium_growth, care_delivery_revenue
   - Medical care ratio is the key margin metric

   **Insurance / P&C** (PGR):
   - net_premiums_written, combined_ratio, loss_ratio, expense_ratio
   - Policies_in_force, premium_per_policy, investment_income
   - Combined ratio < 100% means underwriting profit

   **Banking** (JPM):
   - revenue, net_interest_income, noninterest_revenue, provision_for_credit_losses
   - CET1_ratio, ROTCE, net_charge_offs, loan_growth, deposit_growth
   - NII = Net Interest Income, ROTCE = Return on Tangible Common Equity

   **SaaS** (VEEV):
   - subscription_revenue, total_revenue, operating_margin, billings
   - NRR (net revenue retention), customer_count, fcf_margin
   - Subscription revenue and NRR are the key SaaS metrics

   **Alt Assets** (APO):
   - fee_related_earnings, spread_related_earnings, total_aum, inflows
   - FRE margin, retirement_services_revenue, management_fees
   - AUM = Assets Under Management, FRE = Fee Related Earnings

   **Automotive / Digital Retail** (CVNA):
   - revenue, retail_units_sold, gpu_per_unit, total_gpu
   - Adjusted_ebitda, sga_per_unit, inventory_turns
   - GPU = Gross Profit per Unit

   **AdTech / Mobile** (APP):
   - total_revenue, software_platform_revenue, apps_revenue
   - Adjusted_ebitda, adjusted_ebitda_margin, software_platform_margin
   - Software platform (advertising) is the high-margin growth driver

5. **Generate sector-appropriate `extraction_context`** with domain-specific terminology and abbreviations.

6. **Generate `topic_hints`** — 6-10 key topics to watch for based on the company's sector and business model.

7. **Create the directory structure:**
   ```
   companies/{{TICKER}}/
   ├── config.yaml
   ├── guidance/
   ├── transcripts/
   └── quarters/
   ```

8. **Ask the user for BamSEC transcript IDs** for each quarter. They can be added later — leave the `bamsec_id` field as `""` for now if not provided.

9. **Report what was created** and suggest next steps:
   - "Add transcripts to `companies/{{TICKER}}/transcripts/`"
   - "Run `/earnings-extract {{TICKER}} Q4_2025` to extract a quarter"
   - "Run `/earnings-generate {{TICKER}}` to build HTML pages"
