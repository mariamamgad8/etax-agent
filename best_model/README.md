# Best Model — Tax Fraud Detection

Final production artifact from the tax fraud detection project. Model: **XGBoost**
(regularization-refined, Batch 3), selected over LightGBM and the other Batch 1 finalists
on PR-AUC/ROC-AUC and threshold behavior. Full pipeline history and methodology are in
`../CLAUDE.md`; honest one-time test-set numbers come from `../Final_Report/test_evaluation.ipynb`.

## Contents

| File | Description |
|---|---|
| `xgboost_fraud_model.joblib` | The trained XGBoost model (copy of `Models_Batch_3/artifacts/models/XGBoost_final.joblib`). Expects the 40-column tree feature matrix built by `Models_Batch_1/processing.ipynb` (see `inference/test.py` for the exact encoding). |
| `threshold_sweet_spot_summary.pdf` | Table of test-set Precision/Recall/F1/ROC-AUC/PR-AUC across every tuned threshold (F0.5 → F2), with the chosen operating point highlighted. |
| `confusion_matrix_whole_data_thr_0.231.png` | Confusion matrix on the full dataset (train+val+test, n=50,000) at threshold 0.231. |
| `confusion_matrix_whole_data_thr_0.195.png` | Confusion matrix on the full dataset (train+val+test, n=50,000) at threshold 0.195 — the chosen threshold. |
| `confusion_matrix_test_data_thr_0.231.png` | Confusion matrix on the held-out test set only (n=7,500) at threshold 0.231. |
| `confusion_matrix_test_data_thr_0.195.png` | Confusion matrix on the held-out test set only (n=7,500) at threshold 0.195 — the chosen threshold. |

Note: the "whole data" confusion matrices include the 35,000 training rows the model was fit
on, so their precision/recall read slightly more optimistic than the honest test-only numbers.
The test-only matrices are the ones that reflect real-world generalization.

## Chosen operating point: threshold = 0.195 (F1.75-optimal)

The business priority for this model is **catching fraud (recall) over avoiding false
positives (precision)**, but without collapsing precision the way the most recall-heavy
threshold (F2) would. Threshold 0.195 was chosen as the sweet spot between the two, found by
sweeping Fβ scores (β = 1.0 → 2.0) on out-of-fold training predictions, confirmed on
validation, and evaluated exactly once on the held-out test set.

Threshold 0.231 (F1.5-optimal) is included alongside it for comparison — it sits almost
exactly at the precision/recall crossover point, whereas 0.195 clearly favors recall.

| Threshold | Precision | Recall | F1 | Note |
|---|---|---|---|---|
| 0.231 (F1.5) | 0.739 | 0.746 | 0.743 | Precision ≈ Recall (crossover) |
| **0.195 (F1.75)** | **0.690** | **0.769** | **0.727** | **Chosen — recall clearly ahead of precision** |

Test-set PR-AUC: 0.8335 · Test-set ROC-AUC: 0.9469 (both threshold-independent).

## Usage

```python
import joblib

model = joblib.load("xgboost_fraud_model.joblib")
proba = model.predict_proba(X)[:, 1]        # X = 40-col tree feature matrix
prediction = (proba >= 0.195).astype(int)   # 1 = flagged as fraud
```

See `../inference/test.py` for a full working example, including the exact raw-column-to-feature
encoding (one-hot + ordinal) required before calling `predict_proba`.
