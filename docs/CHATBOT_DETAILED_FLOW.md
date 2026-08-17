# eTax Chatbot: Complete Flow Walkthrough

A detailed trace of how a user message flows through the chatbot system from input to output, with file paths and function references.

---

## 1. USER SENDS MESSAGE (Frontend → API)

### 1.1 Frontend: ChatPage.jsx - User Types and Submits

**File:** [frontend/src/pages/ChatPage.jsx](frontend/src/pages/ChatPage.jsx)

**Flow:**
```javascript
// Line 16-28: Initialize state
export function ChatPage() {
  const { auth, signOut } = useAuth();  // Get current user token from AuthContext
  const [turns, setTurns] = useState([...]); // Chat message history
  const [pendingForm, setPendingForm] = useState(null); // Fraud form (if interrupted)
  const [busy, setBusy] = useState(false); // Loading state
  const [error, setError] = useState(''); // Error messages
  
  // Line 73-89: User types message → calls ask()
  const ask = async (text) => {
    setTurns((prev) => prev.concat({ role: 'user', body: text, time: nowLabel() }));
    setBusy(true);
    try {
      // Call backend API with user's token and message
      const response = await api.sendChatMessage(auth.token, text);
      applyResponse(response);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Something went wrong. Try again.');
    } finally {
      setBusy(false);
    }
  };
```

**Key Actions:**
- User input added to `turns` array (displayed immediately as chat bubble)
- `setBusy(true)` shows loading spinner
- Calls `api.sendChatMessage(auth.token, text)` with JWT token

---

### 1.2 API Client: client.js - Make HTTP Request

**File:** [frontend/src/api/client.js](frontend/src/api/client.js)

**Flow:**
```javascript
// Line 50-52: sendChatMessage wraps POST /chat/message
sendChatMessage: (token, message) =>
  request('/chat/message', { method: 'POST', token, body: { message } }),

// Line 11-28: Generic request function
async function request(path, { method = 'GET', token, body, isForm } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`; // Add JWT
  if (body && !isForm) headers['Content-Type'] = 'application/json';
  
  let res = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers,
    body: isForm ? body : body ? JSON.stringify(body) : undefined,
  });
  
  // Parse response JSON
  let data = await res.json();
  if (!res.ok) throw new ApiError(message, status, data);
  return data;
}
```

**HTTP Request Sent:**
```
POST http://localhost:8000/chat/message HTTP/1.1
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "message": "Check taxpayer 1002 for fraud risk"
}
```

---

## 2. BACKEND RECEIVES MESSAGE & ROUTES REQUEST

### 2.1 Backend: routes.py - Parse & Dispatch

**File:** [backend/app/chat/routes.py](backend/app/chat/routes.py)

**Flow:**
```python
# Line 21-44: POST /chat/message endpoint
@router.post("/message", response_model=ChatMessageResponse)
async def send_message(
    payload: ChatMessageRequest,  # Validates: { message?, thread_id?, form_response? }
    user: User = Depends(require_authenticated),  # Enforces JWT stage=authenticated
):
    # Case 1: Fresh message (no form_response)
    if not payload.form_response:
        if not payload.message:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "message is required")
        
        # Generate unique thread_id: "{user_id}:{random_uuid}"
        thread_id = payload.thread_id or _own_thread_id(user)
        # Verify this thread belongs to the user (thread_id starts with user.id)
        _check_thread_ownership(user, thread_id)
        
        # Run graph from start
        state, interrupt_payload = await run_in_threadpool(
            run_chat, payload.message, thread_id
        )
    
    # Case 2: Resume after form interrupt (user submitted fraud form)
    else:
        thread_id = payload.thread_id
        _check_thread_ownership(user, thread_id)
        
        # Resume paused graph with form values
        state, interrupt_payload = await run_in_threadpool(
            resume_chat, payload.form_response, thread_id
        )
```

**Key Validations:**
- `require_authenticated` dependency ensures JWT `stage=authenticated` (enforced by backend)
- Thread ownership check: thread_id format `{user_id}:{uuid}` prevents user A from accessing user B's conversation
- Each stage token is short-lived, preventing replay attacks

---

### 2.2 Graph Functions: graph.py - Core Logic

**File:** [backend/app/chat/graph.py](backend/app/chat/graph.py) Lines 292-320

```python
def run_chat(query: str, thread_id: str):
    """
    Starts a fresh graph run on thread_id.
    Returns (state, interrupt_payload_or_None)
    """
    config = {"configurable": {"thread_id": thread_id}}
    initial_state: AgentState = {
        "original_query": query,
        "normalized_query": query.strip(),
    }
    # Get compiled graph with InMemorySaver checkpointer
    result = get_graph().invoke(initial_state, config=config)
    return result, _extract_interrupt(result)


def resume_chat(resume_value, thread_id: str):
    """
    Resumes a paused run (continues from interrupt).
    Returns (state, interrupt_payload_or_None)
    """
    config = {"configurable": {"thread_id": thread_id}}
    # Command(resume=...) tells LangGraph to continue from the interrupt
    result = get_graph().invoke(Command(resume=resume_value), config=config)
    return result, _extract_interrupt(result)
```

**AgentState Structure:**

**File:** [backend/app/chat/state.py](backend/app/chat/state.py)

```python
class AgentState(TypedDict, total=False):
    # Request input
    original_query: str                    # User's raw message
    normalized_query: str                  # query.strip()
    
    # Intent classification (after route_intent node)
    intent: str                            # One of 7 intents
    intent_confidence: float               # 0.0-1.0
    
    # Fraud assessment branch (optional, only if intent=fraud_assessment)
    extracted_features: dict               # LLM extraction result (all-Optional)
    confirmed_features: dict               # User-reviewed + confirmed form
    fraud_validation_errors: list[str]     # Validation errors (if any)
    prediction_label: str                  # "Suspicious" or "Not suspicious"
    prediction_probability: float          # 0.0-1.0 model score
    
    # Database query branch (optional, only if intent=database_query)
    db_question_en: str                    # Rephrased English question
    sql_result: dict                       # {"columns": [...], "rows": [...], "error": ...}
    
    # Final response
    final_response: str                    # Text to show user
    response_payload: dict                 # {"table": {...}} or {}
