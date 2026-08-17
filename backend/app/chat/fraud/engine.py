"""
Loads the trained encoders/model and runs a prediction on an already
Python-validated form. Feature order and categories below were confirmed by
inspecting the live artifacts (categories_, feature_names_in_, booster
feature_names), not assumed from ML_inputs_details.txt alone:

  20 numeric columns (NUMERIC_FIELD_ORDER)
  + Industry_Risk_ord (OrdinalEncoder: Low=0, Medium=1, High=2)
  + 10 Business_Type_* one-hot columns
  + 9 Region_* one-hot columns
  = 40 features, in that exact order.

The LLM never sees this module — extraction/validation only ever produce
the raw 23-field form; this is where those become the model's real input.
"""
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
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


def _build_feature_row(values: dict) -> pd.DataFrame:
    onehot, ordinal, _ = _load()

    numeric = {field: float(values[field]) for field in NUMERIC_FIELD_ORDER}

    ordinal_df = pd.DataFrame({"Industry_Risk": [values["Industry_Risk"]]})
    industry_risk_ord = ordinal.transform(ordinal_df)[0, 0]

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


def predict(values: dict) -> tuple[str, float]:
    """
    `values` must already be Python-validated (see fraud/validation.py) —
    all 23 fields present, correct types. Returns (label, probability) where
    probability is the model's score for the positive ("suspicious") class.
    """
    _, _, model = _load()
    frame = _build_feature_row(values)
    probability = float(model.predict_proba(frame)[0, 1])
    label = "Suspicious" if probability >= FRAUD_THRESHOLD else "Not suspicious"
    return label, probability
