"""
Feature 3: 8-feature "standard" model vs. 23-feature "comprehensive" model
routing, required/optional field split, and the chat-based extract-into-form
flow. Model selection is purely a function of exactly how many of the 23
fields are present — never a partial run of the full model with the gap
filled by medians/modes (that combination was benchmarked and found worse:
PR-AUC 0.8259 vs. 0.8305 for the dedicated 8-feature model).
"""
import pytest
from fastapi.testclient import TestClient

from app.chat.fraud.engine import COMPREHENSIVE_TIER, STANDARD_TIER, predict
from app.chat.fraud.extraction import extract_fraud_features
from app.chat.fraud.schema import ALL_FIELDS, CORE_REQUIRED_FIELDS, OPTIONAL_FIELDS
from app.chat.fraud.validation import validate_fraud_features
from app.main import app

client = TestClient(app)

_CORE_VALUES = {
    "Net_Profit": 500000,
    "Taxable_Income": 800000,
    "Declared_Tax": 150000,
    "Previous_Violations": 1,
    "Cash_Transactions_Percentage": 20.5,
    "Invoice_Mismatch": 2,
    "Tax_Gap": 50000,
    "Industry_Risk": "Medium",
}

_OPTIONAL_VALUES = {
    "Years_in_Business": 5,
    "Employee_Count": 10,
    "Annual_Revenue": 2000000,
    "Annual_Expenses": 1200000,
    "Expected_Tax": 160000,
    "VAT_Collected": 100000,
    "VAT_Paid": 90000,
    "Previous_Audits": 0,
    "Late_Payments": 0,
    "Missing_Documents": 0,
    "Expense_Ratio": 0.6,
    "Profit_Margin": 0.25,
    "Revenue_per_Employee": 200000,
    "Business_Type": "Retail",
    "Region": "Cairo",
}


def test_core_required_fields_are_exactly_eight():
    assert len(CORE_REQUIRED_FIELDS) == 8


def test_all_23_fields_partitioned_into_required_and_optional():
    assert set(CORE_REQUIRED_FIELDS) | set(OPTIONAL_FIELDS) == set(ALL_FIELDS)
    assert set(CORE_REQUIRED_FIELDS) & set(OPTIONAL_FIELDS) == set()
    assert len(OPTIONAL_FIELDS) == 15


# --- 1. Exactly 8 valid fields -> 8-feature (Standard) model -----------------


def test_exactly_eight_fields_routes_to_standard_tier():
    result = predict(dict(_CORE_VALUES))
    assert result["tier"] == STANDARD_TIER
    assert result["fields_provided"] == 8
    assert result["fields_total"] == 23
    assert isinstance(result["probability"], float)
    assert result["label"] in ("Suspicious", "Not suspicious")


# --- 2. 9, 15, or 22 fields -> still routes to Standard tier -----------------


@pytest.mark.parametrize("extra_count", [1, 7, 14])
def test_partial_optional_fields_still_routes_to_standard_tier(extra_count):
    values = dict(_CORE_VALUES)
    extra_items = list(_OPTIONAL_VALUES.items())[:extra_count]
    values.update(dict(extra_items))
    expected_total_provided = 8 + extra_count

    result = predict(values)

    assert result["tier"] == STANDARD_TIER
    assert result["fields_provided"] == expected_total_provided
    assert expected_total_provided < 23


def test_extra_fields_are_not_lost_even_though_unused_by_standard_model():
    """Preserving user effort: the extra fields stay in the caller's dict, just aren't fed to the core model."""
    values = dict(_CORE_VALUES)
    values["Years_in_Business"] = 5
    values["Employee_Count"] = 10

    predict(values)  # runs the core model

    # The caller's dict (what graph.py stores as confirmed_features/session
    # state) is untouched — nothing was stripped out by predict() itself.
    assert values["Years_in_Business"] == 5
    assert values["Employee_Count"] == 10


# --- 3. All 23 valid fields -> full (Comprehensive) model --------------------


def test_all_23_fields_routes_to_comprehensive_tier():
    values = {**_CORE_VALUES, **_OPTIONAL_VALUES}
    assert len(values) == 23

    result = predict(values)

    assert result["tier"] == COMPREHENSIVE_TIER
    assert result["fields_provided"] == 23
    assert result["fields_total"] == 23


# --- 4. Missing any of the 8 required fields blocks prediction ---------------


@pytest.mark.parametrize("missing_field", CORE_REQUIRED_FIELDS)
def test_missing_any_required_field_fails_validation(missing_field):
    values = dict(_CORE_VALUES)
    del values[missing_field]

    errors = validate_fraud_features(values)

    assert any(missing_field in e for e in errors)


def test_all_eight_required_fields_present_passes_validation():
    errors = validate_fraud_features(dict(_CORE_VALUES))
    assert errors == []


def test_missing_optional_fields_does_not_fail_validation():
    """Only the 8 core fields are required — an otherwise-empty form beyond them is fine."""
    errors = validate_fraud_features(dict(_CORE_VALUES))
    assert not any(f in " ".join(errors) for f in OPTIONAL_FIELDS)