```

---

## 3. INTENT CLASSIFICATION

### 3.1 Route Intent Node

**File:** [backend/app/chat/graph.py](backend/app/chat/graph.py) Lines 35-38

```python
def route_intent(state: AgentState) -> AgentState:
    # Call LLM to classify intent
    result = classify_intent(state["normalized_query"])
    logger.info("Routed query to intent=%s confidence=%.2f", result.intent, result.confidence)
    return {**state, "intent": result.intent, "intent_confidence": result.confidence}
```

### 3.2 Classify Intent Function

**File:** [backend/app/chat/intent.py](backend/app/chat/intent.py) Lines 67-73

```python
def classify_intent(query: str) -> IntentResult:
    """
    Calls LLM with structured output to classify user's message into one of 7 intents.
    Uses call_llm_structured() from providers/llm.py with fallback/cooldown.
    """
    return call_llm_structured(_SYSTEM_PROMPT, query, IntentResult)
```

**System Prompt (lines 35-65):**
```
You are the intent router for eTax...

Seven intents:
- fraud_assessment: user wants fraud/risk check
- database_query: user wants to look up records
- assistant_identity: asking who/what the assistant is
- tax_conversation: general tax question
- off_topic: unrelated to tax
- unclear: says "check X" with no detail (could be fraud or records)
- multi_intent: two or more different actions in one message

Key distinction:
  "Show me payments for taxpayer 1002" → database_query (explicit retrieval)
  "Check taxpayer 1002" → unclear (ambiguous which check: fraud or records?)
  "Show me payments AND check for fraud" → multi_intent (two actions)
```

**IntentResult Model:**

**File:** [backend/app/chat/intent.py](backend/app/chat/intent.py) Lines 17-32

```python
class IntentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")  # Strict JSON schema
    intent: Intent  # Literal["fraud_assessment", "database_query", ...]
    confidence: float  # Field(ge=0, le=1)
    reasoning: str  # One sentence explanation
```

**LLM Call (Groq or Gemini via fallback):**

**File:** [backend/app/chat/providers/llm.py](backend/app/chat/providers/llm.py) Lines 85-115

```python
def _call_groq_structured(model: str, system: str, user: str, response_model: type[T]) -> T:
    """
    Calls Groq with JSON schema mode (strict if model supports it, fallback otherwise).
    """
    schema = response_model.model_json_schema()
    
    if model in _GROQ_JSON_SCHEMA_MODELS:
        # Use strict mode: response_format={"type": "json_schema", ...}
        completion = _groq_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0,  # Deterministic
            response_format={
                "type": "json_schema",
                "json_schema": {"name": response_model.__name__, "schema": strict_schema, "strict": True},
            },
        )
    else:
        # Fallback: json_object mode + schema in prompt
        completion = _groq_client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system + schema_note},
                {"role": "user", "content": user},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
    
    raw = completion.choices[0].message.content
    return response_model.model_validate_json(raw)  # Parse JSON
```

**Example Output:**
```json
{
  "intent": "fraud_assessment",
  "confidence": 0.95,
  "reasoning": "User explicitly asked to check fraud risk on a taxpayer."
}
```

### 3.3 Intent Routing Decision

**File:** [backend/app/chat/graph.py](backend/app/chat/graph.py) Lines 284-290

```python
# INTENT_ROUTING is a Python dict, NOT an LLM decision
INTENT_ROUTING: dict[str, str] = {
    "fraud_assessment": "extract_fraud_fields",      # → Fraud branch
    "database_query": "prepare_db_question",          # → Database branch
    "assistant_identity": "assistant_identity",       # → Placeholder
    "tax_conversation": "tax_conversation",           # → Placeholder
    "off_topic": "off_topic",                         # → Placeholder
    "unclear": "clarify_intent",                      # → Placeholder
    "multi_intent": "handle_multi_intent",            # → Placeholder
}

# Graph conditional edge: route_intent → branch node
graph.add_conditional_edges(
    "route_intent",
    lambda s: INTENT_ROUTING.get(s.get("intent", ""), "clarify_intent"),
    all_branches
)
```

---

## 4. BRANCH A: FRAUD ASSESSMENT

**For message: "Check taxpayer 1002 for fraud risk"** after intent→fraud_assessment

### 4.1 Extract Fraud Fields Node

**File:** [backend/app/chat/graph.py](backend/app/chat/graph.py) Lines 41-43

```python
def extract_fraud_fields(state: AgentState) -> AgentState:
    # Call LLM with all-Optional FraudFeatures model
    features = extract_fraud_features(state["normalized_query"])
    # Only values the user mentioned; unmentioned fields stay null
    return {**state, "extracted_features": features.model_dump(exclude_none=True)}
```

**Extract Function:**

**File:** [backend/app/chat/fraud/extraction.py](backend/app/chat/fraud/extraction.py)

```python
_SYSTEM_PROMPT = """You extract fraud-risk-assessment inputs from a user's message.
Fill in ONLY fields the user stated or clearly implied — leave others null.
Never guess, never estimate, never fill in defaults.
Missing means null, not 0 and not "Unknown".

Business_Type must be one of: Construction, Restaurant, Education, IT, ... (or null)
Region must be one of: Cairo, Giza, Alex, ... (or null)
Industry_Risk must be one of: Low, Medium, High (or null)

All other fields are numbers — extract only if a number for that concept is present."""

def extract_fraud_features(query: str) -> FraudFeatures:
    return call_llm_structured(_SYSTEM_PROMPT, query, FraudFeatures)
```

**FraudFeatures Model:**

**File:** [backend/app/chat/fraud/schema.py](backend/app/chat/fraud/schema.py) Lines 79-123

```python
class FraudFeatures(BaseModel):
    """
    All 23 fields optional because LLM extraction may not fill all.
    Validation happens AFTER user review.
    """
    model_config = ConfigDict(extra="forbid")
    
    # Categorical (3 fields)
    Business_Type: Optional[BusinessType] = None  # Literal[Construction, ...]
    Region: Optional[RegionValue] = None          # Literal[Cairo, Giza, ...]
    Industry_Risk: Optional[IndustryRisk] = None  # Literal[Low, Medium, High]
    
    # Numeric integer-only (7 fields)
    Years_in_Business: Optional[float] = None
    Employee_Count: Optional[float] = None
    Previous_Audits: Optional[float] = None
    Previous_Violations: Optional[float] = None
    Late_Payments: Optional[float] = None
    Missing_Documents: Optional[float] = None
    Invoice_Mismatch: Optional[float] = None
    
    # Numeric float (13 fields)
    Annual_Revenue: Optional[float] = None
    Annual_Expenses: Optional[float] = None
    Net_Profit: Optional[float] = None
    Taxable_Income: Optional[float] = None
    Expected_Tax: Optional[float] = None
    Declared_Tax: Optional[float] = None
    VAT_Collected: Optional[float] = None
    VAT_Paid: Optional[float] = None
    Cash_Transactions_Percentage: Optional[float] = None
    Expense_Ratio: Optional[float] = None
    Profit_Margin: Optional[float] = None
    Revenue_per_Employee: Optional[float] = None
    Tax_Gap: Optional[float] = None
