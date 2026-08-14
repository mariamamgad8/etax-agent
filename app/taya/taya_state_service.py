from copy import deepcopy
from typing import Any


class TayaStateService:

    # =========================================================
    # USER-PROVIDED FEATURES
    # =========================================================

    USER_FIELDS = [
        "Business_Type",
        "Region",
        "Years_in_Business",
        "Employee_Count",
        "Annual_Revenue",
        "Annual_Expenses",
        "Taxable_Income",
        "Declared_Tax",
        "VAT_Collected",
        "VAT_Paid",
        "Previous_Audits",
        "Previous_Violations",
        "Late_Payments",
        "Cash_Transactions_Percentage",
        "Missing_Documents",
        "Invoice_Mismatch",
    ]

    # =========================================================
    # SYSTEM-DERIVED FEATURES
    # =========================================================

    DERIVED_FIELDS = [
        "Industry_Risk",
        "Net_Profit",
        "Expected_Tax",
        "Expense_Ratio",
        "Profit_Margin",
        "Revenue_per_Employee",
        "Tax_Gap",
    ]

    # =========================================================
    # INTEGER FEATURES
    # =========================================================

    INT_FIELDS = [
        "Years_in_Business",
        "Employee_Count",
        "Previous_Audits",
        "Previous_Violations",
        "Late_Payments",
        "Missing_Documents",
        "Invoice_Mismatch",
    ]

    # =========================================================
    # PERCENTAGE FEATURES
    # =========================================================

    PERCENTAGE_FIELDS = [
        "Cash_Transactions_Percentage",
    ]

    def __init__(self):

        self.sessions: dict[
            str,
            dict[str, Any]
        ] = {}

    # =========================================================
    # CREATE EMPTY STATE
    # =========================================================

    def _create_empty_state(self) -> dict[str, Any]:

        data = {}

        for field in self.USER_FIELDS:
            data[field] = None

        for field in self.DERIVED_FIELDS:
            data[field] = None

        return {
            "data": data,
            "unknown_fields": [],
            "ambiguous_fields": [],
            "completed": False,
        }

    # =========================================================
    # GET SESSION
    # =========================================================

    def get_state(
        self,
        session_id: str,
    ) -> dict[str, Any]:

        if session_id not in self.sessions:

            self.sessions[session_id] = (
                self._create_empty_state()
            )

        return self.sessions[session_id]

    # =========================================================
    # UPDATE SESSION
    # =========================================================

    def update(
        self,
        session_id: str,
        extracted_data: dict[str, Any],
    ) -> dict[str, Any]:

        state = self.get_state(session_id)

        data = state["data"]

        for field, value in extracted_data.items():

            # -------------------------------------------------
            # Ignore unknown fields
            # -------------------------------------------------

            if field not in data:
                continue

            # -------------------------------------------------
            # Do not overwrite existing data with None
            # -------------------------------------------------

            if value is None:
                continue

            # -------------------------------------------------
            # Normalize value
            # -------------------------------------------------

            value = self._normalize_value(
                field,
                value,
            )

            # -------------------------------------------------
            # Validate value
            # -------------------------------------------------

            if not self._is_valid(
                field,
                value,
            ):
                continue

            data[field] = value

            # -------------------------------------------------
            # Remove from unknown / ambiguous
            # -------------------------------------------------

            if field in state["unknown_fields"]:

                state["unknown_fields"].remove(
                    field
                )

            if field in state["ambiguous_fields"]:

                state["ambiguous_fields"].remove(
                    field
                )

        state["completed"] = (
            len(
                self.get_missing_fields(
                    session_id
                )
            ) == 0
        )

        return state

    # =========================================================
    # MARK FIELD AS UNKNOWN
    # =========================================================

    def mark_unknown(
        self,
        session_id: str,
        field: str,
    ):

        state = self.get_state(session_id)

        if field not in self.USER_FIELDS:
            return

        if field not in state["unknown_fields"]:

            state["unknown_fields"].append(
                field
            )

    # =========================================================
    # MARK FIELD AS AMBIGUOUS
    # =========================================================

    def mark_ambiguous(
        self,
        session_id: str,
        field: str,
    ):

        state = self.get_state(session_id)

        if field not in self.USER_FIELDS:
            return

        if field not in state["ambiguous_fields"]:

            state["ambiguous_fields"].append(
                field
            )

    # =========================================================
    # GET MISSING USER FIELDS
    # =========================================================

    def get_missing_fields(
        self,
        session_id: str,
    ) -> list[str]:

        state = self.get_state(session_id)

        data = state["data"]

        return [
            field
            for field in self.USER_FIELDS
            if data.get(field) is None
        ]

    # =========================================================
    # GET NEXT QUESTION FIELD
    # =========================================================

    def get_next_missing_field(
        self,
        session_id: str,
    ) -> str | None:

        missing = self.get_missing_fields(
            session_id
        )

        if not missing:
            return None

        return missing[0]

    # =========================================================
    # CHECK COMPLETION
    # =========================================================

    def is_complete(
        self,
        session_id: str,
    ) -> bool:

        return (
            len(
                self.get_missing_fields(
                    session_id
                )
            ) == 0
        )

    # =========================================================
    # GET USER DATA ONLY
    # =========================================================

    def get_user_data(
        self,
        session_id: str,
    ) -> dict[str, Any]:

        state = self.get_state(session_id)

        return {
            field: state["data"].get(field)
            for field in self.USER_FIELDS
        }

    # =========================================================
    # GET ALL DATA
    # =========================================================

    def get_all_data(
        self,
        session_id: str,
    ) -> dict[str, Any]:

        state = self.get_state(session_id)

        return deepcopy(
            state["data"]
        )

    # =========================================================
    # SET DERIVED FIELD
    # =========================================================

    def set_derived_field(
        self,
        session_id: str,
        field: str,
        value: Any,
    ):

        if field not in self.DERIVED_FIELDS:
            raise ValueError(
                f"'{field}' is not a derived field."
            )

        state = self.get_state(session_id)

        state["data"][field] = value

    # =========================================================
    # SET MULTIPLE DERIVED FIELDS
    # =========================================================

    def set_derived_fields(
        self,
        session_id: str,
        derived_data: dict[str, Any],
    ):

        for field, value in derived_data.items():

            self.set_derived_field(
                session_id=session_id,
                field=field,
                value=value,
            )

    # =========================================================
    # RESET SESSION
    # =========================================================

    def reset(
        self,
        session_id: str,
    ):

        self.sessions[session_id] = (
            self._create_empty_state()
        )

    # =========================================================
    # DELETE SESSION
    # =========================================================

    def delete(
        self,
        session_id: str,
    ):

        self.sessions.pop(
            session_id,
            None,
        )

    # =========================================================
    # NORMALIZATION
    # =========================================================

    def _normalize_value(
        self,
        field: str,
        value: Any,
    ) -> Any:

        # -----------------------------------------------------
        # Integer fields
        # -----------------------------------------------------

        if field in self.INT_FIELDS:

            if isinstance(value, float):

                if value.is_integer():

                    return int(value)

                return value

            if isinstance(value, str):

                try:

                    number = float(
                        value.replace(",", "")
                    )

                    if number.is_integer():

                        return int(number)

                except ValueError:
                    pass

        # -----------------------------------------------------
        # Percentage
        # -----------------------------------------------------

        if field in self.PERCENTAGE_FIELDS:

            if isinstance(value, str):

                cleaned = (
                    value
                    .replace("%", "")
                    .replace(",", "")
                    .strip()
                )

                try:
                    return float(cleaned)

                except ValueError:
                    return value

        # -----------------------------------------------------
        # Numeric fields
        # -----------------------------------------------------

        numeric_fields = {
            "Annual_Revenue",
            "Annual_Expenses",
            "Taxable_Income",
            "Declared_Tax",
            "VAT_Collected",
            "VAT_Paid",
        }

        if field in numeric_fields:

            if isinstance(value, str):

                cleaned = (
                    value
                    .replace(",", "")
                    .strip()
                )

                try:
                    return float(cleaned)

                except ValueError:
                    return value

        return value

    # =========================================================
    # VALIDATION
    # =========================================================

    def _is_valid(
        self,
        field: str,
        value: Any,
    ) -> bool:

        # -----------------------------------------------------
        # Integer fields
        # -----------------------------------------------------

        if field in self.INT_FIELDS:

            if not isinstance(value, int):
                return False

            if value < 0:
                return False

        # -----------------------------------------------------
        # Percentage
        # -----------------------------------------------------

        if field in self.PERCENTAGE_FIELDS:

            if not isinstance(
                value,
                (int, float)
            ):
                return False

            if value < 0 or value > 100:
                return False

        # -----------------------------------------------------
        # Financial values
        # -----------------------------------------------------

        financial_fields = {
            "Annual_Revenue",
            "Annual_Expenses",
            "Taxable_Income",
            "Declared_Tax",
            "VAT_Collected",
            "VAT_Paid",
        }

        if field in financial_fields:

            if not isinstance(
                value,
                (int, float)
            ):
                return False

            if value < 0:
                return False

        return True


# =========================================================
# SINGLETON
# =========================================================

taya_state_service = TayaStateService()