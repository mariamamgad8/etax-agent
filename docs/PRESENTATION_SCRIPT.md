# eTax Presentation Script

## Title

**eTax: Turning Tax Data into Secure, Actionable Answers**

**Suggested duration:** 12 to 15 minutes  
**Audience:** Mixed technical and non-technical audience

---

## 1. Introduction

**Speaker:**

Tax work is rarely difficult because the information does not exist. It is difficult because the information is spread across records, forms, systems, and business processes. People need answers quickly, but those answers also need to be trustworthy, private, and understandable.

That is the problem eTax is designed to address.

eTax is an AI-assisted tax platform that combines secure identity verification, conversational access to tax records, and fraud-risk assessment in one workflow. A user can sign in, verify that they are really the account owner, ask a question by text or voice, and receive either a grounded answer from their authorized records or a guided risk assessment.

The important idea is that eTax is not simply a chatbot placed in front of a database. It is a controlled assistant. It decides what kind of help the user needs, uses the right workflow, and applies authorization checks before sensitive data is returned.

For non-technical users, this means a simpler and more natural experience. For technical stakeholders, it means the convenience of AI is surrounded by explicit identity, validation, authorization, and data-access controls.

---

## 2. Very High-Level Workflow

**Speaker:**

At a high level, the journey looks like this:

1. The user creates an account or logs in with a password.
2. The user enrolls or verifies their face, with a liveness check.
3. The user enters the assistant through text or voice.
4. Speech is converted into text when necessary, and replies can be converted back into speech.
5. The agent identifies the user’s intent.
6. The request enters one of two main paths: fraud assessment or authorized database query.
7. The system validates the request, applies the appropriate controls, and produces a clear result.

The user experiences one conversation. Behind that conversation, different specialized steps work together so that every request is handled according to its purpose.

---

## 3. Signup, Login, and Face Recognition

**Speaker:**

The first layer is identity.

During signup, the user provides their account information and receives a temporary enrollment stage. They then enroll their face through the camera. The platform checks liveness before creating the face representation. In simple terms, it checks that the input is coming from a live person rather than a photograph or a screen.

During a later login, the password is only the first step. The user receives a face-verification stage, and the platform verifies the face associated with that specific account. It does not search every enrolled user and choose whoever looks closest. It checks the identity that the authenticated token already represents.

Once both stages succeed, the user receives an authenticated session and can access the assistant.

This staged design gives us two benefits. It improves the user experience by making the next step explicit, and it lets the backend enforce the same rules independently of what the frontend displays. A user cannot bypass face verification simply by navigating directly to a page.

**Technical bridge:**

Behind the scenes, the application uses short-lived JWT stages such as pending enrollment, face required, and authenticated. The API checks the required stage on every protected endpoint. Liveness gates both enrollment and verification, so a spoofed presentation is rejected before face matching continues.

---

## 4. Text, Speech-to-Text, and Text-to-Speech

**Speaker:**

Once authenticated, the user can interact naturally.

They can type a question such as, “Show me the taxes for my company,” or say it through the microphone. Speech-to-text converts the audio into the same text-based input used by the assistant. This keeps the core reasoning consistent whether the user types or speaks.

The platform uses a two-step speech recognition approach. One speech provider detects the spoken language, and another produces the detailed transcription in that language. This supports English, Arabic, and switching between them across messages.

The answer is always generated as text first. If voice replies are enabled, text-to-speech then turns that answer into audio. This separation matters: if voice generation fails, the user still receives the text answer. Voice is an interface option, not a dependency for the tax workflow.

The same principle applies to provider reliability. Language-model, speech-recognition, and speech-synthesis providers are accessed through centralized provider services, with configured fallback options. The rest of the application does not need to know which provider answered.

---

## 5. The Agent and How It Orchestrates the Conversation

**Speaker:**

The assistant is organized as an agent workflow rather than one large prompt.

A user message enters the backend and becomes the current state of a conversation. That state carries the original request, the detected language, the intent, any extracted assessment fields, database results, and the final response.

The agent then moves through a controlled graph of steps. Each step has a focused responsibility. One step routes the request. Another extracts fraud-assessment information. Another validates a form. Another runs an authorized database query. A final response step explains the result in the user’s language.

This orchestration gives us structure and traceability. We can see which path was taken and why. We can also pause a workflow when the user needs to provide more information, then resume it after the user responds.

For example, a fraud request may pause to show a form. The user can correct a value, fill in missing fields, and submit. The workflow continues from that point instead of starting over.

