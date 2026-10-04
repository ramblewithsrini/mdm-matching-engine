# Who is who? A small MDM matching engine

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/ramblewithsrini/mdm-matching-engine/blob/main/mdm_walkthrough.ipynb)

The same customer often appears in several systems: spelt differently, with dates in different formats and addresses that disagree. **Master data management (MDM)** finds those matches, builds one trusted *golden record* per customer, and groups customers into *households*.

This repository is a small, readable MDM engine in Python that shows how that works, step by step, using ten fictional records.

## Try it in your browser

1. Click **Open in Colab** above. It's free and needs only a Google account, with nothing to install.
2. Choose **Runtime → Run all**.
3. Scroll to **Try it yourself**, change the weights and thresholds, and run the cell again.

## What it does

| Step | How it works |
| --- | --- |
| **Standardise** | Dates in any format; UK addresses with abbreviations expanded and postcodes normalised |
| **Match** | Compares every pair of records: names with Jaro–Winkler similarity, date of birth with partial credit, address, email. A weighted score out of 100. |
| **Decide** | **90+** merges automatically; **70–89** goes to a data steward for review; below 70 stays apart |
| **Golden record** | Survivorship rules pick the winning value for each field: the most trusted source (Policy, then Claims, then Marketing), the most recent or the most complete |
| **Households** | Customers with the same house number and postcode form a household |

## The trade-off

Daniel and Danielle Evans live at the same address and were born a year apart. At the default threshold they go to a data steward. Lower the automatic-merge threshold to 80 and they become one person.

That's the trade-off every MDM programme manages: set the bar too high and duplicates survive; set it too low and you merge strangers.

## Lessons from real programmes

- **Standardise addresses first.** In the UK that means Royal Mail's Postcode Address File (PAF). It does more for match rates than clever algorithms.
- **Agree which source you trust** before debating matching rules.
- **Tune thresholds against known duplicates,** then check them by sampling with data stewards, who also work the review queue.
- **Data quality is a people process** as much as a technology one.

## Run it on your own machine

```bash
python -m pip install -r requirements.txt
python mdm.py                       # one-line summary
python -m pytest                    # 14 tests
jupyter notebook mdm_walkthrough.ipynb
```

## Files

| File | What it is |
| --- | --- |
| `mdm.py` | The engine: standardising, matching, clustering, survivorship, households |
| `test_mdm.py` | Tests for each building block and for the behaviour above |
| `mdm_walkthrough.ipynb` | A step-by-step walkthrough with pandas |
| `data/sample.json` | Ten fictional records and the default settings |

## A note on scope

This illustrates the concepts with fictional data. It isn't any employer's algorithm, and production MDM platforms add much more: reference data, audit trails, unmerge, stewardship workflows and scale.

Built with an AI coding assistant; every line reviewed by me. MIT licence.