```

**Example Extraction Result:**
```python
{
    "Business_Type": None,  # User didn't mention
    "Region": None,
    "Industry_Risk": None,
    "Years_in_Business": None,
    ...
    # All None because "check taxpayer 1002 for fraud" has no specific data
}
```

**State After extract_fraud_fields:**
```python
{
    "original_query": "Check taxpayer 1002 for fraud risk",
    "normalized_query": "Check taxpayer 1002 for fraud risk",
    "intent": "fraud_assessment",
    "intent_confidence": 0.95,
    "extracted_features": {},  # All None, excluded from dict
}
```

### 4.2 Review Form Node (INTERRUPT)

**File:** [backend/app/chat/graph.py](backend/app/chat/graph.py) Lines 46-71

```python
_FRAUD_FORM_SCHEMA = {
    "numeric_fields": NUMERIC_FIELD_ORDER,  # 20-element list
    "integer_fields": INT_FIELDS,           # 7-element list
    "categorical_fields": {
        "Business_Type": BUSINESS_TYPE_OPTIONS,    # 10 options
        "Region": REGION_OPTIONS,                  # 9 options
        "Industry_Risk": INDUSTRY_RISK_OPTIONS,    # 3 options
    },
}

def review_form(state: AgentState) -> AgentState:
    """
    Always shown, even if extraction filled every field.
    User reviews/corrects before anything runs.
    Calls interrupt() to pause the graph.
    """
    # Prefill with extracted values or confirmed (if looping back from validation)
    prefill = state.get("confirmed_features") or state.get("extracted_features") or {}
    
    # Pause graph and send payload to frontend
    submitted = interrupt({
        "type": "fraud_form",
        "fields": prefill,  # Currently empty
        "errors": state.get("fraud_validation_errors") or [],  # Empty on first run
        "schema": _FRAUD_FORM_SCHEMA,  # Tells frontend which options to show
    })
    
    # When resumed, submitted contains user-filled form values
    return {**state, "confirmed_features": submitted}
```

**Graph Execution at Interrupt:**
- LangGraph checkpoints state into `InMemorySaver` with key `thread_id`
- `interrupt()` raises a `GraphInterrupt` exception
- Graph.invoke() catches it and returns the payload in `result["__interrupt__"]`

### 4.3 Backend Response to Frontend (Interrupt Case)

**File:** [backend/app/chat/routes.py](backend/app/chat/routes.py) Lines 62-71

```python
# interrupt_payload is not None (graph paused)
if interrupt_payload is not None:
    return ChatMessageResponse(
        thread_id=thread_id,
        intent=state.get("intent"),
        awaiting=AwaitingInput(  # Signal frontend to show form
            type=interrupt_payload["type"],        # "fraud_form"
            fields=interrupt_payload["fields"],    # {} (empty)
            errors=interrupt_payload["errors"],    # []
            schema_=interrupt_payload["schema"],   # Schema with options
        ),
    )
```

**HTTP Response Sent to Frontend:**
```json
{
  "thread_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479:abc123",
  "intent": "fraud_assessment",
  "reply": null,
  "awaiting": {
    "type": "fraud_form",
    "fields": {},
    "errors": [],
    "schema": {
      "numeric_fields": [
        "Years_in_Business", "Employee_Count", "Annual_Revenue", ...
      ],
      "integer_fields": [
        "Years_in_Business", "Employee_Count", "Previous_Audits", ...
      ],
      "categorical_fields": {
        "Business_Type": ["Construction", "Restaurant", "Education", ...],
        "Region": ["Cairo", "Giza", "Alex", ...],
        "Industry_Risk": ["Low", "Medium", "High"]
      }
    }
  },
  "table": null
}
```

---

### 4.4 Frontend: Display Fraud Form

**File:** [frontend/src/pages/ChatPage.jsx](frontend/src/pages/ChatPage.jsx) Lines 56-72

```javascript
const applyResponse = (response) => {
  if (response.awaiting) {
    // Interrupt: show form
    setPendingForm({
      threadId: response.thread_id,
      fields: response.awaiting.fields || {},      // Empty
      errors: response.awaiting.errors || [],      // []
      schemaInfo: response.awaiting.schema,
    });
  } else {
    // No interrupt: show text + optional table
    setPendingForm(null);
    pushAssistantTurn(response);
  }
};

// Render form
{pendingForm && (
  <ChatMessage role="assistant" time={nowLabel()}>
    <FraudForm
      fields={pendingForm.fields}
      errors={pendingForm.errors}
      schemaInfo={pendingForm.schemaInfo}
      onSubmit={submitForm}
      submitting={busy}
    />
  </ChatMessage>
)}
```

**File:** [frontend/src/components/chat/FraudForm.jsx](frontend/src/components/chat/FraudForm.jsx)

```javascript
export function FraudForm({ fields, errors, schemaInfo, onSubmit, submitting }) {
  const [values, setValues] = useState(() => ({ ...fields }));  // Empty initially
  
  const submit = (e) => {
    e.preventDefault();
    
    // Convert form values, respecting integer_fields vs numeric_fields
    const payload = {};
    for (const [key, raw] of Object.entries(values)) {
      if (raw === '' || raw === undefined || raw === null) continue;
      // Convert numeric fields to Number, rest stay as string
      payload[key] = schemaInfo.numeric_fields.includes(key) ? Number(raw) : raw;
    }
    
    // Call submitForm with filled values
    onSubmit(payload);
  };
  
  return (
    <form onSubmit={submit}>
      {/* Render input fields for all 23 fraud fields */}
      {/* Show errors from validation loop-back */}
      <Button type="submit" disabled={submitting}>
        Assess Risk
      </Button>
    </form>
  );
}
```

**User Fills Form and Clicks "Assess Risk":**
```javascript
submitForm: async (values) => {
  // values = { Annual_Revenue: 500000, Years_in_Business: 5, ... }
  // Only filled fields included
  
  const response = await api.resumeChatForm(
    auth.token,
    pendingForm.threadId,  // "user_id:uuid"
    values                  # Submitted form data
  );
}
```

---

### 4.5 Frontend Resumes Chat (Form Submission)

**File:** [frontend/src/api/client.js](frontend/src/api/client.js) Lines 53-57

```javascript
resumeChatForm: (token, threadId, formResponse) =>
  request('/chat/message', {
    method: 'POST',
    token,
    body: {
      thread_id: threadId,    # "user_id:uuid"
      form_response: formResponse  # { Annual_Revenue: 500000, ... }
    },
  }),
