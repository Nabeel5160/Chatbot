from app.rag_chain import FALLBACK_ANSWER, is_answer_grounded


def test_grounding_accepts_supported_answer_with_number() -> None:
    context = "Coca-Cola reported revenue of 45.8 billion in 2024."
    answer = "Revenue was 45.8 billion in 2024."
    assert is_answer_grounded(answer, context) is True


def test_grounding_rejects_unsupported_answer() -> None:
    context = "Coca-Cola reported revenue of 45.8 billion in 2024."
    answer = "Net profit margin was 33% in 2024."
    assert is_answer_grounded(answer, context) is False


def test_grounding_accepts_fallback_literal() -> None:
    assert is_answer_grounded(FALLBACK_ANSWER, "any context") is True
