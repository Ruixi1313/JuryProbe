# Low-risk Specificity v1

This frozen control checks whether JuryProbe always flags panels as high-risk.

Artifact type: `evaluation`. Stage: `evaluation`. Pool manifests, build
manifests, and evaluation manifests are tracked separately.

The control reuses the grounded verifier cache. The same cheap judge jury sees the original statement as a trusted reference; no oracle or gold fallback is used.

- Results: `results/frozen/low_risk_specificity_v1/summary.json`
- Markdown summary: `results/frozen/low_risk_specificity_v1/summary.md`
- High-risk detected: `{'number': '0/10', 'entity': '0/10'}`
- Grounded verifier validation: 15 raw `parse_fail` verdicts retried, 0 final `parse_fail`
