"""
Gradio inference app for the tax fraud detection models.

Loads the two Batch 3 finalists (XGBoost, LightGBM — see
Models_Batch_3/artifacts/models/*_final.joblib) plus the Batch 1 encoders,
and serves a form where you can either type in a taxpayer's values by hand
or pick a Taxpayer_ID from the dataset to auto-fill the form. Each model's
decision threshold defaults to its own F1-optimal value from
Final_Report/test_evaluation.ipynb but is adjustable via a slider.

Run with:
    python inference/test.py
"""

from pathlib import Path

import gradio as gr
import joblib
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = PROJECT_ROOT / "data" / "tax_fraud_dataset_cleaned.csv"
BATCH1_ARTIFACTS = PROJECT_ROOT / "Models_Batch_1" / "artifacts"
BATCH3_MODELS = PROJECT_ROOT / "Models_Batch_3" / "artifacts" / "models"

# ---------------------------------------------------------------------------
# Fitted preprocessing objects + final models (already trained; see
# Models_Batch_1/processing.ipynb and Final_Report/test_evaluation.ipynb)
# ---------------------------------------------------------------------------
onehot_encoder = joblib.load(BATCH1_ARTIFACTS / "onehot_encoder.joblib")
ordinal_encoder = joblib.load(BATCH1_ARTIFACTS / "ordinal_encoder.joblib")

MODELS = {
    "XGBoost": joblib.load(BATCH3_MODELS / "XGBoost_final.joblib"),
    "LightGBM": joblib.load(BATCH3_MODELS / "LightGBM_final.joblib"),
}

# F1-optimal thresholds chosen via out-of-fold CV in Models_Batch_3/training.ipynb,
# confirmed on the held-out test set in Final_Report/test_evaluation.ipynb.
DEFAULT_THRESHOLDS = {"XGBoost": 0.195, "LightGBM": 0.378}

ONEHOT_COLS = ["Business_Type", "Region"]
ORDINAL_COL = "Industry_Risk"
ORDINAL_ORDER = ["Low", "Medium", "High"]
# Exact order Models_Batch_1/processing.ipynb built (and the models were
# trained on) — must not be reordered.
NUMERIC_COLS = [
    "Years_in_Business", "Employee_Count", "Annual_Revenue", "Annual_Expenses",
    "Net_Profit", "Taxable_Income", "Expected_Tax", "Declared_Tax",
    "VAT_Collected", "VAT_Paid", "Previous_Audits", "Previous_Violations",
    "Late_Payments", "Cash_Transactions_Percentage", "Missing_Documents",
    "Invoice_Mismatch", "Expense_Ratio", "Profit_Margin",
    "Revenue_per_Employee", "Tax_Gap",
]
# Integer-valued columns, used only to pick the Gradio widget precision below.
INT_COLS = [
    "Years_in_Business", "Employee_Count", "Previous_Audits",
    "Previous_Violations", "Late_Payments", "Missing_Documents",
    "Invoice_Mismatch",
]
FLOAT_COLS = [c for c in NUMERIC_COLS if c not in INT_COLS]

# Same column order Models_Batch_1/processing.ipynb's encode_unscaled() builds:
# numeric columns, then the ordinal column, then the one-hot expansion.
ONEHOT_FEATURE_NAMES = list(onehot_encoder.get_feature_names_out(ONEHOT_COLS))
TREE_FEATURE_NAMES = NUMERIC_COLS + [f"{ORDINAL_COL}_ord"] + ONEHOT_FEATURE_NAMES
RAW_INPUT_COLS = NUMERIC_COLS + ONEHOT_COLS + [ORDINAL_COL]

# ---------------------------------------------------------------------------
# Dataset, for the "load by Taxpayer_ID" convenience feature
# ---------------------------------------------------------------------------
df = pd.read_csv(DATA_PATH).set_index("Taxpayer_ID", drop=False)
MIN_TAXPAYER_ID, MAX_TAXPAYER_ID = int(df.index.min()), int(df.index.max())

BUSINESS_TYPES = sorted(df["Business_Type"].unique().tolist())
REGIONS = sorted(df["Region"].unique().tolist())

DEFAULTS = df[RAW_INPUT_COLS].median(numeric_only=True).to_dict()
DEFAULTS["Business_Type"] = df["Business_Type"].mode()[0]
DEFAULTS["Region"] = df["Region"].mode()[0]
DEFAULTS["Industry_Risk"] = df["Industry_Risk"].mode()[0]


def encode_row(raw: dict) -> pd.DataFrame:
    """Replicate Models_Batch_1/processing.ipynb's encode_unscaled() for one row."""
    row_df = pd.DataFrame([raw])

    onehot_part = pd.DataFrame(
        onehot_encoder.transform(row_df[ONEHOT_COLS]),
        columns=ONEHOT_FEATURE_NAMES,
    )
    ordinal_part = pd.DataFrame(
        ordinal_encoder.transform(row_df[[ORDINAL_COL]]),
        columns=[f"{ORDINAL_COL}_ord"],
    )
    numeric_part = row_df[NUMERIC_COLS].reset_index(drop=True)

    encoded = pd.concat([numeric_part, ordinal_part, onehot_part], axis=1)
    return encoded[TREE_FEATURE_NAMES]