```

**HTTP Request:**
```
POST http://localhost:8000/chat/message HTTP/1.1
Authorization: Bearer <jwt_token>
Content-Type: application/json

{
  "thread_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479:abc123",
  "form_response": {
    "Annual_Revenue": 500000,
    "Annual_Expenses": 300000,
    "Net_Profit": 200000,
    "Taxable_Income": 180000,
    "Expected_Tax": 45000,
    "Declared_Tax": 40000,
    "Business_Type": "Retail",
    "Region": "Cairo",
    "Industry_Risk": "Medium",
    "Years_in_Business": 5,
    ... (all 23 fields)
  }
}
```

---

### 4.6 Backend: Resume Chat

**File:** [backend/app/chat/routes.py](backend/app/chat/routes.py) Lines 43-50

```python
is_resume = payload.form_response is not None
if is_resume:
    if not payload.thread_id:
        raise HTTPException(...)
    _check_thread_ownership(user, payload.thread_id)
    
    thread_id = payload.thread_id
    
    # Resume graph from the paused point
    state, interrupt_payload = await run_in_threadpool(
        resume_chat,  # LangGraph resume
        payload.form_response,  # Form values
        thread_id
    )
```

**File:** [backend/app/chat/graph.py](backend/app/chat/graph.py) Lines 310-315

```python
def resume_chat(resume_value, thread_id: str):
    """Resumes a paused run on thread_id."""
    config = {"configurable": {"thread_id": thread_id}}
    # Command(resume=...) tells LangGraph to continue from the interrupt
    result = get_graph().invoke(Command(resume=resume_value), config=config)
    return result, _extract_interrupt(result)
```

---

### 4.7 Validate Fraud Form Node

Graph resumes from `review_form` interrupt and continues to next node: `validate_fraud_form`

**File:** [backend/app/chat/graph.py](backend/app/chat/graph.py) Lines 76-79

```python
def validate_fraud_form(state: AgentState) -> AgentState:
    # All form values in state["confirmed_features"]
    errors = validate_fraud_features(state.get("confirmed_features") or {})
    return {**state, "fraud_validation_errors": errors}
```

**File:** [backend/app/chat/fraud/validation.py](backend/app/chat/fraud/validation.py) Lines 19-50

```python
def validate_fraud_features(values: dict) -> list[str]:
    """Returns list of error strings; empty means ready to predict."""
    errors: list[str] = []
    
    # Check all fields are present
    for field in ALL_FIELDS:
        value = values.get(field)
        if value is None or value == "":
            errors.append(f"{field} is required.")
    
    # Validate categorical fields
    for field in CATEGORICAL_FIELDS:
        value = values.get(field)
        if value not in _CATEGORICAL_OPTIONS[field]:
            errors.append(f"{field} must be one of: ...")
    
    # Validate integer fields (whole numbers, non-negative)
    for field in INT_FIELDS:
        value = values.get(field)
        if not _is_number(value) or float(value) != int(value):
            errors.append(f"{field} must be a whole number.")
        elif value < 0:
            errors.append(f"{field} cannot be negative.")
    
    # Validate float fields (numbers, can be signed)
    for field in FLOAT_FIELDS:
        value = values.get(field)
        if not _is_number(value):
            errors.append(f"{field} must be a number.")
    
    # Range check for percentage
    percentage = values.get("Cash_Transactions_Percentage")
    if _is_number(percentage) and not (0 <= percentage <= 100):
        errors.append("Cash_Transactions_Percentage must be between 0 and 100.")
    
    return errors
```

### 4.8 Conditional Edge: Valid or Loop Back?

**File:** [backend/app/chat/graph.py](backend/app/chat/graph.py) Lines 213-217

```python
def _fraud_form_valid(state: AgentState) -> str:
    # If errors exist, route back to review_form for correction
    return "predict_fraud" if not state.get("fraud_validation_errors") else "review_form"

# Conditional edge in graph
graph.add_conditional_edges(
    "validate_fraud_form", _fraud_form_valid, ["predict_fraud", "review_form"]
)
```

**Case A: Validation Passes**
→ Continue to `predict_fraud` node

**Case B: Validation Fails**
→ Loop back to `review_form` node (sends interrupt again with errors + prefilled values)

Frontend receives:
```json
{
  "awaiting": {
    "type": "fraud_form",
    "fields": { "Annual_Revenue": 500000, ... },  # Prefilled from last submission
    "errors": [
      "Cash_Transactions_Percentage must be between 0 and 100.",
      "Business_Type must be one of: ..."
    ]
  }
}
```

User sees form again with:
- Previous values prefilled
- Error messages highlighted
- Can correct and resubmit

---

### 4.9 Predict Fraud Node (XGBoost)

After validation passes, next node: `predict_fraud`

**File:** [backend/app/chat/graph.py](backend/app/chat/graph.py) Lines 82-84

```python
def predict_fraud(state: AgentState) -> AgentState:
    # confirmed_features now has all 23 fields validated
    label, probability = predict_fraud_model(state["confirmed_features"])
    return {**state, "prediction_label": label, "prediction_probability": probability}
```

**File:** [backend/app/chat/fraud/engine.py](backend/app/chat/fraud/engine.py) Lines 50-62

```python
def predict(values: dict) -> tuple[str, float]:
    """
    `values` has all 23 fields, already validated.
    Returns (label, probability_for_suspicious_class)
    """
    _, _, model = _load()  # Load cached encoders + XGBoost model
    frame = _build_feature_row(values)  # Transform to 40-feature DataFrame
    probability = float(model.predict_proba(frame)[0, 1])  # Get prob for class 1 (Suspicious)
    
    # Compare to threshold (0.195)
    label = "Suspicious" if probability >= FRAUD_THRESHOLD else "Not suspicious"
    return label, probability
