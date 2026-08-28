"""
Loads the trained encoders/model and runs a prediction on a fraud.fraud_records
row fetched from the database — every one of the 23 fields is always present
(it's a complete dataset row, never a partial user-typed form), so this only
ever runs the full 40-feature XGBoost model. Feature order and categories
below were confirmed by inspecting the live artifacts (categories_,
feature_names_in_, booster feature_names), not assumed from
ML_inputs_details.txt alone.
"""
from pathlib import Path

import joblib
import pandas as pd

from app.chat.fraud.schema import FRAUD_THRESHOLD, NUMERIC_FIELD_ORDER

_MODELS_DIR = Path(__file__).resolve().parent / "models"

_onehot = None
_ordinal = None
_model = None


def _load():
    global _onehot, _ordinal, _model
    if _model is None:
        _onehot = joblib.load(_MODELS_DIR / "onehot_encoder.joblib")
        _ordinal = joblib.load(_MODELS_DIR / "ordinal_encoder.joblib")
        _model = joblib.load(_MODELS_DIR / "xgboost_fraud_model.joblib")
    return _onehot, _ordinal, _model


def _industry_risk_ord(ordinal, industry_risk: str) -> float:
    ordinal_df = pd.DataFrame({"Industry_Risk": [industry_risk]})
    return ordinal.transform(ordinal_df)[0, 0]


def _build_feature_row(values: dict) -> pd.DataFrame:
    onehot, ordinal, _ = _load()

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


def predict(values: dict) -> dict:
    """
    `values` is a fraud.fraud_records row (dict) — all 23 fields present.
    Returns {"probability", "is_high_risk"}. `probability` is the model's raw
    score on a 0.00-1.00 scale; `is_high_risk` is probability >= FRAUD_THRESHOLD.
    The "Suspicious"/"Not suspicious" wording this used to return is gone —
    callers report the percentage directly (see responses.build_fraud_result_text).
    """
    _, _, model = _load()
    frame = _build_feature_row(values)
    probability = float(model.predict_proba(frame)[0, 1])

    return {
        "probability": probability,
        "is_high_risk": probability >= FRAUD_THRESHOLD,
    }