def predict(threshold_xgb, threshold_lgb, *values):
    raw = dict(zip(RAW_INPUT_COLS, values))
    raw["Invoice_Mismatch"] = int(raw["Invoice_Mismatch"])
    X = encode_row(raw)

    outputs = []
    for name, threshold in [("XGBoost", threshold_xgb), ("LightGBM", threshold_lgb)]:
        proba = float(MODELS[name].predict_proba(X)[0, 1])
        verdict = "FRAUD" if proba >= threshold else "NOT FRAUD"
        outputs.append(
            f"### {name}: {verdict}\nFraud probability: **{proba:.1%}** "
            f"(threshold {threshold:.3f})"
        )
        outputs.append({"Fraud": proba, "Not Fraud": 1 - proba})
    return outputs


def load_taxpayer(taxpayer_id):
    if taxpayer_id is None or int(taxpayer_id) not in df.index:
        return [gr.update()] * len(RAW_INPUT_COLS) + [
            f"No taxpayer with ID {taxpayer_id} in the dataset."
        ]

    row = df.loc[int(taxpayer_id)]
    updates = []
    for col in RAW_INPUT_COLS:
        if col in INT_COLS:
            updates.append(gr.update(value=int(row[col])))
        elif col in FLOAT_COLS:
            updates.append(gr.update(value=float(row[col])))
        else:
            updates.append(gr.update(value=str(row[col])))

    actual = "FRAUD" if row["Fraud"] == 1 else "NOT FRAUD"
    ground_truth = f"**Actual label for Taxpayer {taxpayer_id} (from dataset): {actual}**"
    return updates + [ground_truth]


with gr.Blocks(title="Tax Fraud Detection") as demo:
    gr.Markdown(
        "# Tax Fraud Detection\n"
        "Enter a taxpayer's data by hand, or load one from the dataset by "
        "Taxpayer_ID, then run it through both final models "
        "(XGBoost and LightGBM). Each model's threshold defaults to its own "
        "F1-optimal value from the project's test evaluation and can be "
        "adjusted."
    )

    with gr.Row():
        taxpayer_id_input = gr.Number(
            label=f"Taxpayer_ID ({MIN_TAXPAYER_ID}-{MAX_TAXPAYER_ID})",
            precision=0,
        )
        load_btn = gr.Button("Load Taxpayer")
    ground_truth_box = gr.Markdown("")

    gr.Markdown("### Inputs")
    components = {}
    with gr.Row():
        components["Business_Type"] = gr.Dropdown(
            BUSINESS_TYPES, value=DEFAULTS["Business_Type"], label="Business_Type"
        )
        components["Region"] = gr.Dropdown(
            REGIONS, value=DEFAULTS["Region"], label="Region"
        )
        components["Industry_Risk"] = gr.Dropdown(
            ORDINAL_ORDER, value=DEFAULTS["Industry_Risk"], label="Industry_Risk"
        )

    with gr.Row():
        for col in INT_COLS:
            components[col] = gr.Number(
                label=col, value=int(DEFAULTS[col]), precision=0
            )

    with gr.Row():
        for col in FLOAT_COLS:
            components[col] = gr.Number(label=col, value=float(DEFAULTS[col]))

    inputs_list = [components[c] for c in RAW_INPUT_COLS]

    gr.Markdown("### Decision thresholds")
    with gr.Row():
        with gr.Column():
            threshold_xgb = gr.Slider(
                0.0, 1.0, value=DEFAULT_THRESHOLDS["XGBoost"], step=0.001,
                label="XGBoost threshold",
            )
            reset_xgb_btn = gr.Button("Reset to optimal (0.195)", size="sm")
        with gr.Column():
            threshold_lgb = gr.Slider(
                0.0, 1.0, value=DEFAULT_THRESHOLDS["LightGBM"], step=0.001,
                label="LightGBM threshold",
            )
            reset_lgb_btn = gr.Button("Reset to optimal (0.378)", size="sm")

    predict_btn = gr.Button("Predict", variant="primary")

    with gr.Row():
        with gr.Column():
            xgb_verdict = gr.Markdown()
            xgb_label = gr.Label(label="XGBoost probability")
        with gr.Column():
            lgb_verdict = gr.Markdown()
            lgb_label = gr.Label(label="LightGBM probability")

    load_btn.click(
        load_taxpayer,
        inputs=[taxpayer_id_input],
        outputs=inputs_list + [ground_truth_box],
    )
    predict_btn.click(
        predict,
        inputs=[threshold_xgb, threshold_lgb] + inputs_list,
        outputs=[xgb_verdict, xgb_label, lgb_verdict, lgb_label],
    )
    reset_xgb_btn.click(
        lambda: DEFAULT_THRESHOLDS["XGBoost"], outputs=threshold_xgb
    )
    reset_lgb_btn.click(
        lambda: DEFAULT_THRESHOLDS["LightGBM"], outputs=threshold_lgb
    )

if __name__ == "__main__":
    demo.launch()