```

**Feature Engineering: 23 → 40 Features**

**File:** [backend/app/chat/fraud/engine.py](backend/app/chat/fraud/engine.py) Lines 32-48

```python
def _build_feature_row(values: dict) -> pd.DataFrame:
    onehot, ordinal, _ = _load()
    
    # Step 1: Extract 20 numeric fields in exact order
    numeric = {field: float(values[field]) for field in NUMERIC_FIELD_ORDER}
    # NUMERIC_FIELD_ORDER = [Years_in_Business, Employee_Count, Annual_Revenue, ...]
    
    # Step 2: Ordinal encode Industry_Risk (Low=0, Medium=1, High=2)
    ordinal_df = pd.DataFrame({"Industry_Risk": [values["Industry_Risk"]]})
    industry_risk_ord = ordinal.transform(ordinal_df)[0, 0]
    
    # Step 3: One-hot encode Business_Type + Region
    onehot_df = pd.DataFrame({
        "Business_Type": [values["Business_Type"]],
        "Region": [values["Region"]]
    })
    onehot_encoded = onehot.transform(onehot_df).toarray()
    onehot_columns = onehot.get_feature_names_out(["Business_Type", "Region"])
    # Produces 10 (Business_Type) + 9 (Region) = 19 columns
    
    # Step 4: Combine
    row = {**numeric, "Industry_Risk_ord": industry_risk_ord}
    row.update(dict(zip(onehot_columns, onehot_encoded[0])))
    
    # Final DataFrame: 20 numeric + 1 ordinal + 19 one-hot = 40 columns
    feature_order = [*NUMERIC_FIELD_ORDER, "Industry_Risk_ord", *onehot_columns]
    return pd.DataFrame([row], columns=feature_order)
```

**Model Loading:**

**File:** [backend/app/chat/fraud/engine.py](backend/app/chat/fraud/engine.py) Lines 22-29

```python
_MODELS_DIR = Path(__file__).resolve().parent / "models"

_onehot = None
_ordinal = None
_model = None

def _load():
    global _onehot, _ordinal, _model
    if _model is None:
        # Load from backend/app/chat/fraud/models/
        _onehot = joblib.load(_MODELS_DIR / "onehot_encoder.joblib")      # Fits Business_Type + Region
        _ordinal = joblib.load(_MODELS_DIR / "ordinal_encoder.joblib")    # Fits Industry_Risk
        _model = joblib.load(_MODELS_DIR / "xgboost_fraud_model.joblib")  # Trained on 40 features
    return _onehot, _ordinal, _model
```

**Example Prediction Flow:**

Input (after validation):
```python
{
    "Annual_Revenue": 500000,
    "Annual_Expenses": 300000,
    "Net_Profit": 200000,
    ...
    "Business_Type": "Retail",
    "Region": "Cairo",
    "Industry_Risk": "Medium",
}
```

→ Transform to 40 features:
```
[500000, 300000, 200000, ..., 45000, 40000]  # 20 numeric
+ [1]  # Industry_Risk: Medium (ordinal encoded)
+ [0, 0, 0, 0, 0, 0, 0, 0, 1, 0]  # Business_Type: Retail (10-d one-hot)
+ [0, 0, 0, 0, 1, 0, 0, 0, 0]  # Region: Cairo (9-d one-hot)
= 40 total features
```

→ XGBoost predicts:
```
probability = 0.32 (32% chance of fraud)
FRAUD_THRESHOLD = 0.195
→ label = "Suspicious" (0.32 >= 0.195)
```

---

### 4.10 Fraud Response Node

**File:** [backend/app/chat/graph.py](backend/app/chat/graph.py) Lines 86-94

```python
def fraud_response(state: AgentState) -> AgentState:
    label = state["prediction_label"]  # "Suspicious"
    probability = state["prediction_probability"]  # 0.32
    
    # Generate hedged response
    text = (
        f'The model returned a result of "{label}" for this input '
        f'(score {probability:.2f} on a 0.00-1.00 scale, review threshold {FRAUD_THRESHOLD:.2f}). '
        "A score above the review threshold does not confirm fraud — refer the case for manual "
        "review before taking any action."
    )
    
    return {**state, "final_response": text}
```

**Generates:**
```
The model returned a result of "Suspicious" for this input (score 0.32 on a 0.00-1.00 scale, review threshold 0.19). A score above the review threshold does not confirm fraud — refer the case for manual review before taking any action.
```

**Graph ends (fraud_response → END)**

---

## 5. BRANCH B: DATABASE QUERY

**For message: "Show me all tax payments for taxpayer 1005 in 2025"** after intent→database_query

### 5.1 Prepare DB Question Node

**File:** [backend/app/chat/graph.py](backend/app/chat/graph.py) Lines 143-146

```python
def prepare_db_question(state: AgentState) -> AgentState:
    # Rephrase user message as English database question
    question_en = call_llm_text(_DB_QUESTION_SYSTEM_PROMPT, state["normalized_query"]).strip()
    return {**state, "db_question_en": question_en}

_DB_QUESTION_SYSTEM_PROMPT = """Rephrase the user's message as a single, clear English question \
about a tax database (tables: taxpayers, tax_returns). The message may be in Arabic, English, or a mix.

Preserve every specific detail exactly — taxpayer IDs, years, amounts, names. Never change a number \
or invent one that wasn't in the original message. Output ONLY the rephrased English question, \
nothing else (no preamble, no quotes)."""
```

**Input:** "Show me all tax payments for taxpayer 1005 in 2025"

**LLM Output:** "What are the tax payments made by taxpayer 1005 in 2025?"

---

### 5.2 Run SQL Query Node

**File:** [backend/app/chat/graph.py](backend/app/chat/graph.py) Lines 149-151

```python
def run_sql_query(state: AgentState) -> AgentState:
    result = generate_and_run_sql(state["db_question_en"])
    return {**state, "sql_result": result, "sql_error": result.get("error")}