The agent uses language models for tasks where language understanding helps, such as classification, extraction, SQL generation within constraints, and grounded summarization. It does not let a language model decide authorization, invent missing values, or decide the final fraud label.

---

## 6. Intent Detection

**Speaker:**

Before the system chooses a business workflow, it identifies what the user is asking for.

The current intent categories include:

- A greeting
- A fraud assessment
- A database query
- A general or unsupported request
- An unclear request
- A message containing multiple intents

There is also a deterministic layer before the language model. Obvious standalone greetings can be handled immediately. A pasted group of fraud-feature fields can be recognized as an assessment request. Clear fraud-related language can also route directly to the assessment path, while stronger database-retrieval language takes priority when the user is clearly asking to retrieve records.

This combination is useful because not every message needs an AI classification call. Simple, predictable cases can be routed by explicit rules, while more ambiguous language is sent to the classifier.

The platform also determines the response language once from the user’s message. Every response-producing step uses that decision, so a translation used internally for database processing does not accidentally change the language of the answer shown to the user.

After intent detection, the two main product paths are fraud assessment and database query.

---

## 7. Path One: Fraud-Risk Assessment

**Speaker:**

Let us start with the fraud-risk workflow.

A user may type a request such as, “Assess this company,” and include some of the available financial or business information. The assistant extracts only the values the user actually provided. It does not guess missing values.

The workflow then presents a review form. The form contains 23 possible features, divided into 8 required fields and 15 optional fields. The required fields are enough to run a standard assessment. Providing all available fields enables a more comprehensive assessment.

This review step is important for both usability and trust. The user can see what the system understood, correct mistakes, and fill in missing information. If a value is invalid, the form is shown again with a clear validation message. The assessment does not silently turn an error into a default value.

After the form is valid, the system selects the model based on the exact completeness of the data:

- With the 8 required fields, it runs the standard assessment model.
- With all 23 fields, it runs the comprehensive assessment model.

It never takes the comprehensive model and fills missing fields with arbitrary medians, modes, or zeros. This avoids presenting a result that appears precise but is based on information the user never supplied.

The final result is presented in plain language, with the assessment tier and the number of supplied fields made clear. The model provides a risk indication, not an accusation or a legal conclusion. The platform communicates that distinction directly to the user.

**Technical bridge:**

The fraud branch separates extraction, validation, and prediction. Extraction is optional-field aware, validation is handled in Python, and prediction is performed by the trained model artifacts through a dedicated engine. The graph can interrupt for human review and resume with the submitted form values.

---

## 8. Path Two: Database Query

**Speaker:**

The second main path is asking questions about tax records.

A user might ask, “Show the transactions for Bright Future Academy,” or “What taxes were recorded for my companies?” The system must answer from real records, but it must also ensure that the user is allowed to see those records.

This is where the structure of the data and the security design work together.

### 8.1 Database Schema

The tax data is stored in a dedicated `tax` schema alongside the authentication data. The main tax entities are:

- Taxpayers
- Companies
- Company ownership relationships
- Transactions
- Items within transactions

A taxpayer can own more than one company, and ownership is represented per company with a share percentage. That means the same user can have majority access to one company and minority access to another.

This per-company relationship is central to the platform. Access is not reduced to one global label such as “majority user” or “minority user.” The system evaluates the company being requested.

### 8.2 Business Context and Query Planning

Before SQL is generated, the platform loads the authenticated user’s business context from the database. It identifies the taxpayer, the companies they own, their ownership shares, and their access level for each company.

The system then extracts a query plan: which companies are mentioned, which fields are requested, and which metric is needed. Company names are resolved in Python against the user’s own companies only. A language model cannot invent a company ID or an ownership level.

The requested fields and metrics come from a fixed registry. Each one has an access requirement. For example, some company identity or tax information may be available for any ownership level, while sales, item prices, quantities, and item-level information require majority ownership.

Authorization happens before SQL generation. If the company is ambiguous, the system asks for clarification. If the user has no ownership, or the requested field is not permitted for that company, the system returns a specific denial without asking another model to find a way around it.

### 8.3 Secure Views

Once a request is authorized, the system exposes only the database view or views needed for that request.

There are four secure views:

- A company-ownership view for company identity, taxpayer information, shares, and access levels
- A majority transaction view containing transaction-level sales and taxes
- A majority item view containing item prices and quantities
- A minority transaction view containing taxes, but not sales

The views are separated by data grain. Transactions and items are not mixed into one view because joining them can duplicate a transaction once for every item and cause totals to be overcounted.

