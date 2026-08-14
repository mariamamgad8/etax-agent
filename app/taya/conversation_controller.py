from enum import Enum
from pathlib import Path
from typing import Any
import json
import re

class ConversationState(str, Enum):
    GREETING="GREETING"
    LANGUAGE_SELECTION="LANGUAGE_SELECTION"
    COLLECTING_DATA="COLLECTING_DATA"
    COMPLETE="COMPLETE"

class Intent(str, Enum):
    GREETING="GREETING"
    LANGUAGE_SELECTION="LANGUAGE_SELECTION"
    ANSWER="ANSWER"
    UNCLEAR="UNCLEAR"
    UNKNOWN="UNKNOWN"
    CORRECTION="CORRECTION"
    GENERAL_QUESTION="GENERAL_QUESTION"

class ConversationController:
    QUESTION_ORDER = ['Business_Type', 'Region', 'Years_in_Business', 'Employee_Count', 'Annual_Revenue', 'Annual_Expenses', 'Taxable_Income', 'Declared_Tax', 'VAT_Collected', 'VAT_Paid', 'Previous_Audits', 'Previous_Violations', 'Late_Payments', 'Cash_Transactions_Percentage', 'Missing_Documents', 'Invoice_Mismatch']
    def __init__(self, question_bank_path=None):
        path=Path(question_bank_path) if question_bank_path else Path(__file__).resolve().parent/"question_bank.json"
        if not path.exists(): raise FileNotFoundError(f"Question bank not found: {path}")
        with path.open("r",encoding="utf-8") as f: self.question_bank=json.load(f)

    def create_conversation(self):
        return {"state":"GREETING","language":None,"current_question":None,"retry_count":0}

    def get_greeting(self):
        return self.question_bank["meta"]["greeting"]["ar"]

    @staticmethod
    def detect_language_choice(message):
        t=message.strip().lower()
        if any(x in t for x in ["عربي","عربى","بالعربي","arabic"]): return "ar"
        if any(x in t for x in ["english","انجليزي","إنجليزي","بالانجليزي","بالإنجليزي"]): return "en"
        return None

    @staticmethod
    def looks_like_greeting(message):
        t=message.strip().lower()
        return any(x in t for x in ["hello","hi","hey","good morning","good evening","أهلا","اهلا","أهلاً","اهلاً","السلام عليكم","صباح الخير","مساء الخير","هاي","هلا"])

    @staticmethod
    def looks_like_unknown(message):
        t=message.strip().lower()
        return any(x in t for x in ["مش عارف","معرفش","معنديش فكرة","لا أعرف","لا اعرف","مش متأكد","i don't know","i dont know","not sure","i'm not sure","im not sure"])

    def classify_intent(self,message,language_selected=False,has_extracted_data=False,extraction_confident=True,is_correction=False):
        if not language_selected and self.detect_language_choice(message): return Intent.LANGUAGE_SELECTION
        if self.looks_like_greeting(message): return Intent.GREETING
        if is_correction: return Intent.CORRECTION
        if self.looks_like_unknown(message): return Intent.UNKNOWN
        if not extraction_confident: return Intent.UNCLEAR
        if has_extracted_data: return Intent.ANSWER
        return Intent.UNCLEAR

    def apply_language(self,conversation,language):
        if language not in ("ar","en"): raise ValueError("Language must be 'ar' or 'en'.")
        conversation.update(language=language,state="COLLECTING_DATA",retry_count=0)
        return conversation

    def get_language_question(self):
        return self.question_bank["meta"]["language_selection"]["ar"]["question"]

    def get_next_missing_feature(self,data):
        return next((f for f in self.QUESTION_ORDER if data.get(f) is None),None)

    def set_current_question(self,conversation,feature):
        conversation["current_question"]=feature

    def get_question(self,feature,language,retry=False):
        language=language if language in ("ar","en") else "ar"
        return self.question_bank[feature][language]["retry" if retry else "question"]

    def register_retry(self,conversation,max_retries=2):
        conversation["retry_count"]=conversation.get("retry_count",0)+1
        return conversation["retry_count"] <= max_retries

    def reset_retry(self,conversation):
        conversation["retry_count"]=0

    def next_action(self,conversation,data,extraction_confident=True,has_extracted_data=False):
        language=conversation.get("language")
        if not language:
            return {"action":"ASK_LANGUAGE","text":self.get_language_question()}
        if not extraction_confident:
            if self.register_retry(conversation):
                feature=conversation.get("current_question")
                if feature:
                    return {"action":"RETRY","feature":feature,"text":self.get_question(feature,language,retry=True)}
                return {"action":"CLARIFY","text":self.question_bank["meta"]["clarification"][language]}
            self.reset_retry(conversation)
        feature=self.get_next_missing_feature(data)
        if feature is None:
            conversation.update(state="COMPLETE",current_question=None)
            return {"action":"COMPLETE","feature":None,"text":None}
        conversation.update(state="COLLECTING_DATA",current_question=feature)
        self.reset_retry(conversation)
        return {"action":"ASK_QUESTION","feature":feature,"text":self.get_question(feature,language)}

conversation_controller=ConversationController()