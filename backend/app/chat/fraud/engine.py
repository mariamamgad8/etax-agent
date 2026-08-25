"""
Loads the trained encoders/models and runs a prediction on an already
Python-validated form. Feature order and categories below were confirmed by
inspecting the live artifacts (categories_, feature_names_in_, booster
feature_names), not assumed from ML_inputs_details.txt alone.

Two trained models, chosen by exactly how many of the 23 fields are present
— never by imputing the gap:
  - xgboost_fraud_model.joblib (the "full" model): 20 numeric columns
    (NUMERIC_FIELD_ORDER) + Industry_Risk_ord (OrdinalEncoder: Low=0,
    Medium=1, High=2) + 10 Business_Type_* one-hot + 9 Region_* one-hot
    = 40 features, in that exact order. Only runs when literally all 23
    fields are present.
  - xgboost_8features.joblib (the "core" model): CORE_FEATURE_ORDER below,
    confirmed live via the loaded model's own feature_names_in_ against
    ml_artifacts/xgboost_8features_columns.txt. Runs whenever anything less
    than all 23 fields is present (but always at least the 8 required —
    fraud/validation.py blocks prediction otherwise). A benchmark on the
    real training data found this dedicated model (PR-AUC 0.8305) actually
    beats the full model with the other 15 columns imputed by median/mode
    (PR-AUC 0.8259), so a partial form is never padded with defaults.

The LLM never sees this module — extraction/validation only ever produce
the raw 23-field form; this is where those become a model's real input.
"""
from pathlib import Path

import joblib
import pandas as pd

from app.chat.fraud.schema import ALL_FIELDS, CORE_REQUIRED_FIELDS, FRAUD_THRESHOLD, NUMERIC_FIELD_ORDER

_MODELS_DIR = Path(__file__).resolve().parent / "models"

# Exact order xgboost_8features.joblib expects its 8 inputs in — confirmed
# live via the loaded model's feature_names_in_, matching
# ml_artifacts/xgboost_8features_columns.txt exactly.
CORE_FEATURE_ORDER = [
    "Net_Profit",
    "Taxable_Income",
    "Declared_Tax",
    "Previous_Violations",
    "Cash_Transactions_Percentage",
    "Invoice_Mismatch",
    "Tax_Gap",
    "Industry_Risk_ord",
]

STANDARD_TIER = "Standard Assessment"
COMPREHENSIVE_TIER = "Comprehensive Assessment"

_onehot = None
_ordinal = None
_model_full = None
_model_core = None


def _load():
    global _onehot, _ordinal, _model_full, _model_core
    if _model_full is None:
        _onehot = joblib.load(_MODELS_DIR / "onehot_encoder.joblib")
        _ordinal = joblib.load(_MODELS_DIR / "ordinal_encoder.joblib")
        _model_full = joblib.load(_MODELS_DIR / "xgboost_fraud_model.joblib")
        _model_core = joblib.load(_MODELS_DIR / "xgboost_8features.joblib")
    return _onehot, _ordinal, _model_full, _model_core


def _industry_risk_ord(ordinal, industry_risk: str) -> float:
    ordinal_df = pd.DataFrame({"Industry_Risk": [industry_risk]})
    return ordinal.transform(ordinal_df)[0, 0]


def _build_feature_row_full(values: dict) -> pd.DataFrame:
    onehot, ordinal, _, _ = _load()

    numeric = {field: float(values[field]) for field in NUMERIC_FIELD_ORDER}
    industry_risk_ord = _industry_risk_ord(ordinal, values["Industry_Risk"])

    onehot_df = pd.DataFrame(
        {"Business_Type": [values["Business_Type"]], "Region": [values["Region"]]}
    )
    onehot_encoded = onehot.transform(onehot_df)
    if hasattr(onehot_encoded, "toarray"):
        onehot_encoded = onehot_encoded.toarray()
    onehot_columns = onehot.get_feature_names_out(["Business_Type", "Region"])

    row = {**numeric, "Industry_Risk_ord": industry_risk_ord}
    row.update(dict(zip(onehot_columns, onehot_encoded[0])))

    feature_order = [*NUMERIC_FIELD_ORDER, "Industry_Risk_ord", *onehot_columns]
    return pd.DataFrame([row], columns=feature_order)


def _build_feature_row_core(values: dict) -> pd.DataFrame:
    _, ordinal, _, _ = _load()
    industry_risk_ord = _industry_risk_ord(ordinal, values["Industry_Risk"])

    row = {field: float(values[field]) for field in CORE_REQUIRED_FIELDS if field != "Industry_Risk"}
    row["Industry_Risk_ord"] = industry_risk_ord
    return pd.DataFrame([row], columns=CORE_FEATURE_ORDER)


def predict(values: dict) -> dict:
    """
    `values` must already be Python-validated (see fraud/validation.py) — at
    minimum the 8 CORE_REQUIRED_FIELDS are present with correct types.
    Model selection is exact field count, never a partial/imputed run of the
    full model: all 23 present -> the full model; anything less (but never
    less than the required 8) -> the core model, using only its 8 inputs —
    any extra fields the user filled in are simply not passed to it (they
    stay in confirmed_features/state, not discarded, just unused for this
    prediction).

    Returns {"label", "probability", "tier", "fields_provided", "fields_total"}.
    `tier` is "Standard Assessment" (core model) or "Comprehensive Assessment"
    (full model) — the two-model distinction itself is never surfaced beyond
    this tier label.
    """
    fields_provided = sum(1 for f in ALL_FIELDS if values.get(f) not in (None, ""))
    fields_total = len(ALL_FIELDS)

    _, _, model_full, model_core = _load()

    if fields_provided == fields_total:
        frame = _build_feature_row_full(values)
        probability = float(model_full.predict_proba(frame)[0, 1])
        tier = COMPREHENSIVE_TIER
    else:
        frame = _build_feature_row_core(values)
        probability = float(model_core.predict_proba(frame)[0, 1])
        tier = STANDARD_TIER

    label = "Suspicious" if probability >= FRAUD_THRESHOLD else "Not suspicious"
    return {
        "label": label,
        "probability": probability,
        "tier": tier,
        "fields_provided": fields_provided,
        "fields_total": fields_total,
    }
