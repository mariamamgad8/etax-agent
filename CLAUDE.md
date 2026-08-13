# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

A tax fraud detection ML case study. The "codebase" is a sequence of Jupyter notebooks and their
disk artifacts (joblib bundles, CSV result tables, PNG figures) — there is no Python package,
script entry point, build system, linter, or test suite. Progress and decisions are recorded as
markdown cells and result CSVs inside the notebooks themselves, not in separate docs.

## Commands

There is no requirements.txt/environment.yml. Dependencies must be installed by hand; the full set
used across the notebooks is: `pandas numpy scikit-learn xgboost lightgbm catboost imbalanced-learn
statsmodels matplotlib seaborn joblib jupyter`.

Run a notebook headlessly (executes in place, updates outputs/artifacts on disk):
```
jupyter nbconvert --to notebook --execute --inplace <path/to/notebook.ipynb>
```
Notebooks must be executed **in pipeline order** (see Architecture below) since each stage reads
artifacts written by the previous one. Each notebook resolves `PROJECT_ROOT` relative to its own
folder name (works whether cwd is the repo root or the notebook's own directory), so no `cd` is
required — but do not move notebooks between folders without checking that cell.

There is no lint/test command — there is no non-notebook code to lint, and correctness is
validated by inspecting each notebook's own evaluation metrics/plots.

## Architecture: the pipeline

Everything downstream depends on artifacts written by earlier stages; nothing re-fits encoders,
scalers, or the train/val/test split once they exist. Treat this as a strict dependency chain:

```
notebooks/Cleaning.ipynb        → data/tax_fraud_dataset_cleaned.csv (+ .xlsx)
notebooks/EDA.ipynb              → insight only (findings feed Batch 1/2 preprocessing decisions)

Models_Batch_1/processing.ipynb → data/splits/{train,val,test}_ids.csv  (created ONCE, reused forever)
                                 → artifacts/batch1_data.joblib + onehot/ordinal encoders + std/robust scalers
Models_Batch_1/training.ipynb   → artifacts/batch1_results.csv, artifacts/models/
Models_Batch_1/evaluation.ipynb → figures/, appends to results/comparison_table.csv

Models_Batch_2/processing.ipynb → artifacts/batch2_data.joblib (VIF-reduced feature-set variants)
Models_Batch_2/training.ipynb   → artifacts/batch2_results.csv (+ checkpoint CSV, resumable)
Models_Batch_2/evaluation.ipynb → figures/, appends to comparison_table.csv

Models_Batch_3/processing.ipynb → artifacts/batch3_setup.joblib (finalist model roster)
Models_Batch_3/training.ipynb   → batch3_refinement_results.csv, batch3_threshold_results.csv
Models_Batch_3/evaluation.ipynb → figures/, appends to comparison_table.csv, final recommendation

Final_Report/test_evaluation.ipynb → final_test_pr_auc_summary.csv, final_test_threshold_results.csv,
                                      figures/, Tax_Fraud_Model_Report.pdf
```

`notebooks/reviewing_py.ipynb` is a throwaway scratch notebook, not part of the pipeline.

### What each batch is *for* (not just what it does)

- **Batch 1 — Baseline.** All reasonable features, correct encoding, no imbalance handling. Trains
  9 models (LogReg, DecisionTree, RandomForest, XGBoost, LightGBM, CatBoost, SVM, GaussianNB, MLP)
  to establish the reference PR-AUC.
- **Batch 2 — Imbalance + redundancy.** Track A tests resampling (class weights, SMOTENC,
  over/undersampling, SMOTEENN/SMOTETomek) via `imblearn.pipeline.Pipeline` against the Batch 1
  baseline. Track B tests VIF-driven redundant-feature removal. **Neither improved PR-AUC over the
  Batch 1 no-sampling baseline for any model** — this negative result is why Batch 3 pivots to
  threshold tuning instead.
- **Batch 3 — Regularization + threshold tuning.** Narrow hyperparameter re-search around Batch 1's
  winners (small gain), then threshold tuning via `cross_val_predict` **out-of-fold on the training
  set** (never validation), sweeping F1/F2/F0.5-optimal thresholds. Threshold tuning beat every
  Batch 2 sampling technique by 8–19 precision points at comparable recall.
- **Final_Report/test_evaluation.ipynb — the only notebook allowed to touch the test set.**
  Evaluates the two finalists (XGBoost, LightGBM) once, at their Batch-3-chosen thresholds. If you
  add new experiments, evaluate against validation and do not touch `data/splits/test_ids.csv`
  until a final decision is ready to be confirmed — that discipline is deliberate and preserved
  across the whole project.

### Conventions enforced in every notebook

- `RANDOM_STATE = 42`, set once near the top, threaded through the split, all CV splitters, and
  every model's `random_state`.
- `OrdinalEncoder` (not `LabelEncoder`) with an explicit `Low < Medium < High` order for
  `Industry_Risk`, to avoid alphabetical miscoding.
- Encoders/scalers are fit on the train split only, in `Models_Batch_1/processing.ipynb`, then
  reused (never refit) by every later notebook.
- Long-running training cells use a checkpoint-CSV + try/except resume pattern (e.g.
  `batch2_results_checkpoint.csv`, `batch3_threshold_checkpoint.csv`) — expect these files and
  don't delete them mid-run.
- PR-AUC (average precision) is the primary model-selection metric throughout, chosen explicitly
  because ROC-AUC looks misleadingly good under this dataset's class imbalance (~10.7% fraud).

## Data and artifacts

- **Target**: `Fraud` (binary). Strongest predictors: `Tax_Gap`, `Previous_Violations`,
  `Invoice_Mismatch`, `Missing_Documents`, `Cash_Transactions_Percentage`, `Business_Type`/
  `Industry_Risk`. Several raw columns are exact mathematical functions of others (e.g.
  `VAT_Collected` = 14% × `Annual_Revenue`, `Expense_Ratio` + `Profit_Margin` = 1) — this
  redundancy is a recurring theme (drives Batch 2 Track B and the Batch 1 feature-importance
  caveat). Full column definitions are in `meta_data/Data_Dictionary.docx` (not parsed
  programmatically anywhere).
- **`Models_Batch_1/artifacts/batch1_data.joblib`**: the single source every later notebook
  subsets from. Dict with `X_{train,val,test}_{tree,std,rob,cb}` (four parallel feature
  representations: unscaled for tree models, `StandardScaler`, `RobustScaler`, and CatBoost-native
  categorical), `y_{train,val,test}`, `cat_feature_indices`, and column-name metadata.
- **Results CSVs share a common schema** (`Batch, Model, Preprocessing, Feature_Set,
  Sampling_Technique, Best_Parameters, CV_PR_AUC, Validation_PR_AUC, Precision, Recall, F1,
  ROC_AUC, ...`). `results/comparison_table.csv` is the cumulative master table every batch's
  evaluation notebook appends to — check it first for a quick cross-batch comparison instead of
  re-deriving numbers from individual notebooks.
- **Final chosen model**: XGBoost (regularization-refined), threshold = 0.338 (F1-optimal). Test
  PR-AUC 0.8335, ROC-AUC 0.9469, Precision 0.832, Recall 0.685, F1 0.752. LightGBM (threshold
  0.378) is the documented close-second alternative; threshold 0.171 (F2-optimal) is offered if
  recall should be weighted higher than precision.