```

**File:** [backend/app/chat/db/query_chain.py](backend/app/chat/db/query_chain.py) Lines 201-245

```python
def generate_and_run_sql(question_en: str) -> dict:
    """
    1. LLM generates SQL
    2. Python validates (SELECT-only, no dangerous keywords)
    3. Execute against read-only SQLite
    Returns {"sql", "columns", "rows", "error"}
    """
    
    # Step 1: Call LLM to generate SQL
    raw = call_llm_text(_sql_generation_prompt(), question_en)
    # Returns: "SELECT amount_paid, year FROM tax_returns WHERE taxpayer_id = 1005 AND year = 2025"
    
    # Step 2: Clean (strip markdown code fences)
    sql = _clean_sql(raw)
    
    # Step 3: Validate
    if not sql.lower().startswith("select"):
        return {"sql": sql, "columns": None, "rows": None, "error": "Not a SELECT query"}
    
    if ";" in sql:
        return {"sql": sql, ..., "error": "Only single statement allowed"}
    
    if _FORBIDDEN_SQL_KEYWORDS.search(sql):  # INSERT, UPDATE, DELETE, DROP, ALTER, ...
        return {"sql": sql, ..., "error": "Disallowed keyword"}
    
    # Step 4: Execute
    try:
        columns, rows = _execute_readonly(sql)
    except Exception as exc:
        return {"sql": sql, ..., "error": str(exc)}
    
    return {"sql": sql, "columns": columns, "rows": rows, "error": None}
```

**SQL Generation Prompt:**

**File:** [backend/app/chat/db/query_chain.py](backend/app/chat/db/query_chain.py) Lines 194-201

```python
def _sql_generation_prompt() -> str:
    return f"""You write a single SQLite SELECT query to answer a question about this schema:

{_get_db().get_table_info()}

Rules:
- Output ONLY the raw SQL statement — no markdown code fences, no backticks, no explanation.
- Exactly one SELECT statement.
- Only use columns and tables shown above.
- Add "LIMIT 20" unless asking for count, sum, average, or aggregate.
"""
```

**Read-Only Execution:**

**File:** [backend/app/chat/db/query_chain.py](backend/app/chat/db/query_chain.py) Lines 156-166

```python
def _execute_readonly(sql: str):
    """Re-runs SQL against read-only SQLite connection."""
    if not sql.strip().lower().startswith("select"):
        raise ValueError("Only SELECT statements")
    
    from app.chat.db.connection import get_connection
    
    conn = get_connection()  # Opens SQLite in read-only mode
    try:
        cursor = conn.execute(sql)
        columns = [d[0] for d in cursor.description]
        rows = [dict(row) for row in cursor.fetchall()]
        return columns, rows
    finally:
        conn.close()
```

**Example SQL Execution:**
```sql
SELECT amount_paid, year FROM tax_returns 
WHERE taxpayer_id = 1005 AND year = 2025
LIMIT 20;
```

**Result:**
```python
{
    "columns": ["amount_paid", "year"],
    "rows": [
        {"amount_paid": 50000, "year": 2025},
        {"amount_paid": 12500, "year": 2025},
    ],
    "error": None
}
```

---

### 5.3 DB Response Node (Language Detection + Summarization)

**File:** [backend/app/chat/graph.py](backend/app/chat/graph.py) Lines 177-202

```python
def db_response(state: AgentState) -> AgentState:
    sql_result = state.get("sql_result") or {}
    
    # Detect user's original language (Arabic or English)
    language = _detect_language_name(state["original_query"])
    
    # Case A: SQL error or no results
    if sql_result.get("error") or not sql_result.get("rows"):
        text = call_llm_text(
            _no_result_prompt(language),  # Tells LLM: respond in {language}
            state["original_query"]
        )
        return {**state, "final_response": text.strip(), "response_payload": {}}
    
    # Case B: Results found → summarize + table
    columns = sql_result["columns"]
    rows = sql_result["rows"]
    
    # Ask LLM to summarize in detected language
    summary_user_prompt = (
        f"User's original question: {state['original_query']}\n\n"
        f"Retrieved records (JSON): {json.dumps(rows[:20], default=str)}"
    )
    summary = call_llm_text(
        _summary_prompt(language),
        summary_user_prompt
    ).strip()
    
    # Format table for frontend
    table = {
        "columns": [c.replace("_", " ").title() for c in columns],  # "amount_paid" → "Amount Paid"
        "rows": [[row.get(c) for c in columns] for row in rows],
    }
    
    return {**state, "final_response": summary, "response_payload": {"table": table}}
```

**Language Detection:**

**File:** [backend/app/chat/graph.py](backend/app/chat/graph.py) Lines 125-137

```python
_ARABIC_SCRIPT = re.compile(r"[؀-ۿ]")  # Unicode range for Arabic

def _detect_language_name(text: str) -> str:
    """Cheap heuristic: check for Arabic Unicode characters."""
    return "Arabic" if _ARABIC_SCRIPT.search(text) else "English"
```

**Summary Prompts:**

**File:** [backend/app/chat/graph.py](backend/app/chat/graph.py) Lines 138-163

```python
def _no_result_prompt(language: str) -> str:
    return f"""The user's question could not be answered from the authorized tax records \
(either no matching rows, or the request couldn't be understood as a database lookup). \
Write one short, plain sentence saying so, in {language} — respond in {language} regardless \
of what language this instruction is written in. Do not mention SQL, databases, columns, or \
any technical detail — just say the information wasn't found and suggest including a \
specific taxpayer ID or year."""

def _summary_prompt(language: str) -> str:
    return f"""You are the eTax assistant. Write a short (1-3 sentence) answer to the \
user's question, in {language} — respond in {language} regardless of what language this \
instruction or the records below are written in. Base the answer ONLY on the retrieved \
records given to you. Never state a number, name, or fact that is not literally present \
in those records. If there are many rows, summarize rather than listing each one — a table \
of the full records is shown separately, so you don't need to enumerate them."""
```

**Example Summary Generation:**
```
User question: "Show me all tax payments for taxpayer 1005 in 2025"
Retrieved rows: [{"amount_paid": 50000, "year": 2025}, {"amount_paid": 12500, "year": 2025}]

