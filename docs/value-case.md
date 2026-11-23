# Value case: why each finding matters to a revenue team

Every claim below is labeled by its evidence:

- **Source**: quoted from a primary source, with a link. Anyone can check it in one click.
- **Research**: a published figure, quoted and attributed to whoever published it.
- **Hypothesis**: reasoning about sales impact. It's plausible, but unmeasured here. The last section shows how Apollo could measure it with its own data.

No figure here is invented. Where no reliable public figure exists, this document says so.

## Why SEC filings are a good signal source

- **Source.** Most 8-Ks arrive within days of the event. SEC: "Companies are required to make most 8-K disclosures within four business days of the triggering event and in some cases even earlier." ([SEC, *Investor Bulletin: How to Read an 8-K*](https://www.sec.gov/files/readan8k.pdf), May 2012)
- **Source.** They're filed because the event is material. SEC: "The types of information required to be disclosed on Form 8-K are generally considered to be 'material.'" (same bulletin)
- The data is free, structured, and comes from the company itself, so it isn't scraped news or a vendor's inference.

## Signals: what each 8-K item means, and the sales angle

All item descriptions below are quoted from the SEC bulletin above.

### Item 5.02: executive change

- **Source.** "If a high-level executive officer—such as the chief executive officer, president, chief financial officer, chief accounting officer or chief operating officer—retires, resigns or is terminated, the company must disclose that fact." Also: "The company also must disclose the appointment of any new director or high-level officers."
- **Hypothesis.** A new leader reviews the tools and vendors they inherit.
  - For a prospect, that review is an opening for outreach.
  - For an existing customer, it's a risk: the new leader may not keep tools they didn't choose. That makes it a useful alert for account managers.
- **What we deliberately don't claim.** Sales content often states that new executives make 60–70% of their vendor decisions in their first 90 days. We couldn't trace that figure to a study, and at least one published critique says the same. So it isn't used here.

### Item 2.01: completed acquisition or disposition

- **Source.** "If a company acquires or disposes of a significant amount of assets, the company must file an 8-K to describe the terms of the transaction. Examples include buying or merging with another company, or selling a business unit."
- **Hypothesis.** An integration means consolidating tools, teams and territories: a buying window. It also creates CRM work, such as parent-child links, duplicate records and reassigned owners.

### Item 2.05: restructuring or layoffs

- **Source.** "This item requires disclosure of restructuring plans under which the company will incur material charges. For example, the 8-K may report the company's decision to close some of its plants or stores or to lay off workers."
- **Hypothesis.** This is mainly a **risk** signal: budget cuts, fewer seats, a pause in buying. For a customer, it's an early warning that the account may shrink or churn. For a prospect, it may open an efficiency conversation. It can't promise a sale.

### Item 1.01: material agreement

- **Source.** "This item requires disclosure of certain material agreements not made in the ordinary course of business, or material amendments to those agreements."
- **Hypothesis (weakest).** A large new agreement, such as financing or a major partnership, can mean new initiatives and budget. The filing alone doesn't say which, so a rep must read it.

### Fiscal year end and former names

- **Hypothesis.** A known fiscal year end lets reps time outreach to budget planning, instead of assuming a calendar year. Three of the seven SEC-matched accounts in the sample (Salesforce, Walmart and NVIDIA) close their year on January 31.
- **Source (Apollo).** Former names help find duplicate records after a rename. Apollo's own guidance lists the cause: "Company data changes due to acquisitions, rebrands, and office closures." ([Apollo, *How Fast Does B2B Contact Data Decay*](https://www.apollo.io/insights/whats-the-average-rate-of-data-decay-in-a-b2b-contact-database-and-how-do-i-address-it))

## Corrections: why accurate firmographics matter

- **Hypothesis.** Territory assignment, lead routing and account scoring all read annual revenue, HQ state, industry and headcount. A wrong value sends an account to the wrong rep or the wrong tier. That misrouting cost is real, but it varies too much by company to put a number on here.
- **Research.** Gartner: "poor data quality costs organizations at least $12.9 million a year on average, according to Gartner research from 2020." ([Gartner, *Data Quality*](https://www.gartner.com/en/data-analytics/topics/data-quality); Gartner's site blocks automated reading, so the author checked this wording by hand on 2026-11-23.) It's an average across all data, not just CRM firmographics.
- **Research (secondary).** Apollo's guidance cites Only-B2B: "B2B data deteriorates at an average monthly rate of 2.1%, which compounds to roughly 22.5% annually." This is about **contact** data, not firmographics, and it's a secondary citation. We use it only to show that data goes stale on a timescale of months, not years.
- **Source (this project).** For public companies, the audit replaces estimates with figures the company filed itself, and links the filing. That's what lets a person approve a change quickly.
- **What the sample does *not* show.** The errors in `data/accounts.csv` were planted. The run proves the tool catches them; it doesn't measure how dirty a real CRM is.

## How Apollo could measure the hypotheses

None of this needs outside research. Apollo has the data.

1. **Signal lift.** Compare meeting and win rates for accounts contacted within N weeks of a 5.02, 2.01 or 2.05 filing against comparable accounts with no filing. Do the same for churn and contraction among existing customers.
2. **Fix acceptance.** Track the share of proposed fixes that people approve, broken down by confidence and source. A low acceptance rate on medium (Apollo-estimate) fixes means those rules need tightening.
3. **Routing impact.** Count accounts whose territory or tier changes after approved fixes are applied.
4. **Time saved.** Compare the time to review an account with linked evidence against manual research.

## Claim strength at a glance

| Claim | Strength |
|---|---|
| What each 8-K item covers; the four-business-day timing | Source (SEC) |
| Rebrands and acquisitions make company data go stale | Source (Apollo) |
| Data decays about 22.5% a year | Research, secondary, about contacts |
| Poor data quality costs at least $12.9M a year on average | Research (Gartner, 2020; wording checked by hand) |
| Executive changes open a buying window | Hypothesis; measure with item 1 above |
| Acquisitions create buying windows and CRM work | Hypothesis |
| Restructuring signals budget risk | Hypothesis |
| Fiscal year end improves outreach timing | Hypothesis |
| "60–70% of vendor decisions in 90 days" | Not used: no traceable source |
