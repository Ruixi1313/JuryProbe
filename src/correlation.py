"""Inter-judge error correlation analysis.

For a set of judges evaluating the same items with known ground truth,
compute:
  - per-judge accuracy
  - pairwise error correlation (Pearson r on binary error vectors)
  - false consensus rate (P(all wrong | all agree))
"""
from __future__ import annotations

from typing import Dict, List, Tuple


def _pearson(x: List[int], y: List[int]) -> float:
    n = len(x)
    if n == 0:
        return 0.0
    mx, my = sum(x) / n, sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    sx = sum((xi - mx) ** 2 for xi in x) ** 0.5
    sy = sum((yi - my) ** 2 for yi in y) ** 0.5
    if sx == 0 or sy == 0:
        return 0.0
    return num / (sx * sy)


def per_judge_accuracy(verdicts: Dict[str, List[str]],
                       ground_truth: List[str]) -> Dict[str, float]:
    out = {}
    for judge, vlist in verdicts.items():
        correct = sum(1 for v, g in zip(vlist, ground_truth) if v == g)
        out[judge] = correct / len(ground_truth) if ground_truth else 0.0
    return out


def error_vectors(verdicts: Dict[str, List[str]],
                  ground_truth: List[str]) -> Dict[str, List[int]]:
    """Binary error indicator per judge: 1 if wrong, 0 if right."""
    return {
        judge: [0 if v == g else 1 for v, g in zip(vlist, ground_truth)]
        for judge, vlist in verdicts.items()
    }


def pairwise_error_correlation(verdicts: Dict[str, List[str]],
                               ground_truth: List[str]) -> Dict[Tuple[str, str], float]:
    errs = error_vectors(verdicts, ground_truth)
    judges = list(errs.keys())
    out = {}
    for i, j1 in enumerate(judges):
        for j2 in judges[i + 1:]:
            out[(j1, j2)] = _pearson(errs[j1], errs[j2])
    return out


def false_consensus_rate(verdicts: Dict[str, List[str]],
                         ground_truth: List[str]) -> float:
    """P(all wrong | all agree). Higher = stronger 'agreement is not accuracy'."""
    judges = list(verdicts.keys())
    n = len(ground_truth)
    n_agree = 0
    n_agree_wrong = 0
    for i in range(n):
        votes = [verdicts[j][i] for j in judges]
        if len(set(votes)) == 1:
            n_agree += 1
            if votes[0] != ground_truth[i]:
                n_agree_wrong += 1
    return n_agree_wrong / n_agree if n_agree else 0.0


def summarize(verdicts: Dict[str, List[str]],
              ground_truth: List[str]) -> Dict:
    accs = per_judge_accuracy(verdicts, ground_truth)
    corrs = pairwise_error_correlation(verdicts, ground_truth)
    avg_corr = sum(corrs.values()) / len(corrs) if corrs else 0.0
    fc = false_consensus_rate(verdicts, ground_truth)
    return {
        "per_judge_accuracy": accs,
        "pairwise_error_correlation": {f"{a}__{b}": v for (a, b), v in corrs.items()},
        "avg_pairwise_correlation": avg_corr,
        "false_consensus_rate": fc,
    }