LLM generates (in English, since input was English):
"Taxpayer 1005 made two tax payments in 2025: 50,000 and 12,500. The full payment details are shown in the table below."
```

---

## 6. BACKEND RESPONSE TO FRONTEND

### 6.1 Non-Interrupt Case (DB Query or Fraud Complete)

**File:** [backend/app/chat/routes.py](backend/app/chat/routes.py) Lines 72-81

```python
table_payload = (state.get("response_payload") or {}).get("table")
return ChatMessageResponse(
    thread_id=thread_id,
    reply=state.get("final_response", ""),  # Text answer
    intent=state.get("intent"),
    table=TablePayload(**table_payload) if table_payload else None,
)
```

**HTTP Response (Database Query):**
```json
{
  "thread_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479:def456",
  "reply": "Taxpayer 1005 made two tax payments in 2025: 50,000 and 12,500...",
  "intent": "database_query",
  "awaiting": null,
  "table": {
    "columns": ["Amount Paid", "Year"],
    "rows": [
      [50000, 2025],
      [12500, 2025]
    ]
  }
}
```

**HTTP Response (Fraud Complete):**
```json
{
  "thread_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479:ghi789",
  "reply": "The model returned a result of \"Suspicious\" for this input (score 0.32 on a 0.00-1.00 scale, review threshold 0.19). A score above the review threshold does not confirm fraud — refer the case for manual review before taking any action.",
  "intent": "fraud_assessment",
  "awaiting": null,
  "table": null
}
```

---

## 7. FRONTEND RENDERS RESPONSE

**File:** [frontend/src/pages/ChatPage.jsx](frontend/src/pages/ChatPage.jsx) Lines 64-72

```javascript
const applyResponse = (response) => {
  if (response.awaiting) {
    // Fraud form interrupt (handled above in section 4.4)
    setPendingForm({...});
  } else {
    // No interrupt: render as assistant message
    setPendingForm(null);
    pushAssistantTurn(response);
  }
};

