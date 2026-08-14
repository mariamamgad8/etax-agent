import json
import re
from pathlib import Path
from typing import Any

from app.services.llm_service import llm_service
from app.taya.taya_state_service import (
    taya_state_service,
)
from app.taya.conversation_controller import (
    conversation_controller,
    ConversationState,
)


class TayaService:

    # =========================================================
    # PATHS
    # =========================================================

    BASE_DIR = Path(__file__).resolve().parent

    SYSTEM_PROMPT_PATH = (
        BASE_DIR
        / "prompts"
        / "taya_system_prompt.txt"
    )

    EXTRACTION_PROMPT_PATH = (
        BASE_DIR
        / "prompts"
        / "taya_extraction_prompt.txt"
    )

    SCHEMA_PATH = (
        BASE_DIR
        / "schemas"
        / "taya_feature_schema.json"
    )

    # =========================================================
    # INITIALIZATION
    # =========================================================

    def __init__(self):

        self._conversations: dict[str, dict[str, Any]] = {}

        self.system_prompt = (
            self._load_text(
                self.SYSTEM_PROMPT_PATH
            )
        )

        self.extraction_prompt = (
            self._load_text(
                self.EXTRACTION_PROMPT_PATH
            )
        )

        self.feature_schema = (
            self._load_json(
                self.SCHEMA_PATH
            )
        )

    # =========================================================
    # FILE HELPERS
    # =========================================================

    @staticmethod
    def _load_text(
        path: Path,
    ) -> str:

        if not path.exists():

            raise FileNotFoundError(
                f"Taya prompt not found: {path}"
            )

        return path.read_text(
            encoding="utf-8"
        )

    @staticmethod
    def _load_json(
        path: Path,
    ) -> dict[str, Any]:

        if not path.exists():

            raise FileNotFoundError(
                f"Taya schema not found: {path}"
            )

        with open(
            path,
            "r",
            encoding="utf-8",
        ) as file:

            return json.load(file)

    # =========================================================
    # PROCESS USER MESSAGE
    # =========================================================

    async def process_message(
        self,
        session_id: str,
        user_message: str,
    ) -> dict[str, Any]:

        user_message = (user_message or "").strip()

        conversation = self._get_conversation(
            session_id
        )

        # -----------------------------------------------------
        # LANGUAGE / GREETING GATE
        #
        # Do this BEFORE calling the LLM. This saves latency and
        # prevents "hello" from being treated as an ML feature.
        # -----------------------------------------------------

        language = conversation.get("language")

        if language is None:

            selected_language = (
                conversation_controller
                .detect_language_choice(
                    user_message
                )
            )

            if selected_language:

                conversation_controller.apply_language(
                    conversation,
                    selected_language,
                )

                language = selected_language

                state = taya_state_service.get_state(
                    session_id
                )

                # Synchronize the controller before extraction.
                first_feature = (
                    conversation_controller.get_next_missing_feature(
                        state.get("data", {})
                    )
                )

                if first_feature is not None:
                    conversation["current_question"] = first_feature

                # -------------------------------------------------
                # IMPORTANT:
                # The user may select the language AND provide
                # business information in the SAME message.
                #
                # Example:
                # "عربي، ضريبة القيمة المضافة اللي جمعتها 150 ألف..."
                #
                # Do not throw away everything after "عربي".
                # Extract the whole message, then continue from the
                # next missing feature.
                # -------------------------------------------------

                extraction_state = dict(state)
                extraction_state["session_id"] = session_id

                extracted = await self._extract_information(
                    user_message=user_message,
                    current_state=extraction_state,
                )

                extracted_data = extracted.get(
                    "extracted",
                    {},
                )

                self._apply_extraction(
                    session_id,
                    extracted,
                )

                updated_state = (
                    taya_state_service.get_state(
                        session_id
                    )
                )

                # Recalculate the next missing feature after the
                # language-selection message has been extracted.
                next_feature = (
                    conversation_controller
                    .get_next_missing_feature(
                        updated_state.get(
                            "data",
                            {},
                        )
                    )
                )

                if next_feature is not None:
                    conversation["current_question"] = (
                        next_feature
                    )
                else:
                    conversation["current_question"] = None

                confirmation = (
                    "تمام 👌 هنكمل بالعربي."
                    if language == "ar"
                    else "Great! We'll continue in English."
                )

                # If the user only said "عربي", extracted_data will
                # be empty and we simply ask the first missing field.
                if next_feature is not None:

                    question = (
                        conversation_controller.get_question(
                            next_feature,
                            language,
                        )
                    )

                    response = (
                        confirmation
                        + " "
                        + question
                    )

                else:

                    response = confirmation

                return self._build_result(
                    session_id,
                    response,
                    extracted_data,
                )

            if conversation_controller.looks_like_greeting(
                user_message
            ):

                response = (
                    "أهلاً بيك 👋 أنا Taya، مساعدك الذكي. "
                    "تحب نكمل بالعربي ولا English؟"
                )

                return self._build_result(
                    session_id,
                    response,
                    {},
                )

            # If the user starts immediately with business
            # information, we DO extract it, then ask for language.
            state = taya_state_service.get_state(
                session_id
            )

            extracted = await self._extract_information(
                user_message=user_message,
                current_state=state,
            )

            extracted_data = extracted.get(
                "extracted",
                {},
            )

            self._apply_extraction(
                session_id,
                extracted,
            )

            if extracted_data:

                response = (
                    "تمام، سجلت المعلومات اللي قلتها. "
                    "قبل ما نكمل، تحب نتكلم بالعربي ولا English؟"
                )

            else:

                response = (
                    "تحب نكمل بالعربي ولا English؟"
                )

            return self._build_result(
                session_id,
                response,
                extracted_data,
            )

        # -----------------------------------------------------
        # DATA COLLECTION
        # -----------------------------------------------------

        # Greeting during collection does not require an LLM call.
        if conversation_controller.looks_like_greeting(
            user_message
        ):

            state = taya_state_service.get_state(
                session_id
            )

            action = (
                conversation_controller.next_action(
                    conversation,
                    state.get("data", {}),
                )
            )

            prefix = (
                "أهلاً بيك 👋 "
                if language == "ar"
                else "Hi 👋 "
            )

            response = (
                prefix + (action["text"] or "")
            )

            return self._build_result(
                session_id,
                response,
                {},
            )

        # -----------------------------------------------------
        # Extract the actual user answer.
        # -----------------------------------------------------

        state = taya_state_service.get_state(
            session_id
        )

        # Always synchronize the controller with the actual first
        # missing feature before extraction. This prevents stale
        # current_question values (for example Annual_Revenue) from
        # causing a short answer like "900 ألف" to be assigned to the
        # wrong field.
        controller_data = state.get(
            "data",
            {},
        )

        current_feature = (
            conversation_controller
            .get_next_missing_feature(
                controller_data
            )
        )

        if current_feature is not None:
            conversation["current_question"] = (
                current_feature
            )

        extraction_state = dict(state)
        extraction_state["session_id"] = session_id

        extracted = await self._extract_information(
            user_message=user_message,
            current_state=extraction_state,
        )

        extracted_data = extracted.get(
            "extracted",
            {},
        )

        self._apply_extraction(
            session_id,
            extracted,
        )

        updated_state = taya_state_service.get_state(
            session_id
        )

        complete = taya_state_service.is_complete(
            session_id
        )

        # The current question must always represent the next missing
        # model feature. Never let it remain stuck on Business_Type
        # after the user has already supplied another feature.
        next_feature = (
            conversation_controller.get_next_missing_feature(
                updated_state.get("data", {})
            )
        )

        if next_feature is not None:
            conversation["current_question"] = next_feature

        else:
            conversation["current_question"] = None

        if complete:

            conversation["state"] = (
                ConversationState.COMPLETE.value
            )

            return self._build_result(
                session_id,
                self._complete_response(language),
                extracted_data,
            )

        # -----------------------------------------------------
        # A valid answer was extracted.
        # Move to the next canonical question.
        # -----------------------------------------------------

        if extracted_data:

            conversation_controller.reset_retry(
                conversation
            )

            action = (
                conversation_controller.next_action(
                    conversation,
                    updated_state.get(
                        "data",
                        {},
                    ),
                    extraction_confident=True,
                    has_extracted_data=True,
                )
            )

            response = action["text"] or ""

            return self._build_result(
                session_id,
                response,
                extracted_data,
            )

        # -----------------------------------------------------
        # Explicit "I don't know".
        # -----------------------------------------------------

        if conversation_controller.looks_like_unknown(
            user_message
        ):

            feature = conversation.get(
                "current_question"
            )

            if feature:

                if language == "ar":
                    response = (
                        "تمام، مفيش مشكلة. لو عندك تقدير تقريبي "
                        "ممكن تقولهولي. "
                        + conversation_controller.get_question(
                            feature,
                            language,
                            retry=True,
                        )
                    )
                else:
                    response = (
                        "No problem. If you have an approximate "
                        "value, you can provide it. "
                        + conversation_controller.get_question(
                            feature,
                            language,
                            retry=True,
                        )
                    )

            else:

                action = (
                    conversation_controller.next_action(
                        conversation,
                        updated_state.get(
                            "data",
                            {},
                        ),
                    )
                )

                response = action["text"] or ""

            return self._build_result(
                session_id,
                response,
                {},
            )

        # -----------------------------------------------------
        # No confident extraction: retry the same canonical
        # question. Never invent a value.
        # -----------------------------------------------------

        feature = conversation.get(
            "current_question"
        )

        if feature is None:

            feature = (
                conversation_controller
                .get_next_missing_feature(
                    updated_state.get(
                        "data",
                        {},
                    )
                )
            )

            conversation["current_question"] = feature

        if feature:

            if conversation_controller.register_retry(
                conversation
            ):

                response = (
                    conversation_controller.get_question(
                        feature,
                        language,
                        retry=True,
                    )
                )

            else:

                conversation_controller.reset_retry(
                    conversation
                )

                response = (
                    conversation_controller.get_question(
                        feature,
                        language,
                    )
                )

        else:

            response = self._complete_response(
                language
            )

        return self._build_result(
            session_id,
            response,
            {},
        )

    # =========================================================
    # EXTRACTION -> STATE
    # =========================================================

    def _apply_extraction(
        self,
        session_id: str,
        extracted: dict[str, Any],
    ) -> None:

        extracted_data = extracted.get(
            "extracted",
            {},
        )

        if extracted_data:
            taya_state_service.update(
                session_id=session_id,
                extracted_data=extracted_data,
            )

        for field in extracted.get(
            "unknown_fields",
            [],
        ):
            taya_state_service.mark_unknown(
                session_id=session_id,
                field=field,
            )

        for field in extracted.get(
            "ambiguous_fields",
            [],
        ):
            taya_state_service.mark_ambiguous(
                session_id=session_id,
                field=field,
            )

    # =========================================================
    # CONTROLLER HELPERS
    # =========================================================

    def _get_conversation(
        self,
        session_id: str,
    ) -> dict[str, Any]:

        conversation = self._conversations.get(
            session_id
        )

        if conversation is None:
            conversation = (
                conversation_controller
                .create_conversation()
            )
            self._conversations[
                session_id
            ] = conversation

        return conversation

    def _build_result(
        self,
        session_id: str,
        response: str,
        extracted_data: dict[str, Any],
    ) -> dict[str, Any]:

        state = taya_state_service.get_state(
            session_id
        )

        return {
            "response": response.strip(),
            "extracted": extracted_data,
            "state": state,
            "missing_fields": (
                taya_state_service.get_missing_fields(
                    session_id
                )
            ),
            "complete": taya_state_service.is_complete(
                session_id
            ),
        }

    @staticmethod
    def _complete_response(
        language: str,
    ) -> str:

        if language == "en":
            return (
                "Great! I've collected all the required "
                "information. We're ready to run the assessment."
            )

        return (
            "تمام جدًا 👌 جمعت كل المعلومات المطلوبة. "
            "دلوقتي البيانات جاهزة للتقييم."
        )

    # =========================================================
    # INFORMATION EXTRACTION
    # =========================================================

    async def _extract_information(
        self,
        user_message: str,
        current_state: dict[str, Any],
    ) -> dict[str, Any]:

        current_data = current_state.get("data", {})

        user_fields = self.feature_schema.get("user_fields", {})
        field_names = list(user_fields.keys())

        # The controller tells the extractor what Taya is currently
        # asking about. This is especially important for voice:
        # "900 ألف" should become Annual_Expenses when that is the
        # current question, even though the user did not repeat
        # the word "expenses".
        conversation = self._conversations.get(
            current_state.get("session_id"),
            {},
        )

        current_question = (
            conversation.get("current_question")
            if conversation
            else None
        )

        extraction_instructions = f"""
You are Taya's STRUCTURED DATA EXTRACTION engine.

IMPORTANT:
- You are NOT the conversational assistant.
- Do NOT greet the user.
- Do NOT acknowledge the user.
- Do NOT explain anything.
- Do NOT ask questions.
- Do NOT answer the user's message.
- Your ONLY job is to extract explicit information from the user's message.
- Return JSON ONLY.
- Never invent a value.
- Never infer a value that is not explicitly stated.
- If the user did not provide a field, do not add it to "extracted".
- If the user says they do not know a value, add that field to "unknown_fields".
- If the value is genuinely unclear, add that field to "ambiguous_fields".

USER-OWNED FIELDS:
{json.dumps(field_names, ensure_ascii=False, indent=2)}

CURRENT STATE:
{json.dumps(current_data, ensure_ascii=False, indent=2)}

CURRENT QUESTION / EXPECTED FIELD:
{current_question}

IMPORTANT CURRENT-QUESTION RULE:
- If CURRENT QUESTION / EXPECTED FIELD is not null, interpret a
  concise answer in the context of that field.
- Example: if the expected field is Annual_Expenses and the user says
  "900 ألف" or "حوالي 900 ألف", extract Annual_Expenses = 900000.
- Example: if the expected field is Employee_Count and the user says
  "15", extract Employee_Count = 15.
- Example: if the expected field is Cash_Transactions_Percentage and
  the user says "حوالي 60%" extract 60.
- Never use the current question to invent a value. The user's message
  must still contain an answer/value.
- If the user asks a question instead of answering, do not extract it
  as the expected field.

OUTPUT MUST HAVE EXACTLY THIS TOP-LEVEL STRUCTURE:
{{
  "extracted": {{}},
  "unknown_fields": [],
  "ambiguous_fields": [],
  "notes": []
}}

RULES:
1. "extracted" contains only newly stated or explicitly corrected values.
2. Keep the exact feature names from USER-OWNED FIELDS.
3. Convert unambiguous spoken numbers to numeric values.
4. Do not calculate derived fields.
5. Do not extract Industry_Risk, Net_Profit, Expected_Tax, Expense_Ratio,
   Profit_Margin, Revenue_per_Employee, or Tax_Gap.
6. If the user says "no" to a count-type history field, use 0.
7. If the user says "yes" without a count, do not invent the count.
8. Return ONLY valid JSON. No markdown fences. No prose.
"""

        history = [
            {"role": "system", "content": extraction_instructions},
            {"role": "user", "content": user_message},
        ]

        raw_response = await llm_service.generate_response(history)

        parsed = self._parse_json_response(raw_response)

        if parsed.get("_parse_failed") is True:
            retry_history = [
                {"role": "system", "content": extraction_instructions},
                {
                    "role": "user",
                    "content": f"""
The previous output was invalid JSON.

Previous output:
{raw_response}

Extract the information again from this user message:

{user_message}

Return ONLY valid JSON using the exact required structure.
""",
                },
            ]

            retry_response = await llm_service.generate_response(
                retry_history
            )

            parsed = self._parse_json_response(retry_response)

        # ---------------------------------------------------------
        # Deterministic extraction runs AFTER the LLM retry so
        # explicit high-confidence facts are never lost.
        # ---------------------------------------------------------
        deterministic = (
            self._extract_answer_for_current_question(
                user_message=user_message,
                current_question=current_question,
            )
        )

        # Also preserve the existing conservative phrase-based
        # extractor for multi-field answers.
        explicit_facts = (
            self._extract_explicit_facts(
                user_message
            )
        )

        if explicit_facts:
            deterministic.update(explicit_facts)

        # For a short numeric voice answer, the current question is
        # authoritative. The LLM sometimes sees "900 ألف" and may
        # incorrectly attach it to a previous financial field. If the
        # deterministic context-aware extractor has a value, keep only
        # that current-field value.
        short_context_answer = (
            current_question is not None
            and self._is_short_numeric_answer(
                user_message
            )
        )

        if (
            short_context_answer
            and deterministic
            and current_question in deterministic
        ):
            parsed["extracted"] = {
                current_question: deterministic[
                    current_question
                ]
            }
            parsed["unknown_fields"] = [
                field
                for field in parsed.get(
                    "unknown_fields",
                    [],
                )
                if field != current_question
            ]
            parsed["ambiguous_fields"] = [
                field
                for field in parsed.get(
                    "ambiguous_fields",
                    [],
                )
                if field != current_question
            ]

        if deterministic:

            parsed.setdefault(
                "extracted",
                {},
            )

            if not isinstance(
                parsed["extracted"],
                dict,
            ):
                parsed["extracted"] = {}

            for field, value in deterministic.items():
                parsed["extracted"][field] = value

            parsed["unknown_fields"] = [
                field
                for field in parsed.get(
                    "unknown_fields",
                    [],
                )
                if field not in deterministic
            ]

            parsed["ambiguous_fields"] = [
                field
                for field in parsed.get(
                    "ambiguous_fields",
                    [],
                )
                if field not in deterministic
            ]

        # Final safety net for compact answers: if the current
        # question was clear and we deterministically extracted its
        # value, never keep an LLM-assigned value for another field.
        if (
            short_context_answer
            and deterministic
            and current_question in deterministic
        ):
            parsed["extracted"] = {
                current_question: deterministic[
                    current_question
                ]
            }

        parsed.pop("_parse_failed", None)

        extracted_data = parsed.get("extracted", {})

        if not isinstance(extracted_data, dict):
            extracted_data = {}

        parsed["extracted"] = {
            field: value
            for field, value in extracted_data.items()
            if field in user_fields and value is not None
        }

        # ---------------------------------------------------------
        # CRITICAL SAFETY RULE:
        #
        # The LLM receives CURRENT STATE as context, so it may echo
        # old values as if they were extracted from the new message.
        #
        # Example:
        #   Current question = VAT_Collected
        #   User says = "200 ألف"
        #
        # The LLM must NOT return old fields such as:
        #   Annual_Revenue
        #   Annual_Expenses
        #   Previous_Audits
        #   etc.
        #
        # Only accept:
        #   1) fields explicitly detected in the NEW message by our
        #      deterministic extractor, and
        #   2) the current question when its answer was confidently
        #      extracted.
        #
        # This prevents previous state from leaking into the new
        # extraction result.
        # ---------------------------------------------------------
        allowed_new_fields = set(
            deterministic.keys()
        )

        if current_question in deterministic:
            allowed_new_fields.add(
                current_question
            )

        parsed["extracted"] = {
            field: value
            for field, value in parsed["extracted"].items()
            if field in allowed_new_fields
        }

        parsed["unknown_fields"] = [
            field
            for field in parsed.get("unknown_fields", [])
            if field in user_fields
        ]

        parsed["ambiguous_fields"] = [
            field
            for field in parsed.get("ambiguous_fields", [])
            if field in user_fields
        ]

        return parsed

    @staticmethod
    def _is_short_numeric_answer(
        user_message: str,
    ) -> bool:
        """
        Detect compact voice answers such as:
            "900 ألف"
            "2 مليون"
            "15"
            "60%"
            "حوالي 900 ألف"

        This is deliberately conservative and is only used to prevent
        an LLM from assigning a short answer to the wrong feature.
        """

        text = (
            user_message
            .strip()
            .lower()
            .translate(
                str.maketrans(
                    "٠١٢٣٤٥٦٧٨٩",
                    "0123456789",
                )
            )
        )

        # Remove common conversational prefixes.
        text = re.sub(
            r"^(حوالي|تقريبًا|تقريبا|approximately|about|around)\s*",
            "",
            text,
        )

        return bool(
            re.fullmatch(
                r"\d+(?:[.,]\d+)?\s*"
                r"(?:مليون|million|ألف|الف|thousand|k|%|percent|في المية|بالمية)?",
                text,
            )
        )

    @staticmethod
    def _extract_answer_for_current_question(
        user_message: str,
        current_question: str | None,
    ) -> dict[str, Any]:
        """
        Conservative context-aware extraction for short voice answers.

        Examples:
            current_question = Annual_Expenses
            user = "900 ألف"
            -> {"Annual_Expenses": 900000}

            current_question = Employee_Count
            user = "15"
            -> {"Employee_Count": 15}

        We only apply this to the field Taya is currently asking for.
        """

        if not current_question:
            return {}

        text = user_message.strip().lower()

        if not text:
            return {}

        # Normalize Arabic-Indic digits once and use this normalized
        # value throughout the whole current-question extractor.
        digit_translation = str.maketrans(
            "٠١٢٣٤٥٦٧٨٩",
            "0123456789",
        )

        normalized = text.translate(
            digit_translation
        )

        # Do not interpret obvious non-answer conversational messages
        # as numeric values.
        non_answers = (
            "اهلا",
            "أهلا",
            "hello",
            "hi",
            "hey",
            "مش عارف",
            "معرفش",
            "لا اعرف",
            "لا أعرف",
            "مش متأكد",
            "i don't know",
            "i dont know",
            "not sure",
        )

        if any(
            phrase == text
            or text.startswith(phrase + " ")
            for phrase in non_answers
        ):
            return {}

        # Business type / region can also be short answers.
        if current_question == "Business_Type":
            mapping = {
                "مطعم": "Restaurant",
                "restaurant": "Restaurant",
                "مطاعم": "Restaurant",
                "retail": "Retail",
                "تجزئة": "Retail",
                "manufacturing": "Manufacturing",
                "تصنيع": "Manufacturing",
                "construction": "Construction",
                "مقاولات": "Construction",
                "pharmacy": "Pharmacy",
                "صيدلية": "Pharmacy",
                "healthcare": "Healthcare",
                "رعاية صحية": "Healthcare",
                "education": "Education",
                "تعليم": "Education",
                "it": "IT",
                "technology": "IT",
                "تكنولوجيا": "IT",
            }

            for phrase, value in mapping.items():
                if re.search(
                    rf"(?<!\w){re.escape(phrase)}(?!\w)",
                    text,
                ):
                    return {
                        "Business_Type": value
                    }

            return {}

        if current_question == "Region":
            mapping = {
                # Cairo
                "القاهرة": "Cairo",
                "القاهره": "Cairo",
                "cairo": "Cairo",

                # Giza
                "الجيزة": "Giza",
                "الجيزه": "Giza",
                "جيزة": "Giza",
                "جيزه": "Giza",
                "giza": "Giza",

                # Alexandria
                "الإسكندرية": "Alexandria",
                "الاسكندرية": "Alexandria",
                "الإسكندريه": "Alexandria",
                "الاسكندريه": "Alexandria",
                "اسكندرية": "Alexandria",
                "اسكندريه": "Alexandria",
                "alexandria": "Alexandria",
                "alex": "Alexandria",

                # Qalyubia
                "القليوبية": "Qalyubia",
                "القليوبيه": "Qalyubia",
                "قليوبية": "Qalyubia",
                "قليوبيه": "Qalyubia",
                "qalyubia": "Qalyubia",
                "qalyoubia": "Qalyubia",

                # Port Said
                "بورسعيد": "Port Said",
                "بور سعيد": "Port Said",
                "بورسعيده": "Port Said",
                "port said": "Port Said",
                "portsaid": "Port Said",

                # Suez
                "السويس": "Suez",
                "سويس": "Suez",
                "suez": "Suez",

                # Damietta
                "دمياط": "Damietta",
                "دمياطة": "Damietta",
                "دمياطه": "Damietta",
                "damietta": "Damietta",

                # Dakahlia
                "الدقهلية": "Dakahlia",
                "الدقهليه": "Dakahlia",
                "دقهلية": "Dakahlia",
                "دقهليه": "Dakahlia",
                "dakahlia": "Dakahlia",

                # Sharqia
                "الشرقية": "Sharqia",
                "الشرقيه": "Sharqia",
                "شرقية": "Sharqia",
                "شرقيه": "Sharqia",
                "sharqia": "Sharqia",
                "sharkia": "Sharqia",

                # Kafr El Sheikh
                "كفر الشيخ": "Kafr El Sheikh",
                "كفرالشيخ": "Kafr El Sheikh",
                "كفرشيخ": "Kafr El Sheikh",
                "قفر الشيخ": "Kafr El Sheikh",
                "قفرالشيخ": "Kafr El Sheikh",
                "كفر الشيخة": "Kafr El Sheikh",
                "kafr el sheikh": "Kafr El Sheikh",
                "kafr-el-sheikh": "Kafr El Sheikh",
                "kafrelsheikh": "Kafr El Sheikh",

                # Gharbia
                "الغربية": "Gharbia",
                "الغربيه": "Gharbia",
                "غربية": "Gharbia",
                "غربيه": "Gharbia",
                "gharbia": "Gharbia",
                "gharbeya": "Gharbia",

                # Monufia
                "المنوفية": "Monufia",
                "المنوفيه": "Monufia",
                "منوفية": "Monufia",
                "منوفيه": "Monufia",
                "monufia": "Monufia",
                "menoufia": "Monufia",

                # Matrouh
                "مطروح": "Matrouh",
                "مرسى مطروح": "Matrouh",
                "مرسى مطروح": "Matrouh",
                "matrouh": "Matrouh",
                "marsa matrouh": "Matrouh",

                # Beheira
                "مطروح": "Matrouh",
            "مرسى مطروح": "Matrouh",
            "matrouh": "Matrouh",
            "marsa matrouh": "Matrouh",

            "البحيرة": "Beheira",
                "البحيره": "Beheira",
                "بحيرة": "Beheira",
                "بحيره": "Beheira",
                "beheira": "Beheira",
                "behira": "Beheira",

                # Ismailia
                "الإسماعيلية": "Ismailia",
                "الاسماعيلية": "Ismailia",
                "الإسماعيليه": "Ismailia",
                "الاسماعيليه": "Ismailia",
                "اسماعيلية": "Ismailia",
                "اسماعيليه": "Ismailia",
                "ismailia": "Ismailia",

                # Fayoum
                "الفيوم": "Fayoum",
                "فيوم": "Fayoum",
                "fayoum": "Fayoum",
                "faiyum": "Fayoum",
                "fayum": "Fayoum",

                # Beni Suef
                "بني سويف": "Beni Suef",
                "بنى سويف": "Beni Suef",
                "بني سويف": "Beni Suef",
                "بني سويف": "Beni Suef",
                "بني سويف": "Beni Suef",
                "beni suef": "Beni Suef",
                "benisuef": "Beni Suef",

                # Minya
                "المنيا": "Minya",
                "منيا": "Minya",
                "minya": "Minya",
                "minia": "Minya",
                "menia": "Minya",

                # Assiut
                "أسيوط": "Assiut",
                "اسيوط": "Assiut",
                "اسيـوط": "Assiut",
                "assiut": "Assiut",
                "asyut": "Assiut",
                "assuit": "Assiut",

                # Sohag
                "سوهاج": "Sohag",
                "suhag": "Sohag",
                "sohag": "Sohag",
                "sohaj": "Sohag",

                # Qena
                "قنا": "Qena",
                "قناه": "Qena",
                "qena": "Qena",
                "qina": "Qena",

                # Luxor
                "الأقصر": "Luxor",
                "الاقصر": "Luxor",
                "أقصر": "Luxor",
                "اقصر": "Luxor",
                "luxor": "Luxor",

                # Aswan
                "أسوان": "Aswan",
                "اسوان": "Aswan",
                "aswan": "Aswan",

                # Red Sea
                "البحر الأحمر": "Red Sea",
                "البحر الاحمر": "Red Sea",
                "بحر الأحمر": "Red Sea",
                "بحر الاحمر": "Red Sea",
                "red sea": "Red Sea",
                "redsea": "Red Sea",

                # New Valley
                "الوادي الجديد": "New Valley",
                "الوادي الجديده": "New Valley",
                "وادي الجديد": "New Valley",
                "وادى الجديد": "New Valley",
                "new valley": "New Valley",
                "newvalley": "New Valley",

                # North Sinai
                "شمال سيناء": "North Sinai",
                "شمال سينا": "North Sinai",
                "شمال سينا": "North Sinai",
                "north sinai": "North Sinai",
                "northsina": "North Sinai",

                # South Sinai
                "جنوب سيناء": "South Sinai",
                "جنوب سينا": "South Sinai",
                "south sinai": "South Sinai",
                "southsina": "South Sinai",
            }

            for phrase, value in mapping.items():
                if phrase in text:
                    return {
                        "Region": value
                    }

            return {}

        # ---------------------------------------------------------
        # Semantic phrases in the user's answer have priority over
        # a bare number. This is important when the user answers
        # with a complete phrase such as:
        # "ضريبة القيمة المضافة اللي جمعتها 150 ألف".
        # ---------------------------------------------------------
        semantic = (
            TayaService._extract_explicit_facts(
                user_message
            )
        )

        if current_question in semantic:
            return {
                current_question: semantic[
                    current_question
                ]
            }

        # Continuation answers are common in natural speech:
        #   "واللي دفعتها 100 ألف"
        #   "واللي أعلنتها 200 ألف"
        # When the controller already knows which field is expected,
        # the field context is sufficient to interpret the number.
        continuation_match = re.search(
            r"(?:(?:واللي|والتى|والتي|و)?\s*"
            r"(?:دفعتها|دفعته|دفعت|اللي دفعته|"
            r"جمعتها|جمعته|أعلنتها|صرحت بها|"
            r"معلنة|المعلنة))"
            r".*?"
            r"(\d+(?:[.,]\d+)?)\s*"
            r"(مليون|million|ألف|الف|thousand|k)?",
            normalized,
        )

        if continuation_match and current_question in {
            "VAT_Collected",
            "VAT_Paid",
            "Declared_Tax",
        }:
            number = continuation_match.group(1)
            unit = continuation_match.group(2) or ""

            value = float(
                number.replace(",", "")
            )

            if unit.lower() in {
                "مليون",
                "million",
            }:
                value *= 1_000_000
            elif unit.lower() in {
                "ألف",
                "الف",
                "thousand",
                "k",
            }:
                value *= 1_000

            return {
                current_question: value
            }

        # Count/percentage/money fields.
        numeric_fields = {
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
        }

        if current_question not in numeric_fields:
            return {}

        # Support:
        # 900000
        # 900,000
        # 900.000
        # 900 ألف
        # 2 مليون
        # 60%
        match = re.search(
            r"(?<!\d)(\d+(?:[.,]\d+)?)\s*"
            r"(مليون|million|ألف|الف|thousand|k|%|percent|في المية|بالمية)?",
            normalized,
        )

        if not match:
            return {}

        raw_number = match.group(1)
        unit = (
            match.group(2)
            or ""
        ).lower()

        # Avoid treating decimal separators as thousands separators
        # when there is no explicit unit.
        try:
            if unit in {
                "مليون",
                "million",
            }:
                value = float(
                    raw_number.replace(",", ".")
                ) * 1_000_000

            elif unit in {
                "ألف",
                "الف",
                "thousand",
                "k",
            }:
                value = float(
                    raw_number.replace(",", ".")
                ) * 1_000

            elif unit in {
                "%",
                "percent",
                "في المية",
                "بالمية",
            }:
                value = float(
                    raw_number.replace(",", ".")
                )

            else:
                # For integer/count answers, commas are usually
                # thousands separators.
                if (
                    current_question
                    in {
                        "Employee_Count",
                        "Years_in_Business",
                        "Previous_Audits",
                        "Previous_Violations",
                        "Late_Payments",
                        "Missing_Documents",
                        "Invoice_Mismatch",
                    }
                ):
                    value = float(
                        raw_number.replace(",", "")
                    )
                else:
                    value = float(
                        raw_number.replace(",", "")
                    )

        except ValueError:
            return {}

        if current_question in {
            "Employee_Count",
            "Years_in_Business",
            "Previous_Audits",
            "Previous_Violations",
            "Late_Payments",
            "Missing_Documents",
            "Invoice_Mismatch",
        }:
            if not float(value).is_integer():
                return {}
            value = int(value)

        return {
            current_question: value
        }

    @staticmethod
    def _extract_explicit_facts(
        user_message: str,
    ) -> dict[str, Any]:
        """
        Extract high-confidence, explicitly stated facts without
        depending on the LLM returning JSON.

        This is intentionally conservative: it only handles values
        that are stated with recognizable phrases. The LLM remains
        responsible for more complex/ambiguous language.
        """

        text = user_message.strip()
        normalized = text.lower()

        extracted: dict[str, Any] = {}

        # ---------------------------------------------------------
        # Business Type
        # ---------------------------------------------------------
        business_types = {
            "مطعم": "Restaurant",
            "مطاعم": "Restaurant",
            "restaurant": "Restaurant",
            "retail": "Retail",
            "تجزئة": "Retail",
            "manufacturing": "Manufacturing",
            "تصنيع": "Manufacturing",
            "construction": "Construction",
            "مقاولات": "Construction",
            "pharmacy": "Pharmacy",
            "صيدلية": "Pharmacy",
            "healthcare": "Healthcare",
            "رعاية صحية": "Healthcare",
            "education": "Education",
            "تعليم": "Education",
            "it": "IT",
            "تكنولوجيا": "IT",
            "technology": "IT",
            "import/export": "Import/Export",
            "استيراد وتصدير": "Import/Export",
        }

        for phrase, value in business_types.items():
            if phrase in normalized:
                extracted["Business_Type"] = value
                break

        # ---------------------------------------------------------
        # Region
        # ---------------------------------------------------------
        regions = {
            "القاهرة": "Cairo",
            "القاهره": "Cairo",
            "cairo": "Cairo",

            "الجيزة": "Giza",
            "الجيزه": "Giza",
            "جيزة": "Giza",
            "جيزه": "Giza",
            "giza": "Giza",

            "الإسكندرية": "Alexandria",
            "الاسكندرية": "Alexandria",
            "الإسكندريه": "Alexandria",
            "الاسكندريه": "Alexandria",
            "اسكندرية": "Alexandria",
            "اسكندريه": "Alexandria",
            "alexandria": "Alexandria",
            "alex": "Alexandria",

            "القليوبية": "Qalyubia",
            "القليوبيه": "Qalyubia",
            "قليوبية": "Qalyubia",
            "قليوبيه": "Qalyubia",
            "qalyubia": "Qalyubia",
            "qalyoubia": "Qalyubia",

            "بورسعيد": "Port Said",
            "بور سعيد": "Port Said",
            "port said": "Port Said",
            "portsaid": "Port Said",

            "السويس": "Suez",
            "سويس": "Suez",
            "suez": "Suez",

            "دمياط": "Damietta",
            "دمياطة": "Damietta",
            "damietta": "Damietta",

            "الدقهلية": "Dakahlia",
            "الدقهليه": "Dakahlia",
            "دقهلية": "Dakahlia",
            "دقهليه": "Dakahlia",
            "dakahlia": "Dakahlia",

            "الشرقية": "Sharqia",
            "الشرقيه": "Sharqia",
            "شرقية": "Sharqia",
            "شرقيه": "Sharqia",
            "sharqia": "Sharqia",
            "sharkia": "Sharqia",

            "كفر الشيخ": "Kafr El Sheikh",
            "كفرالشيخ": "Kafr El Sheikh",
            "كفرشيخ": "Kafr El Sheikh",
            "قفر الشيخ": "Kafr El Sheikh",
            "قفرالشيخ": "Kafr El Sheikh",
            "كفر الشيخة": "Kafr El Sheikh",
            "kafr el sheikh": "Kafr El Sheikh",
            "kafr-el-sheikh": "Kafr El Sheikh",
            "kafrelsheikh": "Kafr El Sheikh",

            "الغربية": "Gharbia",
            "الغربيه": "Gharbia",
            "غربية": "Gharbia",
            "غربيه": "Gharbia",
            "gharbia": "Gharbia",
            "gharbeya": "Gharbia",

            "المنوفية": "Monufia",
            "المنوفيه": "Monufia",
            "منوفية": "Monufia",
            "منوفيه": "Monufia",
            "monufia": "Monufia",
            "menoufia": "Monufia",

            "البحيرة": "Beheira",
            "البحيره": "Beheira",
            "بحيرة": "Beheira",
            "بحيره": "Beheira",
            "beheira": "Beheira",
            "behira": "Beheira",

            "الإسماعيلية": "Ismailia",
            "الاسماعيلية": "Ismailia",
            "الإسماعيليه": "Ismailia",
            "الاسماعيليه": "Ismailia",
            "اسماعيلية": "Ismailia",
            "اسماعيليه": "Ismailia",
            "ismailia": "Ismailia",

            "الفيوم": "Fayoum",
            "فيوم": "Fayoum",
            "fayoum": "Fayoum",
            "faiyum": "Fayoum",
            "fayum": "Fayoum",

            "بني سويف": "Beni Suef",
            "بنى سويف": "Beni Suef",
            "بني سويف": "Beni Suef",
            "beni suef": "Beni Suef",
            "benisuef": "Beni Suef",

            "المنيا": "Minya",
            "منيا": "Minya",
            "minya": "Minya",
            "minia": "Minya",
            "menia": "Minya",

            "أسيوط": "Assiut",
            "اسيوط": "Assiut",
            "اسيـوط": "Assiut",
            "assiut": "Assiut",
            "asyut": "Assiut",
            "assuit": "Assiut",

            "سوهاج": "Sohag",
            "suhag": "Sohag",
            "sohag": "Sohag",
            "sohaj": "Sohag",

            "قنا": "Qena",
            "قناه": "Qena",
            "qena": "Qena",
            "qina": "Qena",

            "الأقصر": "Luxor",
            "الاقصر": "Luxor",
            "أقصر": "Luxor",
            "اقصر": "Luxor",
            "luxor": "Luxor",

            "أسوان": "Aswan",
            "اسوان": "Aswan",
            "aswan": "Aswan",

            "البحر الأحمر": "Red Sea",
            "البحر الاحمر": "Red Sea",
            "بحر الأحمر": "Red Sea",
            "بحر الاحمر": "Red Sea",
            "red sea": "Red Sea",
            "redsea": "Red Sea",

            "الوادي الجديد": "New Valley",
            "الوادي الجديده": "New Valley",
            "وادي الجديد": "New Valley",
            "وادى الجديد": "New Valley",
            "new valley": "New Valley",
            "newvalley": "New Valley",

            "شمال سيناء": "North Sinai",
            "شمال سينا": "North Sinai",
            "north sinai": "North Sinai",
            "northsina": "North Sinai",

            "جنوب سيناء": "South Sinai",
            "جنوب سينا": "South Sinai",
            "south sinai": "South Sinai",
            "southsina": "South Sinai",
        }

        for phrase, value in regions.items():
            if phrase in normalized:
                extracted["Region"] = value
                break

        # ---------------------------------------------------------
        # Years in business
        # Examples:
        # "بقاله 8 سنين"
        # "منذ 8 سنوات"
        # "8 years in business"
        # ---------------------------------------------------------
        year_patterns = [
            r"(?:بقال[هها]|بقالنا|منذ)\s*(\d+(?:[.,]\d+)?)\s*(?:سنة|سنين|سنوات|عام|أعوام)",
            r"(\d+(?:[.,]\d+)?)\s*(?:years?|yrs?)\s*(?:in business|in the business|business)",
        ]

        for pattern in year_patterns:
            match = re.search(pattern, normalized)
            if match:
                extracted["Years_in_Business"] = int(
                    float(match.group(1).replace(",", "."))
                )
                break

        # ---------------------------------------------------------
        # Employee count
        # ---------------------------------------------------------
        employee_patterns = [
            r"(?:عندي|لدينا|عندنا)\s*(\d+)\s*(?:موظف|موظفين|عامل|عمال)",
            r"(\d+)\s*(?:employees?|staff|workers?)",
        ]

        for pattern in employee_patterns:
            match = re.search(pattern, normalized)
            if match:
                extracted["Employee_Count"] = int(match.group(1))
                break

        # ---------------------------------------------------------
        # Money parser
        # ---------------------------------------------------------
        def parse_money(number: str, multiplier: float = 1.0) -> float:
            value = float(
                number.replace(",", "").replace("،", "")
            )
            return value * multiplier

        # ---------------------------------------------------------
        # Annual Revenue
        # Supports:
        # "إيراداتي السنوية حوالي 2 مليون جنيه"
        # "annual revenue 2 million"
        # ---------------------------------------------------------
        revenue_patterns = [
            (
                r"(?:إيراداتي|ايراداتي|الإيرادات|الايرادات|إيراداتنا|ايراداتنا)"
                r".{0,20}?(\d+(?:[.,]\d+)?)\s*(مليون|million|ألف|الف|thousand)?"
            ),
            (
                r"(?:annual revenue|yearly revenue)"
                r".{0,20}?(\d+(?:[.,]\d+)?)\s*(million|thousand|مليون|ألف|الف)?"
            ),
        ]

        for pattern in revenue_patterns:
            match = re.search(pattern, normalized)
            if match:
                multiplier = 1.0
                unit = (match.group(2) or "").lower()

                if unit in ("مليون", "million"):
                    multiplier = 1_000_000
                elif unit in ("ألف", "الف", "thousand"):
                    multiplier = 1_000

                extracted["Annual_Revenue"] = parse_money(
                    match.group(1),
                    multiplier,
                )
                break

        # ---------------------------------------------------------
        # Explicit numeric/count fields
        #
        # These patterns intentionally recognize the way people
        # actually speak, especially in Arabic voice transcripts:
        # "اللي جمعتها", "اللي دفعتها", "حصل لي تدقيق مرتين",
        # "60% من المعاملات نقدية", "مستندين ناقصين".
        # ---------------------------------------------------------

        def money_value(
            number: str,
            unit: str = "",
        ) -> float:

            value = float(
                number.replace(",", "")
                      .replace("،", "")
            )

            unit = (unit or "").lower()

            if unit in {
                "مليون",
                "million",
            }:
                value *= 1_000_000

            elif unit in {
                "ألف",
                "الف",
                "thousand",
                "k",
            }:
                value *= 1_000

            return value

        # Annual expenses
        match = re.search(
            r"(?:مصاريفي|مصروفاتي|المصاريف|المصروفات|"
            r"المصاريف السنوية|المصروفات السنوية|"
            r"annual expenses|yearly expenses)"
            r".{0,35}?(\d+(?:[.,]\d+)?)\s*"
            r"(مليون|million|ألف|الف|thousand|k)?",
            normalized,
        )

        if match:
            extracted["Annual_Expenses"] = money_value(
                match.group(1),
                match.group(2) or "",
            )

        # Taxable income
        match = re.search(
            r"(?:الدخل الخاضع للضريبة|"
            r"الدخل الخاضع للضريبه|"
            r"taxable income)"
            r".{0,35}?(\d+(?:[.,]\d+)?)\s*"
            r"(مليون|million|ألف|الف|thousand|k)?",
            normalized,
        )

        if match:
            extracted["Taxable_Income"] = money_value(
                match.group(1),
                match.group(2) or "",
            )

        # Declared tax
        match = re.search(
            r"(?:الضريبة المعلنة|"
            r"الضريبة المصرح بها|"
            r"الضريبة المصرح عنها|"
            r"declared tax)"
            r".{0,35}?(\d+(?:[.,]\d+)?)\s*"
            r"(مليون|million|ألف|الف|thousand|k)?",
            normalized,
        )

        if match:
            extracted["Declared_Tax"] = money_value(
                match.group(1),
                match.group(2) or "",
            )

        # VAT collected
        match = re.search(
            r"(?:ضريبة\s+القيمة\s+المضافة|vat)"
            r".{0,45}?"
            r"(?:التي|اللى|اللي)?\s*"
            r"(?:جمعتها|جمعته|تم\s+جمعها|collected)"
            r".{0,20}?"
            r"(\d+(?:[.,]\d+)?)\s*"
            r"(مليون|million|ألف|الف|thousand|k)?",
            normalized,
        )

        if match:
            extracted["VAT_Collected"] = money_value(
                match.group(1),
                match.group(2) or "",
            )

        # VAT paid
        match = re.search(
            r"(?:ضريبة\s+القيمة\s+المضافة|vat)"
            r".{0,45}?"
            r"(?:التي|اللى|اللي)?\s*"
            r"(?:دفعتها|دفعته|تم\s+دفعها|paid)"
            r".{0,20}?"
            r"(\d+(?:[.,]\d+)?)\s*"
            r"(مليون|million|ألف|الف|thousand|k)?",
            normalized,
        )

        if match:
            extracted["VAT_Paid"] = money_value(
                match.group(1),
                match.group(2) or "",
            )

        # Previous audits.
        #
        # Numeric form:
        #   "تدقيق ضريبي مرتين"
        #   "audit 2 times"
        #
        # Arabic dual "مرتين" is explicitly handled.
        audit_match = re.search(
            r"(?:تدقيق|مراجعة|audit|audits)"
            r".{0,35}?"
            r"(مرتين|مرة واحدة|مرة|مرات|times?|"
            r"\d+)",
            normalized,
        )

        if audit_match:
            token = audit_match.group(1)

            if token == "مرتين":
                extracted["Previous_Audits"] = 2

            elif token == "مرة واحدة":
                extracted["Previous_Audits"] = 1

            elif token == "مرة":
                extracted["Previous_Audits"] = 1

            elif token in {"مرات", "times", "time"}:
                pass

            else:
                extracted["Previous_Audits"] = int(
                    token
                )

        # Previous violations.
        violation_match = re.search(
            r"(?:مخالفات|violations)"
            r".{0,20}?"
            r"(\d+)\s*(?:مخالفة|مخالفات|violations)?",
            normalized,
        )

        if violation_match:
            extracted["Previous_Violations"] = int(
                violation_match.group(1)
            )

        # Late payments.
        late_match = re.search(
            r"(?:اتأخرت|تأخرت|تأخير|late)"
            r".{0,30}?"
            r"(\d+)\s*(?:مرة|مرات|times)?",
            normalized,
        )

        if late_match:
            extracted["Late_Payments"] = int(
                late_match.group(1)
            )

        # Cash transactions percentage.
        #
        # Handles:
        #   "60% من المعاملات نقدية"
        #   "60% من المعاملات عندي نقدية"
        #   "المعاملات النقدية حوالي 60%"
        cash_patterns = [
            r"(\d+(?:[.,]\d+)?)\s*%\s*"
            r".{0,20}?(?:المعاملات|transactions)"
            r".{0,20}?(?:نقدية|نقد|cash)",

            r"(?:المعاملات\s+النقدية|cash\s+transactions)"
            r".{0,25}?"
            r"(\d+(?:[.,]\d+)?)\s*%?",
        ]

        for pattern in cash_patterns:
            match = re.search(
                pattern,
                normalized,
            )

            if match:
                extracted[
                    "Cash_Transactions_Percentage"
                ] = float(
                    match.group(1).replace(",", ".")
                )
                break

        # Missing documents.
        #
        # Numeric form:
        #   "عندي 2 مستندات ناقصة"
        # Word form:
        #   "عندي مستندين ناقصين"
        missing_doc_match = re.search(
            r"(?:عندي|لدينا|عندنا)?\s*"
            r"(?:(\d+)\s*(?:مستند|مستندات|وثيقة|وثائق)"
            r"|(?:مستندين|وثيقتين))"
            r".{0,15}?(?:ناقص|مفقود|missing)?",
            normalized,
        )

        if missing_doc_match:
            if missing_doc_match.group(1):
                extracted["Missing_Documents"] = int(
                    missing_doc_match.group(1)
                )
            else:
                extracted["Missing_Documents"] = 2

        # Invoice mismatch, numeric form.
        mismatch_match = re.search(
            r"(?:اختلاف|اختلافات|عدم\s+تطابق|"
            r"invoice\s+mismatch|invoice\s+mismatches)"
            r".{0,20}?"
            r"(\d+)\s*(?:حالة|حالات|cases)?",
            normalized,
        )

        if mismatch_match:
            extracted["Invoice_Mismatch"] = int(
                mismatch_match.group(1)
            )

        # Explicit zero statements.
        zero_patterns = {
            "Previous_Violations": [
                "مفيش مخالفات",
                "مفيش أي مخالفات",
                "مفيش عندي مخالفات",
                "لا توجد مخالفات",
                "لا يوجد مخالفات",
                "محصلتش لي أي مخالفات",
                "محصلتش مخالفات",
                "no violations",
                "no previous violations",
            ],
            "Invoice_Mismatch": [
                "مفيش اختلاف في الفواتير",
                "لا يوجد اختلاف في الفواتير",
                "لا توجد اختلافات في الفواتير",
                "مفيش اختلافات في الفواتير",
                "no invoice mismatch",
                "no invoice mismatches",
            ],
        }

        for field, phrases in zero_patterns.items():
            if field not in extracted and any(
                phrase in normalized
                for phrase in phrases
            ):
                extracted[field] = 0

        return extracted

    # =========================================================
    # JSON PARSER

    # =========================================================

    @staticmethod
    def _parse_json_response(
        raw_response: str,
    ) -> dict[str, Any]:

        if not isinstance(raw_response, str):
            return {
                "extracted": {},
                "unknown_fields": [],
                "ambiguous_fields": [],
                "notes": ["LLM returned a non-string response."],
                "_parse_failed": True,
            }

        text = raw_response.strip()

        if text.startswith("```"):
            lines = text.splitlines()
            if lines:
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            first = text.find("{")
            last = text.rfind("}")

            if first == -1 or last <= first:
                return {
                    "extracted": {},
                    "unknown_fields": [],
                    "ambiguous_fields": [],
                    "notes": ["LLM returned invalid JSON."],
                    "_parse_failed": True,
                }

            try:
                result = json.loads(text[first:last + 1])
            except json.JSONDecodeError:
                return {
                    "extracted": {},
                    "unknown_fields": [],
                    "ambiguous_fields": [],
                    "notes": ["LLM returned invalid JSON."],
                    "_parse_failed": True,
                }

        if not isinstance(result, dict):
            return {
                "extracted": {},
                "unknown_fields": [],
                "ambiguous_fields": [],
                "notes": ["Invalid extraction structure."],
                "_parse_failed": True,
            }

        result.setdefault("extracted", {})
        result.setdefault("unknown_fields", [])
        result.setdefault("ambiguous_fields", [])
        result.setdefault("notes", [])
        result["_parse_failed"] = False

        return result

# =========================================================
# SINGLETON
# =========================================================

taya_service = TayaService()