The minority transaction view physically omits restricted columns. There is no minority item view at all. This is stronger than merely returning an empty value: the restricted data is not part of the accessible shape.

### 8.4 Row-Level Security

The secure views are supported by PostgreSQL row-level security, or RLS.

RLS limits the rows that the database role can see to companies connected to the authenticated user’s identity. The identity is placed into a transaction-local database setting for that request, so it does not leak into a later request that reuses the same connection.

The generated query runs as an unprivileged application role rather than the table-owning or superuser role. The database is therefore part of the enforcement boundary, not just a passive storage layer.

The design uses defense in depth:

- The application resolves ownership and authorizes the requested fields.
- The views expose only approved columns and data grains.
- RLS restricts the visible rows.
- The database role cannot bypass those protections through superuser privileges.

### 8.5 SQL Validation and Execution

Only after the plan is authorized does the platform ask a language model to produce SQL. The prompt names the approved view or views and the exact authorized company IDs.

The generated SQL is parsed as a real SQL syntax tree. The validator checks that it is a read-only query, contains no multiple statements or mutations, and references only approved views. A valid query is then executed through the unprivileged database connection with the current user identity set for that transaction.

If the query returns rows, the user receives two things:

1. A short natural-language explanation grounded in those rows.
2. The complete result set in a table.

If no rows are found, the user receives an empty-result response rather than a misleading security denial. Other outcomes, such as no ownership, a forbidden field, a forbidden company, or an ambiguous company name, receive distinct responses.

There is a limited repair path for a genuine execution error, such as a type mismatch in an otherwise permitted query. The system can make one fresh generation attempt using the database error as feedback. Security validation failures are not repaired by patching the SQL; they are rejected.

---

## 9. Returning the Result to the User

**Speaker:**

From the user’s perspective, all of this becomes one clear answer.

For a fraud assessment, the user receives the risk result, the assessment tier, and the relevant explanation. For a database question, the user receives a concise answer plus the underlying rows in a table. For a request that cannot be answered, the user receives a reason that matches the actual situation: clarification, no records, no ownership, or insufficient access.

The response is phrased in the language detected from the original message. The system does not expose internal model names, SQL details, or unnecessary architecture to the user. The complexity stays behind the interface while the controls remain available for auditing and engineering review.

---

## 10. Why This Approach Matters

**Speaker:**

The value of eTax is the combination of accessibility and control.

For users, it provides:

- A familiar conversational interface
- Text and voice interaction
- Password plus face-based identity verification
- Guided fraud assessment instead of an opaque form submission
- Answers grounded in the records the user is authorized to access
- Clear results in English or Arabic

For organizations and technical stakeholders, it provides:

- Staged authentication enforced by the backend
- Explicit workflow orchestration
- Human review before fraud prediction
- No silent imputation of missing assessment data
- Per-company ownership authorization
- Secure views, row-level security, and an unprivileged query role
- SQL parsing and validation before execution
- Fallback handling for external AI and speech providers

The platform is deliberately designed so that AI helps interpret language and coordinate work, while identity, authorization, validation, and factual results remain controlled by application logic and the database.

---

## 11. Closing

**Speaker:**

To summarize, eTax takes a complicated tax interaction and turns it into a guided, secure conversation.

The user signs up or logs in, verifies their identity with a liveness-gated face check, and communicates by text or voice. The agent identifies the request and sends it through the right path. Fraud assessment becomes a reviewed and validated prediction. Database questions become authorized, validated, and grounded answers from the user’s own records.

The result is not just an AI chatbot. It is an end-to-end tax platform where convenience is connected to identity, intelligence is connected to workflow, and access to data is connected to enforceable security.

**Final line:**

> eTax makes tax information easier to ask for, easier to understand, and safer to access.

---

## Optional Live Demonstration Sequence

1. Open the eTax landing page and show the product entry point.
2. Demonstrate signup or login and the face-verification stage.
3. Ask a database question in English and show the answer plus result table.
4. Ask a database question for a company or field the user is not authorized to access, and show the specific denial.
5. Ask for a fraud assessment using a few feature values.
6. Show the prefilled review form, edit a value, and submit it.
7. Show the standard or comprehensive assessment result.
8. Toggle voice input or voice replies to demonstrate the speech layer.
ed to access, and show the specific denial.
5. Ask for a fraud assessment using a few feature values.
6. Show the prefilled review form, edit a value, and submit it.
7. Show the standard or comprehensive assessment result.
8. Toggle voice input or voice replies to demonstrate the speech layer.
