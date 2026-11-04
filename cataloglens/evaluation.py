"""Small labeled fixture evaluation, kept separate from the demonstration feeds."""

from collections import Counter
import hashlib
import json
from pathlib import Path

from .ai import PROMPT_VERSION, classify_claude
from .core import CATEGORIES, RULE_VERSION, ValidationError, classify_rules


def evaluate(path, *, provider="rules", classifier=None):
    raw = Path(path).read_bytes()
    cases = json.loads(raw)
    if not isinstance(cases, list) or not cases:
        raise ValidationError("evaluation set must be a nonempty array")
    if provider not in ("rules", "claude"):
        raise ValidationError("unknown evaluation provider")
    # Validate every label before any paid request.
    ids = set()
    for case in cases:
        if (not isinstance(case, dict) or not isinstance(case.get("id"), str)
            or case["id"] in ids or case.get("expected") not in CATEGORIES
            or not isinstance(case.get("title"), str) or not isinstance(case.get("description", ""), str)):
            raise ValidationError("invalid or duplicate evaluation case")
        ids.add(case["id"])
    confusion, outcomes = Counter(), []
    input_tokens = output_tokens = elapsed_ms = correct = abstentions = 0
    models = set()
    for case in cases:
        title, description = case["title"], case.get("description", "")
        if provider == "rules":
            predicted, evidence = classify_rules(title, description)
        else:
            suggestion = (classifier or classify_claude)(title, description)
            predicted, evidence = suggestion.category, suggestion.evidence
            input_tokens += suggestion.input_tokens
            output_tokens += suggestion.output_tokens
            elapsed_ms += suggestion.elapsed_ms
            models.add(suggestion.model)
        expected = case["expected"]
        correct += predicted == expected
        abstentions += predicted == "other"
        confusion[expected, predicted] += 1
        outcomes.append({"id": case["id"], "title": title, "expected": expected,
                         "predicted": predicted, "evidence": evidence, "correct": predicted == expected})
    by_category = {}
    for category in CATEGORIES:
        true_positive = confusion[category, category]
        predicted_count = sum(n for (actual, pred), n in confusion.items() if pred == category)
        actual_count = sum(n for (actual, pred), n in confusion.items() if actual == category)
        by_category[category] = {"precision": round(true_positive / predicted_count, 4) if predicted_count else None,
                                 "recall": round(true_positive / actual_count, 4) if actual_count else None,
                                 "support": actual_count}
    return {"provider": provider, "version": RULE_VERSION if provider == "rules" else PROMPT_VERSION,
            "dataset_sha256": hashlib.sha256(raw).hexdigest(), "cases": len(cases), "correct": correct,
            "accuracy": round(correct / len(cases), 4), "other_rate": round(abstentions / len(cases), 4),
            "per_category": by_category, "outcomes": outcomes, "models": sorted(models),
            "input_tokens": input_tokens, "output_tokens": output_tokens, "elapsed_ms": elapsed_ms,
            "scope": "Synthetic fixture results, not an estimate of production accuracy."}