const pushAssistantTurn = (response) => {
  setTurns((prev) =>
    prev.concat({
      role: 'assistant',
      body: response.reply || '',
      table: response.table || null,
      time: nowLabel(),
    }),
  );
};
```

**Rendered Output:**

**File:** [frontend/src/pages/ChatPage.jsx](frontend/src/pages/ChatPage.jsx) Lines 133-146

```javascript
{turns.map((t, i) => (
  <ChatMessage key={i} role={t.role} time={t.time}>
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      {t.body}  {/* Assistant's text reply */}
      {t.table && <DataTable columns={t.table.columns} rows={t.table.rows} />}  {/* If table exists, render it */}
    </div>
  </ChatMessage>
))}
```

**File:** [frontend/src/components/data/DataTable.jsx](frontend/src/components/data/DataTable.jsx)

```javascript
export function DataTable({ columns, rows }) {
  return (
    <table style={{...}}>
      <thead>
        <tr>
          {columns.map((col) => <th key={col}>{col}</th>)}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={i}>
            {row.map((cell, j) => <td key={j}>{cell}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

---

## 8. COMPLETE FLOW DIAGRAM

```
┌─────────────────────────────────────────────────────────────┐
│ FRONTEND: User Types Message                                │
│ ChatPage.jsx: ask() → api.sendChatMessage(token, text)      │
└───────────────────────┬─────────────────────────────────────┘
                        │ HTTP POST /chat/message
                        ▼
┌─────────────────────────────────────────────────────────────┐
│ BACKEND: Route Receives Request                             │
│ routes.py: send_message() → require_authenticated           │
│ 1. Validate JWT (stage=authenticated)                       │
│ 2. Check thread ownership (user_id matches)                 │
│ 3. Call run_chat() or resume_chat()                         │
└───────────────────────┬─────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────┐
│ LANGGRAPH: State Machine Execution                          │
│ graph.py: build_graph() → get_graph().invoke(state)         │
│                                                              │
│ Step 1: route_intent                                        │
│ ├─ Call classify_intent() (LLM)                             │
│ └─ Set state["intent"] + route to next node                │
└───────────────────────┬─────────────────────────────────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
┌──────────────────────────────────────────────────────────────┐
│ FRAUD BRANCH           DB BRANCH          PLACEHOLDER        │
│ fraud_assessment       database_query     intent             │
│                                                               │
│ Step 2: extract_fraud_fields   prepare_db_question          │
│ - LLM extracts fields          - Rephrase to English         │
│ - All-Optional model           - Preserve details            │
│                                                              │
│ Step 3: review_form            run_sql_query                │
│ - interrupt() pauses graph    - LLM writes SQL             │
│ - Frontend shows form         - Validate: SELECT-only       │
│ - User fills + submits        - Execute against SQLite      │
│ - resume_chat() continues      - Return columns + rows      │
│                                                              │
│ Step 4: validate_fraud_form    db_response                  │
│ - Check all fields present    - Detect language            │
│ - Type + range validation     - Summarize with LLM         │
│ - If invalid, loop back to    - Format table payload       │
│   review_form with errors                                   │
│                                                              │
│ Step 5: predict_fraud         (ends here)                   │
│ - Load XGBoost model                                        │
│ - Transform 23 → 40 features                               │
│ - Get probability                                           │
│ - Label: Suspicious/Not                                     │
│                                                              │
│ Step 6: fraud_response        (returns to routes.py)       │
│ - Hedged text output                                        │
│ - (ends here)                                               │
└──────────────────────────────────────────────────────────────┘
                        │
        ┌───────────────┴───────────────┐
        │                               │
        ▼ Interrupt (fraud form)        ▼ No interrupt
┌──────────────────────────────────┐  ┌──────────────────────────────────┐
│ BACKEND: Return Form to Frontend │  │ BACKEND: Return Response to      │
│ routes.py: ChatMessageResponse  │  │ Frontend                          │
│ {                               │  │ routes.py: ChatMessageResponse   │
│   thread_id,                    │  │ {                                 │
│   awaiting: {                   │  │   thread_id,                      │
│     type: "fraud_form",         │  │   reply: "...",                   │
│     fields: {...},              │  │   intent: "...",                  │
│     errors: [],                 │  │   table: {...}  (optional)        │
│     schema: {...}               │  │ }                                 │
│   }                             │  │                                   │
│ }                               │  └──────────────────────────────────┘
└───────────┬─────────────────────┘                │
            │                                      │
            ▼                                      ▼
┌──────────────────────────────────┐  ┌──────────────────────────────────┐
│ FRONTEND: Display Fraud Form     │  │ FRONTEND: Display Response        │
│ ChatPage.jsx: FraudForm          │  │ ChatPage.jsx: ChatMessage        │
│ - Show empty form fields         │  │ - Show text reply                │
│ - Show categorical options       │  │ - Show DataTable (if present)    │
│ - User fills + clicks Submit     │  │                                   │
│                                   │  │ User sees final answer           │
└───────────┬─────────────────────┘  └──────────────────────────────────┘
            │
            │ HTTP POST /chat/message
            │ { thread_id, form_response: {...} }
            │
            ▼
        ┌─ Returns to Backend ──────────┐
        │ resume_chat(form, thread_id)  │
        │ graph.invoke(Command(resume))  │
        └─ Loop back to Step 4 ─────────┘
```

---

## 9. KEY DATA FLOWS

### 9.1 Message Type: Fraud Assessment with Correction Loop

```
User Input: "Business revenue is 500k, expenses 300k, business type is Retail, region is Cairo"

Extract (LLM):
  → { Annual_Revenue: 500000, Annual_Expenses: 300000, Business_Type: "Retail", Region: "Cairo", ... (others null) }

Review (Interrupt #1):
  Form shown with fields prefilled (from extraction)
  User sees missing fields (all others are empty)
  
User Fills Form:
  Adds: Industry_Risk: "Medium", Years_in_Business: 5, etc. (all 23 fields)
  Submits

Validate:
  ✅ All 23 fields present
  ❌ Error: "Cash_Transactions_Percentage must be between 0 and 100" (user entered 150)

Review (Interrupt #2, Loop Back):
  Form shown again with:
  - All previous values prefilled
  - Error messages highlighted: "Cash_Transactions_Percentage..."
  - User corrects: enters 75

Validate:
  ✅ All fields valid
  
Predict:
  Model.predict_proba([40-feature row]) → 0.32
  Label: "Suspicious"
  
Response:
  "The model returned a result of "Suspicious"..."
  Final answer shown to user
```

### 9.2 Message Type: Database Query with Language Detection

```
User Input (Arabic): "أين الضرائب المدفوعة للعامل 1005 في 2025"
                     (English: "Show the tax payments for taxpayer 1005 in 2025")

Language Detection:
  Contains Arabic script → language = "Arabic"

Prepare Question (LLM):
  Input: "أين الضرائب المدفوعة للعامل 1005 في 2025"
  Output: "What are the tax payments for taxpayer 1005 in 2025?"

Generate & Run SQL:
  Prompt: "Write SQL to answer: What are the tax payments for taxpayer 1005 in 2025?"
  LLM: SELECT amount_paid, year FROM tax_returns WHERE taxpayer_id = 1005 AND year = 2025
  Execute: 2 rows returned
  
Summarize (LLM, in Arabic):
  Prompt: "Summarize in Arabic: [rows shown]"
  Output: "دفع دافع الضرائب 1005 مبلغ 50,000 و 12,500 في عام 2025. التفاصيل الكاملة في الجدول أدناه."
          (Taxpayer 1005 paid 50,000 and 12,500 in 2025. Full details in table below.)

Response:
  reply: "دفع دافع الضرائب 1005 مبلغ 50,000 و 12,500..."
  table: {columns: ["Amount Paid", "Year"], rows: [[50000, 2025], [12500, 2025]]}
```

### 9.3 Checkpointing & Resumption

```
Thread ID: "550e8400-e29b-41d4-a716-446655440000:abc123def456"
                 └─ User ID ──────────────────────┘  └─ Session UUID ─┘

Initial run_chat():
  graph.invoke(initial_state, config={"thread_id": "..."})
  InMemorySaver checkpoints: {thread_id: state_dict}
  Graph pauses on interrupt() → returns state + interrupt_payload

Resume resume_chat():
  graph.invoke(Command(resume=form_response), config={"thread_id": "..."})
  InMemorySaver loads: {thread_id: previous_state}
  Resumes from paused point, continues execution
  
State recovered:
  ✅ intent, extracted_features, original_query, normalized_query all preserved
  ✅ User input (form_response) resumessegmentation from exactly where it left off
```

---

## 10. PROVIDER FALLBACK & COOLDOWN

**All LLM calls route through single abstraction: `call_llm_text()` or `call_llm_structured()`**

**File:** [backend/app/chat/providers/llm.py](backend/app/chat/providers/llm.py) Lines 48-65

```python
def call_llm_text(system: str, user: str) -> str:
    """Plain text completion with provider/model fallback and cooldown."""
    last_error = None
    
    # Try candidates in order
    for provider, model in _candidates():  # Yields (provider, model) pairs
        key = f"{provider}:{model}"
        
        # Skip if cooling down after failure
        if _cooldown.is_cooling_down(key):
            continue
        
        try:
            if provider == "groq":
                return _call_groq_text(model, system, user)
            return _call_gemini_text(model, system, user)
        except Exception as exc:
            logger.warning("LLM text call failed on %s: %s", key, exc)
            _cooldown.mark(key)  # Start cooldown timer
            last_error = exc
    
    # All candidates exhausted
    raise AllProvidersExhausted(f"Every configured LLM model failed. Last error: {last_error}")
```

**Example Fallback Sequence (env vars in .env):**
```
LLM_PROVIDER_ORDER = "groq,gemini"
GROQ_LLM_MODELS = "openai/gpt-oss-20b,llama-3.3-70b-versatile"
GEMINI_LLM_MODELS = "gemini-2.0-flash"
MODEL_COOLDOWN_SECONDS = 60

Call 1: call_llm_text("intent routing", query)
  → Try: groq:openai/gpt-oss-20b ✅ Success → Return result

Call 2: call_llm_text("fraud extraction", query)
  → Try: groq:openai/gpt-oss-20b ❌ Timeout
  → Mark groq:openai/gpt-oss-20b on cooldown for 60s
  → Try: groq:llama-3.3-70b-versatile ✅ Success → Return result

Call 3 (within 60s): call_llm_text("SQL generation", query)
  → Try: groq:openai/gpt-oss-20b ⏭️ Skip (cooling down)
  → Try: groq:llama-3.3-70b-versatile ✅ Success → Return result

Call 4 (after 60s): call_llm_text("summarization", query)
  → Try: groq:openai/gpt-oss-20b ✅ Cooldown expired, retry → Success
```

---

## Summary

**Complete flow:** User message → Frontend → API → Intent classification → Branch execution (Fraud/Database/Placeholder) → LLM calls (with fallback/cooldown) → Optional interrupt (form review) → Validation/ML prediction → Response → Frontend rendering

**Key safeguards:**
- ✅ JWT stage enforcement (backend-independent)
- ✅ Thread ownership validation
- ✅ Read-only SQLite (OS-level protection)
- ✅ SQL keyword blocklist + SELECT-only validation
- ✅ All LLM calls through centralized provider abstraction
- ✅ Form validation before XGBoost prediction
- ✅ Hedged fraud response language

**State preserved across interrupts:** InMemorySaver checkpointer with `thread_id` key

