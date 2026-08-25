"""
Fraud model input schema — mirrors ML_inputs_details.txt exactly (option
lists, threshold, integer-only columns) and the actual encoders/model
(feature order, categories) loaded from backend/app/chat/fraud/models/.
"""
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict

REGION_OPTIONS = [
    "Sharqia",
    "Giza",
    "Alex",
    "Cairo",
    "Dakahlia",
    "Monufia",
    "Sohag",
    "Assiut",
    "Unknown",
]
BUSINESS_TYPE_OPTIONS = [
    "Construction",
    "Restaurant",
    "Education",
    "IT",
    "Pharmacy",
    "Import/Export",
    "Retail",
    "Manufacturing",
    "Healthcare",
    "Unknown",
]
INDUSTRY_RISK_OPTIONS = ["Low", "Medium", "High"]

# Named RegionValue (not Region) — a type alias with the same name as the
# field it annotates below caused Pydantic to resolve the annotation against
# the field itself instead of this alias, forcing every value to null.
RegionValue = Literal[
    "Sharqia", "Giza", "Alex", "Cairo", "Dakahlia", "Monufia", "Sohag", "Assiut", "Unknown"
]
BusinessType = Literal[
    "Construction", "Restaurant", "Education", "IT", "Pharmacy",
    "Import/Export", "Retail", "Manufacturing", "Healthcare", "Unknown",
]
IndustryRisk = Literal["Low", "Medium", "High"]

# Integer-valued columns — validated as whole, non-negative counts.
INT_FIELDS = [
    "Years_in_Business",
    "Employee_Count",
    "Previous_Audits",
    "Previous_Violations",
    "Late_Payments",
    "Missing_Documents",
    "Invoice_Mismatch",
]

# Remaining numeric columns — validated as plain numbers (signed allowed,
# e.g. Net_Profit or Tax_Gap can legitimately be negative).
FLOAT_FIELDS = [
    "Annual_Revenue",
    "Annual_Expenses",
    "Net_Profit",
    "Taxable_Income",
    "Expected_Tax",
    "Declared_Tax",
    "VAT_Collected",
    "VAT_Paid",
    "Cash_Transactions_Percentage",
    "Expense_Ratio",
    "Profit_Margin",
    "Revenue_per_Employee",
    "Tax_Gap",
]

CATEGORICAL_FIELDS = ["Business_Type", "Region", "Industry_Risk"]

# Exact order the trained XGBoost model expects its 20 raw numeric inputs in
# (before the encoders expand Business_Type/Region/Industry_Risk into the
# model's real 40 engineered columns — see fraud/engine.py).
NUMERIC_FIELD_ORDER = [
    "Years_in_Business", "Employee_Count", "Annual_Revenue", "Annual_Expenses",
    "Net_Profit", "Taxable_Income", "Expected_Tax", "Declared_Tax",
    "VAT_Collected", "VAT_Paid", "Previous_Audits", "Previous_Violations",
    "Late_Payments", "Cash_Transactions_Percentage", "Missing_Documents",
    "Invoice_Mismatch", "Expense_Ratio", "Profit_Margin",
    "Revenue_per_Employee", "Tax_Gap",
]

ALL_FIELDS = NUMERIC_FIELD_ORDER + CATEGORICAL_FIELDS

# The 8 raw fields backend/app/chat/fraud/models/xgboost_8features.joblib
# needs — read directly from ml_artifacts/xgboost_8features_columns.txt
# (its 8th entry, Industry_Risk_ord, is the ordinal-encoded form of the raw
# Industry_Risk field below; see fraud/engine.py's CORE_FEATURE_ORDER for the
# post-encoding order the model itself expects). A benchmark on the real
# training data found this dedicated 8-feature model (PR-AUC 0.8305) actually
# outperforms the 23-feature model with the missing 15 imputed by
# median/mode (PR-AUC 0.8259) — so a partial form is never padded with
# defaults; it runs this model on exactly these 8 fields instead. Only when
# literally all 23 fields are present does the full model run.
CORE_REQUIRED_FIELDS = [
    "Net_Profit",
    "Taxable_Income",
    "Declared_Tax",
    "Previous_Violations",
    "Cash_Transactions_Percentage",
    "Invoice_Mismatch",
    "Tax_Gap",
    "Industry_Risk",
]

OPTIONAL_FIELDS = [f for f in ALL_FIELDS if f not in CORE_REQUIRED_FIELDS]

FRAUD_THRESHOLD = 0.195


class FraudFeatures(BaseModel):
    """
    Every field is optional because this is an EXTRACTION result, not a
    validated/complete form — the LLM must leave anything the user didn't
    mention as null rather than guess a value. Only the 8 fields in
    CORE_REQUIRED_FIELDS are actually required before a prediction can run;
    see fraud/validation.py.
    """

    model_config = ConfigDict(extra="forbid")

    Business_Type: Optional[BusinessType] = None
    Region: Optional[RegionValue] = None
    Industry_Risk: Optional[IndustryRisk] = None

    Years_in_Business: Optional[float] = None
    Employee_Count: Optional[float] = None
    Annual_Revenue: Optional[float] = None
    Annual_Expenses: Optional[float] = None
    Net_Profit: Optional[float] = None
    Taxable_Income: Optional[float] = None
    Expected_Tax: Optional[float] = None
    Declared_Tax: Optional[float] = None
    VAT_Collected: Optional[float] = None
    VAT_Paid: Optional[float] = None
    Previous_Audits: Optional[float] = None
    Previous_Violations: Optional[float] = None
    Late_Payments: Optional[float] = None
    Cash_Transactions_Percentage: Optional[float] = None
    Missing_Documents: Optional[float] = None
    Invoice_Mismatch: Optional[float] = None
    Expense_Ratio: Optional[float] = None
    Profit_Margin: Optional[float] = None
    Revenue_per_Employee: Optional[float] = None
    Tax_Gap: Optional[float] = None
