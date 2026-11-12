# Search evaluation (2026-11-04)

> DRAFT relevance labels, written by Claude (an AI assistant) on 2026-11-04 by reading each of the 100 judgments' headnotes (the summary on page 1), not the search results. They have NOT been reviewed by a lawyer. Grades: 2 = on the topic of the query, 1 = partly relevant or a closely related issue; cases not listed are treated as not relevant. A legal reviewer should check and correct these before the results are relied on. Q01-Q22 are topic searches; Q23-Q28 (specific names, provisions and statutes) were added after the first run, because the first set had no searches of that kind.

28 search queries and 4 similar-case queries; top 10 results scored. P@5 = precision in the top 5, R@10 = recall in the top 10, MRR = mean reciprocal rank, nDCG@10 = ranking quality (1.0 = ideal order).

## Search: keyword vs semantic vs hybrid (current settings)

| mode | P@5 | R@10 | MRR | nDCG@10 |
|---|---|---|---|---|
| keyword | 0.186 | 0.463 | 0.571 | 0.488 |
| semantic | 0.471 | 1.000 | 0.964 | 0.936 |
| hybrid | 0.471 | 1.000 | 0.964 | 0.933 |

nDCG@10 per query:

| query | keyword | semantic | hybrid |
|---|---|---|---|
| Q01 land acquisition lapsed under Section 24(2) of the 2013 Act | 1.000 | 0.860 | 0.984 |
| Q02 acquisition of farmland cancelled because the owners were ne | 0.000 | 0.993 | 0.993 |
| Q03 murder conviction based only on circumstantial evidence | 0.380 | 0.993 | 0.993 |
| Q04 recovery of dead body on disclosure statement of accused und | 1.000 | 1.000 | 1.000 |
| Q05 High Court wrongly granted bail to the accused in a serious  | 0.000 | 0.987 | 0.987 |
| Q06 default bail when charge sheet not filed within 90 days | 0.000 | 0.797 | 0.797 |
| Q07 arrest and bail under the Prevention of Money Laundering Act | 1.000 | 1.000 | 1.000 |
| Q08 quashing of criminal proceedings under Section 482 CrPC | 0.185 | 1.000 | 0.815 |
| Q09 a business dispute about unpaid money was turned into a chea | 0.000 | 0.631 | 0.631 |
| Q10 pension of retired employee wrongly fixed or denied | 0.000 | 0.933 | 0.933 |
| Q11 dismissal from service after departmental inquiry for miscon | 0.000 | 0.821 | 0.821 |
| Q12 candidate hid a criminal case when applying for a police con | 0.000 | 0.624 | 0.624 |
| Q13 eligibility criteria for recruitment of teachers | 0.000 | 0.815 | 0.815 |
| Q14 stay of enforcement of an arbitral award | 0.726 | 0.960 | 0.960 |
| Q15 arbitrator fees and termination of the mandate of the arbitr | 0.826 | 1.000 | 1.000 |
| Q16 liability to pay service tax | 0.765 | 1.000 | 0.967 |
| Q17 suit for specific performance of an agreement to sell | 0.776 | 0.815 | 0.815 |
| Q18 bank recovering loan dues from a defaulting borrower under S | 0.000 | 0.987 | 0.987 |
| Q19 punishment for contempt of court for disobeying court orders | 0.000 | 1.000 | 1.000 |
| Q20 admission to medical courses and NEET counselling | 1.000 | 1.000 | 1.000 |
| Q21 landlord asked to strike off the tenant's defence for not de | 0.000 | 1.000 | 1.000 |
| Q22 permission to terminate a pregnancy | 1.000 | 1.000 | 1.000 |
| Q23 Vijay Mallya contempt for disbursing US$ 40 million | 1.000 | 1.000 | 1.000 |
| Q24 Section 6A of the DSPE Act approval before investigating sen | 1.000 | 1.000 | 1.000 |
| Q25 NSEL commodity exchange as a financial establishment under t | 1.000 | 1.000 | 1.000 |
| Q26 divorce for cruelty and irretrievable breakdown of marriage | 1.000 | 1.000 | 1.000 |
| Q27 jurisdiction of the Wakf Tribunal over a suit | 1.000 | 1.000 | 1.000 |
| Q28 gender cap on performers in cabaret licence conditions | 0.000 | 1.000 | 1.000 |

## Similar cases (current settings)

| query case | P@5 | R@10 | MRR | nDCG@10 |
|---|---|---|---|---|
| S1 SC-ESCR010000092023 | 1.000 | 1.000 | 1.000 | 0.954 |
| S2 SC-ESCR010001322022 | 0.400 | 0.750 | 1.000 | 0.659 |
| S3 SC-ESCR010000582023 | 1.000 | 1.000 | 1.000 | 1.000 |
| S4 SC-ESCR010001442023 | 0.400 | 0.750 | 1.000 | 0.767 |
| **average** | 0.700 | 0.875 | 1.000 | 0.845 |