# --- 5. Pasted text prefills recognized fields, leaves the rest None --------


def test_extraction_leaves_unstated_fields_null():
    """One live LLM call — confirms partial extraction never guesses a value for something not stated."""
    features = extract_fraud_features(
        "The company's net profit was 500,000 and the tax gap came out to 50,000."
    )
    dumped = features.model_dump()

    assert dumped["Net_Profit"] == 500000
    assert dumped["Tax_Gap"] == 50000
    # Nothing else was mentioned — must stay None, not a guessed/default value.
    assert dumped["Declared_Tax"] is None
    assert dumped["Industry_Risk"] is None
    assert dumped["Business_Type"] is None


# --- 6. Invalid optional input generates a standard validation error --------


def test_invalid_optional_categorical_value_rejected():
    values = dict(_CORE_VALUES)
    values["Business_Type"] = "Spaceship Manufacturing"  # not a canonical option

    errors = validate_fraud_features(values)

    assert any("Business_Type" in e for e in errors)


def test_invalid_optional_numeric_type_rejected():
    values = dict(_CORE_VALUES)
    values["Annual_Revenue"] = "a lot of money"  # not a number

    errors = validate_fraud_features(values)

    assert any("Annual_Revenue" in e for e in errors)


def test_out_of_range_percentage_rejected_even_though_optional_tier_field():
    values = dict(_CORE_VALUES)
    values["Cash_Transactions_Percentage"] = 150  # out of 0-100 range, and also a required field

    errors = validate_fraud_features(values)

    assert any("Cash_Transactions_Percentage" in e for e in errors)


# --- 7. Zero silent defaults/imputations anywhere in the pipeline ----------


def test_core_model_input_uses_exactly_the_eight_columns_no_more_no_less():
    from app.chat.fraud.engine import CORE_FEATURE_ORDER, _build_feature_row_core

    values = {**_CORE_VALUES, **_OPTIONAL_VALUES}  # includes all 15 optional fields too
    frame = _build_feature_row_core(values)

    assert list(frame.columns) == CORE_FEATURE_ORDER
    assert len(frame.columns) == 8


def test_predict_raises_rather_than_imputes_a_missing_required_field():
    """
    fraud/validation.py is what's supposed to block this before predict() is
    ever called — but predict() itself must never silently default a missing
    value; it should fail loudly (TypeError from float(None)) instead of
    quietly substituting 0/median/mode.
    """
    values = dict(_CORE_VALUES)
    values["Tax_Gap"] = None

    with pytest.raises(TypeError):
        predict(values)


def test_full_model_input_uses_exactly_forty_engineered_columns():
    from app.chat.fraud.engine import _build_feature_row_full

    values = {**_CORE_VALUES, **_OPTIONAL_VALUES}
    frame = _build_feature_row_full(values)

    assert len(frame.columns) == 40


# --- /chat/fraud/extract: merges into the currently-shown form, never overwrites with null ---


@pytest.fixture()
def authed_headers(db, unique_suffix):
    from app.auth.security import create_token
    from app.database.models import User

    username = f"fraudtest_{unique_suffix}"
    response = client.post(
        "/auth/signup",
        json={
            "full_name": "Fraud Extract Test",
            "username": username,
            "email": f"{username}@example.com",
            "password": "testpass123",
            "confirm_password": "testpass123",
        },
    )
    user_id = response.json()["user"]["id"]
    token = create_token(user_id, "authenticated", 60)

    yield {"Authorization": f"Bearer {token}"}

    db.query(User).filter_by(username=username).delete()
    db.commit()


def test_extract_endpoint_merges_new_text_without_erasing_current_fields(authed_headers):
    response = client.post(
        "/chat/fraud/extract",
        headers=authed_headers,
        json={
            "text": "Net profit was 500000 and tax gap is 50000, industry risk medium",
            "current_fields": {"Declared_Tax": 150000},
        },
    )
    assert response.status_code == 200
    body = response.json()

    assert body["fields"]["Declared_Tax"] == 150000  # preserved, not mentioned in the new text
    assert body["fields"]["Net_Profit"] == 500000
    assert body["fields"]["Tax_Gap"] == 50000
    assert body["fields"]["Industry_Risk"] == "Medium"
    # Still missing 4 of the 8 required fields.
    assert len(body["errors"]) == 4


def test_extract_endpoint_new_text_overrides_same_field(authed_headers):
    response = client.post(
        "/chat/fraud/extract",
        headers=authed_headers,
        json={
            "text": "Actually the net profit was 999000.",
            "current_fields": {"Net_Profit": 500000, "Tax_Gap": 50000},
        },
    )
    assert response.status_code == 200
    body = response.json()

    assert body["fields"]["Net_Profit"] == 999000  # overwritten by the new statement
    assert body["fields"]["Tax_Gap"] == 50000  # untouched, not mentioned again
