# Tax Fraud Detection — ML Case Study

Binary classification project to flag fraudulent tax filings (`Fraud` target, ~10.7% positive
class) from ~50,000 taxpayer records. The "codebase" is a sequence of Jupyter notebooks and the
artifacts they write to disk (joblib model/encoder bundles, CSV result tables, PNG figures) —
there is no Python package, build system, or test suite. Each stage reads what the previous stage
wrote, so the notebooks must be run in order; see `CLAUDE.md` for full architecture notes,
conventions, and per-batch rationale.

## Where's the model?

**`best_model/`** — the final, ready-to-use deliverable. Start there if you just need the trained
model, its chosen decision threshold, and its performance numbers. See `best_model/README.md` for
details. Short version:

```python
import joblib
model = joblib.load("best_model/xgboost_fraud_model.joblib")
proba = model.predict_proba(X)[:, 1]        # X = 40-col tree feature matrix
prediction = (proba >= 0.195).astype(int)   # 1 = flagged as fraud
```

**Final model: XGBoost, decision threshold = 0.195** — chosen because the business priority here
is catching fraud (recall) over avoiding false positives (precision), without collapsing precision
entirely. Test set: Precision 0.690, Recall 0.769, F1 0.727, PR-AUC 0.8335, ROC-AUC 0.9469.

## Repo structure

```
data/                    Raw + cleaned dataset, and the fixed train/val/test ID splits
notebooks/                Cleaning.ipynb, EDA.ipynb — data prep and exploratory analysis
Models_Batch_1/            Baseline: 9 models, full feature set, no imbalance handling
Models_Batch_2/            Imbalance handling (resampling) + redundant-feature removal — negative result
Models_Batch_3/            Regularization refinement + threshold tuning (the approach that worked)
Final_Report/               One-time honest test-set evaluation of the finalists + PDF report
best_model/                 Final deliverable: model file, chosen threshold, PDF + confusion matrices
inference/                  Runnable Gradio demo app (inference/test.py) serving both finalist models
results/                   comparison_table.csv — cumulative results across every batch
meta_data/                  Data dictionary for the raw columns
important_indicators_imgs/  Feature-importance figures
CLAUDE.md                   Full architecture/conventions reference (read this for the "why")
```

### The pipeline, in order

```
notebooks/Cleaning.ipynb        → data/tax_fraud_dataset_cleaned.csv
notebooks/EDA.ipynb              → insight only, feeds preprocessing decisions

Models_Batch_1/processing.ipynb → data/splits/{train,val,test}_ids.csv (fixed split, reused forever)
                                 → encoders/scalers, artifacts/batch1_data.joblib
Models_Batch_1/training.ipynb   → 9 baseline models
Models_Batch_1/evaluation.ipynb → baseline results → results/comparison_table.csv

Models_Batch_2/*                → resampling + redundant-feature experiments (did not beat baseline)

Models_Batch_3/processing.ipynb → finalist roster (XGBoost, LightGBM, ...)
Models_Batch_3/training.ipynb   → regularization refinement + out-of-fold threshold tuning
Models_Batch_3/evaluation.ipynb → final recommendation going into the test-set evaluation

Final_Report/test_evaluation.ipynb → the ONLY notebook allowed to touch the test set;
                                      evaluates the finalists once at their chosen thresholds
                                   → Final_Report/Tax_Fraud_Model_Report.pdf

best_model/                        → final XGBoost model + threshold + performance visuals,
                                      packaged from the above for downstream use
```

### Why threshold tuning instead of resampling

Batch 2 tried class weighting, SMOTENC, over/undersampling, and SMOTEENN/SMOTETomek — none beat
the Batch 1 no-sampling baseline on PR-AUC. Batch 3 instead tuned the decision threshold via
out-of-fold predictions on the training set (`cross_val_predict`, never touching validation or
test until a threshold was chosen), which beat every Batch 2 sampling technique by 8–19 precision
points at comparable recall. `best_model/` reflects the outcome of that approach: threshold 0.195,
chosen from a sweep of Fβ scores to sit at the point where recall is clearly ahead of precision
without letting precision collapse (see `best_model/README.md` for the full threshold comparison
table).

## Running things

No `requirements.txt` — install by hand: `pandas numpy scikit-learn xgboost lightgbm catboost
imbalanced-learn statsmodels matplotlib seaborn joblib jupyter` (plus `gradio` for the demo app).

Re-run a notebook headlessly:
```
jupyter nbconvert --to notebook --execute --inplace <path/to/notebook.ipynb>
```

Try the model interactively:
```
python inference/test.py
```
