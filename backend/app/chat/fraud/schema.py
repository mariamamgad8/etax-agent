"""
Fraud model input vocabulary — option lists and field order, shared by the
DB model (app.database.tax_models.FraudRecord), the seed loader
(app.chat.db.seed), the deterministic fraud-intent pre-router
(app.chat.graph), and the prediction engine (fraud/engine.py). There is no
user-facing form/extraction schema anymore — every field's value always
comes from the linked tax.fraud_records row, never typed/pasted by the user.
"""

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

CATEGORICAL_FIELDS = ["Business_Type", "Region", "Industry_Risk"]

ALL_FIELDS = NUMERIC_FIELD_ORDER + CATEGORICAL_FIELDS

FRAUD_THRESHOLD = 0.195
