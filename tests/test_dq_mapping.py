"""Unit tests for the mapping between dbt tests and injected issue types."""

from dq.compare_answer_key import issue_for_test


def test_mapping_core_issue_types():
    assert issue_for_test("dq_not_null", "transactions", "amount") == "null_value"
    assert issue_for_test("dq_unique", "transactions", "transaction_id") == "duplicate_transaction_id"
    assert issue_for_test("dq_not_in_future", "transactions", "timestamp") == "future_timestamp"
    assert issue_for_test("dq_value_in_range", "transactions", "amount") == "negative_amount"
    assert issue_for_test("dq_referential_integrity", "transactions", "card_id") == "orphan_foreign_key"


def test_mapping_validity_checks_depend_on_column():
    assert issue_for_test("dq_matches_pattern", "transactions", "currency") == "currency_format"
    assert issue_for_test("dq_in_reference_list", "merchants", "mcc") == "invalid_mcc"
    assert issue_for_test("dq_in_reference_list", "transactions", "auth_response_code") is None


def test_unrelated_tests_are_not_scored():
    assert issue_for_test("dq_value_in_range", "transactions", "interchange_fee") is None
    assert issue_for_test("dq_unique", "merchants", "merchant_id") is None
    assert issue_for_test("dq_expression_is_true", "transactions", "is_approved") is None
