# Two-minute walkthrough

Run from the repository root:

```sh
python -m cataloglens demo
python -m cataloglens serve
```

1. Open `http://127.0.0.1:8000`. The import shows 26 incoming records and 19 offers.
2. Search `wireless`, select `headphones`, set the maximum to `80.00`. The results
   are stored offers ordered by price, not model-written recommendations.
3. Inspect the Aero offer from Harbor. It costs USD 74.90, normalized from `74,90`
   in the JSON source. Northstar sells the same named model for USD 79.90; both
   remain separate offers. The tool does not prove they are identical products.
4. Open **Data quality**. Inspect an unsupported currency, an empty title and
   the conflicting Mesa speaker prices. Both conflicting records were quarantined.
5. Open **Evaluation**. The baseline calls a paper notebook a laptop and an empty
   headphone case headphones. It scores 75% on the 24-case fixture. Explain why
   these failures matter before introducing an LLM.
6. Open **AI review queue**. Without a key it is intentionally empty. The demo
   does not show fabricated model output. Explain the optional CLI flow: selected
   text goes to Claude, a literal quote is checked and a human reviews the label.

## Questions worth answering in an interview

- Why use integer cents instead of `float`?
- Why quarantine a price conflict rather than choose the last record?
- Does a quote prove a classification is correct? (No.)
- What can the keyword baseline do when source text contains instructions?
- What evidence would justify paying for an LLM on this task?
- Why is 75% on a small synthetic fixture not production accuracy?
- How would you handle cross-merchant identity, feed updates and millions of rows?

The project demonstrates a small data quality workflow and its limitations. It
does not demonstrate a production shopping assistant or a trained AI model.
