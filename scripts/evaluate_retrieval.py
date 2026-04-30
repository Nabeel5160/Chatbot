import argparse
import json
from pathlib import Path

from app.api import get_services


def load_eval_set(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate retrieval quality (precision@k proxy).")
    parser.add_argument("--dataset", required=True, help="Path to JSON dataset.")
    args = parser.parse_args()

    dataset = load_eval_set(Path(args.dataset))
    services = get_services()
    retriever = services["retriever"]

    correct = 0
    total = 0
    for item in dataset:
        question = item["question"]
        expected_pages = set(item.get("expected_pages", []))
        result = retriever.retrieve(question)
        predicted_pages = {s.get("page") for s in result["sources"]}
        hit = bool(expected_pages.intersection(predicted_pages))
        correct += 1 if hit else 0
        total += 1
        print(f"Q: {question}\nExpected: {sorted(expected_pages)} | Pred: {sorted(predicted_pages)} | Hit={hit}\n")

    score = correct / max(1, total)
    print(f"precision_at_k_proxy={score:.3f} ({correct}/{total})")


if __name__ == "__main__":
    main()
