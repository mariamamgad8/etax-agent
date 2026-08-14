from typing import Any


class FeatureEngineeringService:

    # =========================================================
    # FEATURES EXPECTED BY THE MODEL
    # =========================================================

    MODEL_FEATURES = [
        "Business_Type",
        "Region",
        "Industry_Risk",

        "Years_in_Business",
        "Employee_Count",

        "Annual_Revenue",
        "Annual_Expenses",
        "Net_Profit",

        "Taxable_Income",
        "Expected_Tax",
        "Declared_Tax",

        "VAT_Collected",
        "VAT_Paid",

        "Previous_Audits",
        "Previous_Violations",
        "Late_Payments",

        "Cash_Transactions_Percentage",

        "Missing_Documents",
        "Invoice_Mismatch",

        "Expense_Ratio",
        "Profit_Margin",
        "Revenue_per_Employee",
        "Tax_Gap",
    ]

    # =========================================================
    # INDUSTRY RISK MAPPING
    # =========================================================

    INDUSTRY_RISK_MAPPING = {
        "Construction": "High",
        "Import/Export": "High",

        "Manufacturing": "Medium",
        "Restaurant": "Medium",
        "Retail": "Medium",

        "Education": "Low",
        "Healthcare": "Low",
        "IT": "Low",
        "Pharmacy": "Low",
    }

    # =========================================================
    # BUILD FEATURES
    # =========================================================

    def build_features(
        self,
        data: dict[str, Any],
    ) -> dict[str, Any]:

        features = dict(data)

        # -----------------------------------------------------
        # Industry Risk
        # -----------------------------------------------------

        business_type = (
            features.get("Business_Type")
        )

        if business_type:

            industry_risk = (
                self.INDUSTRY_RISK_MAPPING.get(
                    business_type
                )
            )

            if industry_risk is not None:

                features["Industry_Risk"] = (
                    industry_risk
                )

        # -----------------------------------------------------
        # Net Profit
        # -----------------------------------------------------

        revenue = features.get(
            "Annual_Revenue"
        )

        expenses = features.get(
            "Annual_Expenses"
        )

        if (
            self._is_number(revenue)
            and self._is_number(expenses)
        ):

            features["Net_Profit"] = (
                revenue - expenses
            )

        # -----------------------------------------------------
        # Expected Tax
        #
        # IMPORTANT:
        # This currently follows the dataset-derived
        # relationship we observed.
        #
        # Keep this isolated so it can be changed easily
        # if the project definition uses another formula.
        # -----------------------------------------------------

        taxable_income = features.get(
            "Taxable_Income"
        )

        if self._is_number(
            taxable_income
        ):

            features["Expected_Tax"] = (
                taxable_income * 0.225
            )

        # -----------------------------------------------------
        # Expense Ratio
        # -----------------------------------------------------

        if (
            self._is_number(revenue)
            and self._is_number(expenses)
            and revenue != 0
        ):

            features["Expense_Ratio"] = (
                expenses / revenue
            )

        # -----------------------------------------------------
        # Profit Margin
        # -----------------------------------------------------

        net_profit = features.get(
            "Net_Profit"
        )

        if (
            self._is_number(net_profit)
            and self._is_number(revenue)
            and revenue != 0
        ):

            features["Profit_Margin"] = (
                net_profit / revenue
            )

        # -----------------------------------------------------
        # Revenue per Employee
        # -----------------------------------------------------

        employee_count = features.get(
            "Employee_Count"
        )

        if (
            self._is_number(revenue)
            and self._is_number(employee_count)
            and employee_count != 0
        ):

            features["Revenue_per_Employee"] = (
                revenue / employee_count
            )

        # -----------------------------------------------------
        # Tax Gap
        # -----------------------------------------------------

        expected_tax = features.get(
            "Expected_Tax"
        )

        declared_tax = features.get(
            "Declared_Tax"
        )

        if (
            self._is_number(expected_tax)
            and self._is_number(declared_tax)
        ):

            features["Tax_Gap"] = (
                expected_tax - declared_tax
            )

        # -----------------------------------------------------
        # Normalize integer columns
        # -----------------------------------------------------

        for field in [
            "Years_in_Business",
            "Employee_Count",
            "Previous_Audits",
            "Previous_Violations",
            "Late_Payments",
            "Missing_Documents",
            "Invoice_Mismatch",
        ]:

            value = features.get(field)

            if (
                isinstance(value, float)
                and value.is_integer()
            ):

                features[field] = int(value)

        return features

    # =========================================================
    # CHECK REQUIRED FEATURES
    # =========================================================

    def get_missing_features(
        self,
        features: dict[str, Any],
    ) -> list[str]:

        return [
            feature
            for feature in self.MODEL_FEATURES
            if features.get(feature) is None
        ]

    # =========================================================
    # CHECK COMPLETENESS
    # =========================================================

    def is_ready_for_model(
        self,
        features: dict[str, Any],
    ) -> bool:

        return (
            len(
                self.get_missing_features(
                    features
                )
            ) == 0
        )

    # =========================================================
    # NUMERIC CHECK
    # =========================================================

    @staticmethod
    def _is_number(
        value: Any,
    ) -> bool:

        return isinstance(
            value,
            (int, float),
        )


# =========================================================
# SINGLETON
# =========================================================

feature_engineering_service = (
    FeatureEngineeringService()
)