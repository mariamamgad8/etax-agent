\# TAYA — AI-Powered Tax Risk Assessment Voice Assistant



<p align="center">



&#x20; <strong>Voice-first conversational AI system for intelligent tax-risk data collection and assessment.</strong>



</p>



<p align="center">



&#x20; Python • FastAPI • AsyncIO • LLM • STT • TTS • Provider Architecture



</p>



\---



\## Table of Contents



\- \[Overview](#overview)

\- \[Key Capabilities](#key-capabilities)

\- \[System Architecture](#system-architecture)

\- \[End-to-End Pipeline](#end-to-end-pipeline)

\- \[Project Structure](#project-structure)

\- \[Frontend](#frontend)

\- \[Backend](#backend)

\- \[Speech-to-Text](#speech-to-text)

\- \[Taya Conversation Engine](#taya-conversation-engine)

\- \[Conversation Controller](#conversation-controller)

\- \[LLM Layer](#llm-layer)

\- \[Prompt Engineering](#prompt-engineering)

\- \[State Management](#state-management)

\- \[Feature Extraction](#feature-extraction)

\- \[Feature Engineering](#feature-engineering)

\- \[Text-to-Speech](#text-to-speech)

\- \[Provider Architecture](#provider-architecture)

\- \[Fallback Architecture](#fallback-architecture)

\- \[Data Schema](#data-schema)

\- \[Supported Egyptian Governorates](#supported-egyptian-governorates)

\- \[Conversation Flow](#conversation-flow)

\- \[API](#api)

\- \[Example Conversation](#example-conversation)

\- \[Example Structured Data](#example-structured-data)

\- \[Performance](#performance)

\- \[Testing](#testing)

\- \[Installation](#installation)

\- \[Environment Variables](#environment-variables)

\- \[Running the Application](#running-the-application)

\- \[Security Considerations](#security-considerations)

\- \[Current Limitations](#current-limitations)

\- \[Future Improvements](#future-improvements)

\- \[Development Workflow](#development-workflow)



\---



\# Overview



TAYA is an AI-powered conversational voice assistant designed to collect structured business and tax-related information through a natural voice conversation.



Instead of presenting users with a traditional form containing multiple fields, TAYA guides the user through a conversational workflow.



The system combines:



\- Speech-to-Text (STT)

\- Large Language Models (LLMs)

\- Structured information extraction

\- Conversation state management

\- Feature engineering

\- Text-to-Speech (TTS)

\- Provider abstraction

\- Fallback mechanisms

\- Session-based conversation management



The final objective is to transform an unstructured voice conversation into a structured feature vector that can be consumed by an existing machine-learning tax-risk assessment pipeline.



\---



\# Key Capabilities



\## Voice-first interaction



Users communicate with TAYA using their microphone rather than manually completing a long form.



```text

User Voice

&#x20;   ↓

Speech-to-Text

&#x20;   ↓

Transcript

&#x20;   ↓

Taya

&#x20;   ↓

Structured Information

&#x20;   ↓

Next Question

&#x20;   ↓

Text-to-Speech

&#x20;   ↓

User Voice

```



\## Multilingual conversation



TAYA supports both:



\- Arabic

\- English



The conversation begins by asking the user which language they prefer.



Example:



> \*\*Taya:\*\* أهلاً بيك 👋 أنا Taya، مساعدك الذكي. تحب نكمل بالعربي ولا English؟



The user can respond:



> عربي



TAYA then continues the conversation in Arabic.



\---



\# System Architecture



The application follows a layered and provider-oriented architecture.



```text

&#x20;                        ┌─────────────────────┐

&#x20;                        │      Frontend       │

&#x20;                        │  Browser / Mic UI   │

&#x20;                        └──────────┬──────────┘

&#x20;                                   │

&#x20;                                   │ Voice

&#x20;                                   ▼

&#x20;                        ┌─────────────────────┐

&#x20;                        │      FastAPI        │

&#x20;                        │       API Layer     │

&#x20;                        └──────────┬──────────┘

&#x20;                                   │

&#x20;                                   ▼

&#x20;                        ┌─────────────────────┐

&#x20;                        │    Speech Service   │

&#x20;                        └──────────┬──────────┘

&#x20;                                   │

&#x20;                                   ▼

&#x20;                        ┌─────────────────────┐

&#x20;                        │        STT          │

&#x20;                        │ Speech-to-Text      │

&#x20;                        └──────────┬──────────┘

&#x20;                                   │

&#x20;                                   │ Transcript

&#x20;                                   ▼

&#x20;                   ┌───────────────────────────────┐

&#x20;                   │       Taya Service            │

&#x20;                   │                               │

&#x20;                   │ Conversation Controller       │

&#x20;                   │ LLM Extraction               │

&#x20;                   │ State Management              │

&#x20;                   │ Question Selection            │

&#x20;                   └───────────────┬───────────────┘

&#x20;                                   │

&#x20;                                   ▼

&#x20;                        ┌─────────────────────┐

&#x20;                        │ Structured Features │

&#x20;                        └──────────┬──────────┘

&#x20;                                   │

&#x20;                                   ▼

&#x20;                        ┌─────────────────────┐

&#x20;                        │ Feature Engineering │

&#x20;                        └──────────┬──────────┘

&#x20;                                   │

&#x20;                                   ▼

&#x20;                        ┌─────────────────────┐

&#x20;                        │ Existing ML Model  │

&#x20;                        │ Tax Risk Assessment│

&#x20;                        └─────────────────────┘



&#x20;                                   │

&#x20;                                   │ Taya Response

&#x20;                                   ▼



&#x20;                        ┌─────────────────────┐

&#x20;                        │        TTS          │

&#x20;                        │ Text-to-Speech      │

&#x20;                        └──────────┬──────────┘

&#x20;                                   │

&#x20;                                   ▼

&#x20;                        ┌─────────────────────┐

&#x20;                        │      Frontend       │

&#x20;                        │   Audio Playback    │

&#x20;                        └─────────────────────┘

```



\---



\# End-to-End Pipeline



A complete request follows this pipeline:



```text

1\. User speaks

&#x20;      ↓

2\. Browser captures audio

&#x20;      ↓

3\. Audio sent to backend

&#x20;      ↓

4\. STT provider converts audio → text

&#x20;      ↓

5\. Transcript passed to Taya

&#x20;      ↓

6\. Conversation Controller determines current state

&#x20;      ↓

7\. LLM extracts structured information

&#x20;      ↓

8\. State Service updates collected fields

&#x20;      ↓

9\. Missing fields are calculated

&#x20;      ↓

10\. Taya selects the next question

&#x20;      ↓

11\. Response converted to speech

&#x20;      ↓

12\. Audio returned to frontend

&#x20;      ↓

13\. User hears Taya's response

```



\---



\# Project Structure



```text

speech-api/

│

├── app/

│   │

│   ├── main.py

│   │

│   ├── api/

│   │   └── routes.py

│   │

│   ├── core/

│   │   ├── config.py

│   │   └── enums.py

│   │

│   ├── exceptions/

│   │   └── speech\_exception.py

│   │

│   ├── frontend/

│   │   └── index.html

│   │

│   ├── providers/

│   │   │

│   │   ├── base\_provider.py

│   │   ├── cloudflare\_provider.py

│   │   ├── cohere\_provider.py

│   │   ├── groq\_provider.py

│   │   ├── provider\_factory.py

│   │   └── provider\_manager.py

│   │

│   │   └── tts/

│   │       ├── elevenlabs\_tts\_provider.py

│   │       ├── fish\_tts\_provider.py

│   │       ├── gemini\_tts\_provider.py

│   │       ├── fallback\_tts\_provider.py

│   │       └── tts\_router.py

│   │

│   ├── services/

│   │   ├── conversation\_service.py

│   │   ├── fallback\_service.py

│   │   ├── llm\_service.py

│   │   └── speech\_service.py

│   │

│   └── taya/

│       ├── \_\_init\_\_.py

│       ├── conversation\_controller.py

│       ├── feature\_engineering\_service.py

│       ├── question\_bank.json

│       ├── taya\_service.py

│       ├── taya\_state\_service.py

│       │

│       ├── prompts/

│       │   ├── taya\_extraction\_prompt.txt

│       │   └── taya\_system\_prompt.txt

│       │

│       └── schemas/

│           └── taya\_feature\_schema.json

│

├── frontend/

│   └── index.html

│

├── playground/

│

├── tests/

│

├── requirements.txt

└── README.md

```



\---



\# Frontend



The frontend provides the user-facing voice interface.



Its primary responsibilities are:



1\. Access the microphone.

2\. Capture user audio.

3\. Send audio to the backend.

4\. Receive TAYA's response.

5\. Play the generated audio.

6\. Maintain the current session identifier.



The frontend communicates with the FastAPI backend through HTTP endpoints.



Conceptually:



```text

Browser

&#x20;  │

&#x20;  ├── Microphone

&#x20;  │

&#x20;  ├── Record Audio

&#x20;  │

&#x20;  └── POST /chat

&#x20;         │

&#x20;         ▼

&#x20;      FastAPI

&#x20;         │

&#x20;         ▼

&#x20;      TAYA

&#x20;         │

&#x20;         ▼

&#x20;      Audio

&#x20;         │

&#x20;         ▼

&#x20;      Browser

```



\---



\# Backend



The backend is implemented using Python and FastAPI.



FastAPI is responsible for:



\- HTTP routing

\- Request handling

\- Session-based conversations

\- Audio processing orchestration

\- TAYA integration

\- TTS response delivery



The main application entry point is:



```text

app/main.py

```



API routes are located in:



```text

app/api/routes.py

```



\---



\# Speech-to-Text



Speech-to-Text converts the user's voice into a text transcript.



```text

Audio

&#x20; ↓

STT Provider

&#x20; ↓

Transcript

```



The project uses a provider-based architecture for speech processing.



Current STT-related providers include integrations represented by:



```text

Cloudflare

Cohere

Groq

```



The provider abstraction makes it possible to switch between services without changing the Taya conversation logic.



\---



\# STT Architecture



```text

&#x20;               ┌──────────────────┐

&#x20;               │   Speech Service │

&#x20;               └────────┬─────────┘

&#x20;                        │

&#x20;                        ▼

&#x20;               ┌──────────────────┐

&#x20;               │ Provider Manager │

&#x20;               └────────┬─────────┘

&#x20;                        │

&#x20;           ┌────────────┼────────────┐

&#x20;           ▼            ▼            ▼

&#x20;      Cloudflare      Cohere       Groq

&#x20;           │            │            │

&#x20;           └────────────┼────────────┘

&#x20;                        ▼

&#x20;                    Transcript

```



This separation allows the STT implementation to evolve independently from the conversation engine.



\---



\# Taya Conversation Engine



Taya is the central conversational intelligence layer.



The main Taya components are:



```text

TayaService

&#x20;   │

&#x20;   ├── ConversationController

&#x20;   │

&#x20;   ├── StateService

&#x20;   │

&#x20;   ├── FeatureEngineeringService

&#x20;   │

&#x20;   ├── QuestionBank

&#x20;   │

&#x20;   └── LLM / Extraction Layer

```



\---



\# Conversation Controller



The `ConversationController` is responsible for controlling the conversational state.



It determines:



\- What stage the conversation is currently in.

\- Which information has already been collected.

\- Which fields are still missing.

\- Which question should be asked next.

\- Whether the conversation is complete.

\- Whether the user needs to provide clarification.



The controller prevents TAYA from behaving like a simple chatbot that generates unrelated questions.



Instead, the conversation is driven by the required feature schema.



Conceptually:



```text

&#x20;                   User Message

&#x20;                        │

&#x20;                        ▼

&#x20;             ┌─────────────────────┐

&#x20;             │ Conversation         │

&#x20;             │ Controller           │

&#x20;             └──────────┬──────────┘

&#x20;                        │

&#x20;             ┌──────────┴──────────┐

&#x20;             │                     │

&#x20;             ▼                     ▼

&#x20;      Extract Information     Read State

&#x20;             │                     │

&#x20;             └──────────┬──────────┘

&#x20;                        ▼

&#x20;                Missing Fields

&#x20;                        │

&#x20;                        ▼

&#x20;                Next Question

```



\---



\# Conversation Stages



The conversation begins with language selection.



```text

START

&#x20; ↓

Greeting

&#x20; ↓

Language Selection

&#x20; ↓

Business Information

&#x20; ↓

Financial Information

&#x20; ↓

Tax Information

&#x20; ↓

Compliance Information

&#x20; ↓

Transaction Information

&#x20; ↓

Document / Invoice Information

&#x20; ↓

Feature Validation

&#x20; ↓

Model Readiness

&#x20; ↓

END

```



\---



\# Language Selection



Taya initially asks the user to select a language.



Example:



> \*\*Taya:\*\* أهلاً بيك 👋 أنا Taya، مساعدك الذكي. تحب نكمل بالعربي ولا English؟



If the user responds:



> عربي



Taya continues in Arabic.



If the user selects English, the conversation continues in English.



\---



\# LLM Layer



The LLM is used as part of the conversational intelligence and structured information extraction pipeline.



The LLM is not responsible for storing the application's state.



Instead, the architecture separates:



```text

LLM

&#x20;↓

Information Extraction

&#x20;↓

Validated Structured Data

&#x20;↓

State Service

```



This separation is important because conversational generation and deterministic state management are different responsibilities.



\---



\# Prompt Engineering



TAYA uses dedicated prompt files rather than embedding large prompts directly into application logic.



Current prompt files:



```text

app/taya/prompts/

│

├── taya\_system\_prompt.txt

└── taya\_extraction\_prompt.txt

```



\## System Prompt



The system prompt defines TAYA's overall conversational behavior.



It controls:



\- Assistant identity

\- Conversation behavior

\- Language behavior

\- Questioning style

\- Response constraints

\- Information collection behavior



\## Extraction Prompt



The extraction prompt focuses on converting natural language into structured feature values.



Conceptually:



```text

Natural Language

&#x20;      ↓

Extraction Prompt

&#x20;      ↓

LLM

&#x20;      ↓

Structured JSON

&#x20;      ↓

Schema Validation

&#x20;      ↓

State Update

```



\---



\# Structured Information Extraction



The user does not need to answer questions using exact field names.



For example, the user can say:



> أنا عندي مطعم في القاهرة بقاله 8 سنين وعندي 15 موظف والإيرادات حوالي 2 مليون جنيه.



The system can extract:



```json

{

&#x20; "Business\_Type": "Restaurant",

&#x20; "Region": "Cairo",

&#x20; "Years\_in\_Business": 8,

&#x20; "Employee\_Count": 15,

&#x20; "Annual\_Revenue": 2000000

}

```



This is one of the core advantages of the conversational architecture.



\---



\# State Management



Conversation state is maintained per session.



The session identifier allows TAYA to distinguish between different users/conversations.



Conceptually:



```text

session\_id

&#x20;   │

&#x20;   ▼

Taya State

&#x20;   │

&#x20;   ├── Collected Features

&#x20;   ├── Missing Features

&#x20;   ├── Conversation Progress

&#x20;   └── Current Context

```



The state service is implemented in:



```text

app/taya/taya\_state\_service.py

```



\---



\# Feature Schema



The expected TAYA feature set contains 16 fields:



```text

Business\_Type

Region

Years\_in\_Business

Employee\_Count

Annual\_Revenue

Annual\_Expenses

Taxable\_Income

Declared\_Tax

VAT\_Collected

VAT\_Paid

Previous\_Audits

Previous\_Violations

Late\_Payments

Cash\_Transactions\_Percentage

Missing\_Documents

Invoice\_Mismatch

```



The schema is defined in:



```text

app/taya/schemas/taya\_feature\_schema.json

```



\---



\# Feature Categories



\## Business Information



```text

Business\_Type

Region

Years\_in\_Business

Employee\_Count

```



\## Financial Information



```text

Annual\_Revenue

Annual\_Expenses

Taxable\_Income

Declared\_Tax

```



\## VAT Information



```text

VAT\_Collected

VAT\_Paid

```



\## Compliance History



```text

Previous\_Audits

Previous\_Violations

Late\_Payments

```



\## Transaction \& Documentation



```text

Cash\_Transactions\_Percentage

Missing\_Documents

Invoice\_Mismatch

```



\---



\# Question Bank



The question bank is stored separately from the core controller:



```text

app/taya/question\_bank.json

```



This allows questions to be modified without rewriting the conversation engine.



Example conversational questions:



> إيه نوع النشاط التجاري بتاعك؟



> في أي محافظة موجود النشاط التجاري بتاعك؟



> بقالك كام سنة شغال في النشاط ده تقريبًا؟



> عندك كام موظف تقريبًا؟



> كم تبلغ إيراداتك السنوية تقريبًا؟



> كم تبلغ مصروفاتك السنوية تقريبًا؟



The actual question selection is driven by the missing feature state.



\---



\# Feature Engineering



Once all required conversational features have been collected, the system passes them to:



```text

feature\_engineering\_service.py

```



The feature engineering layer is responsible for preparing the collected information for the downstream ML model.



The pipeline is:



```text

Conversation Data

&#x20;      ↓

Collected Features

&#x20;      ↓

Feature Engineering

&#x20;      ↓

Model Features

&#x20;      ↓

Validation

&#x20;      ↓

ML Model

```



The service verifies whether the final feature representation is complete and ready for the existing model.



\---



\# Model Readiness



TAYA does not immediately send partially collected information to the ML model.



Instead:



```text

Collected Data

&#x20;     ↓

Feature Engineering

&#x20;     ↓

Missing Feature Check

&#x20;     ↓

&#x20;     ├── Missing → Continue Conversation

&#x20;     │

&#x20;     └── Complete → Model Ready

```



This prevents incomplete feature vectors from being passed to the assessment model.



\---



\# Text-to-Speech



After TAYA generates a response, the response is converted back into audio.



```text

Taya Response

&#x20;     ↓

TTS Router

&#x20;     ↓

Selected Provider

&#x20;     ↓

Audio

&#x20;     ↓

Frontend

```



The project contains integrations for:



```text

ElevenLabs

Fish Audio

Gemini

Fallback TTS

```



\---



\# TTS Router



The TTS router provides a single interface for text-to-speech generation.



Instead of the rest of the application knowing how each TTS provider works:



```text

Taya

&#x20;↓

TTS Router

&#x20;↓

Provider

&#x20;↓

Audio

```



This reduces coupling between the conversation engine and external TTS services.



\---



\# Provider Architecture



The project uses an abstraction-based provider architecture.



Core components include:



```text

base\_provider.py

provider\_factory.py

provider\_manager.py

```



The architecture allows external AI providers to be replaced or extended without rewriting the business logic.



Conceptually:



```text

&#x20;                   Application

&#x20;                       │

&#x20;                       ▼

&#x20;                Provider Manager

&#x20;                       │

&#x20;                       ▼

&#x20;                Provider Interface

&#x20;                       │

&#x20;         ┌─────────────┼─────────────┐

&#x20;         ▼             ▼             ▼

&#x20;     Provider A    Provider B    Provider C

```



\---



\# Why Provider Abstraction?



External AI providers can differ in:



\- API behavior

\- latency

\- availability

\- pricing

\- supported languages

\- audio quality

\- rate limits

\- failure modes



A provider abstraction prevents these differences from leaking into the rest of the application.



\---



\# Fallback Architecture



The system contains fallback mechanisms for service failures.



Conceptually:



```text

Primary Provider

&#x20;      │

&#x20;      │ Success

&#x20;      ▼

&#x20;   Response



&#x20;      │

&#x20;      │ Failure

&#x20;      ▼

Fallback Provider

&#x20;      │

&#x20;      ▼

&#x20;   Response

```



This improves system resilience and reduces dependency on a single external AI provider.



\---



\# Data Schema



The TAYA feature schema is represented as structured JSON.



Example:



```json

{

&#x20; "Business\_Type": "Restaurant",

&#x20; "Region": "Cairo",

&#x20; "Years\_in\_Business": 8,

&#x20; "Employee\_Count": 15,

&#x20; "Annual\_Revenue": 2000000,

&#x20; "Annual\_Expenses": 900000,

&#x20; "Taxable\_Income": 1000000,

&#x20; "Declared\_Tax": 200000,

&#x20; "VAT\_Collected": 150000,

&#x20; "VAT\_Paid": 100000,

&#x20; "Previous\_Audits": 2,

&#x20; "Previous\_Violations": 0,

&#x20; "Late\_Payments": 3,

&#x20; "Cash\_Transactions\_Percentage": 60,

&#x20; "Missing\_Documents": 2,

&#x20; "Invoice\_Mismatch": 0

}

```



\---



\# Supported Egyptian Governorates



TAYA supports Egyptian governorate selection through the configured region validation.



The supported governorates are:



```text

Cairo

Giza

Alexandria

Qalyubia

Port Said

Suez

Damietta

Dakahlia

Sharqia

Gharbia

Kafr El Sheikh

Beheira

Monufia

Ismailia

Gharbia

Fayoum

Beni Suef

Minya

Asyut

Sohag

Qena

Luxor

Aswan

Red Sea

New Valley

Matrouh

North Sinai

South Sinai

```



Region recognition is intended to handle natural conversational input rather than requiring users to provide an exact schema value.



\---



\# Conversation Flow



A typical conversation looks like:



```text

START

&#x20; │

&#x20; ▼

Greeting

&#x20; │

&#x20; ▼

Language Selection

&#x20; │

&#x20; ▼

Business Type

&#x20; │

&#x20; ▼

Region

&#x20; │

&#x20; ▼

Years in Business

&#x20; │

&#x20; ▼

Employee Count

&#x20; │

&#x20; ▼

Annual Revenue

&#x20; │

&#x20; ▼

Annual Expenses

&#x20; │

&#x20; ▼

Taxable Income

&#x20; │

&#x20; ▼

Declared Tax

&#x20; │

&#x20; ▼

VAT Collected

&#x20; │

&#x20; ▼

VAT Paid

&#x20; │

&#x20; ▼

Previous Audits

&#x20; │

&#x20; ▼

Previous Violations

&#x20; │

&#x20; ▼

Late Payments

&#x20; │

&#x20; ▼

Cash Transactions

&#x20; │

&#x20; ▼

Missing Documents

&#x20; │

&#x20; ▼

Invoice Mismatch

&#x20; │

&#x20; ▼

Feature Validation

&#x20; │

&#x20; ▼

ML Model Ready

```



The controller can also extract multiple fields from a single user response.



For example:



> عندي مطعم في القاهرة بقاله 8 سنين وعندي 15 موظف والإيرادات حوالي 2 مليون جنيه.



can satisfy multiple fields at once.



The system should therefore ask only for information that remains missing.



\---



\# Example Conversation



\### Greeting



> \*\*Taya:\*\* أهلاً بيك 👋 أنا Taya، مساعدك الذكي. تحب نكمل بالعربي ولا English؟



\### Language



> \*\*User:\*\* عربي



> \*\*Taya:\*\* تمام 👌 هنكمل بالعربي. إيه نوع النشاط التجاري بتاعك؟



\### Business Information



> \*\*User:\*\* أنا عندي مطعم في القاهرة بقاله 8 سنين وعندي 15 موظف والإيرادات السنوية حوالي 2 مليون جنيه.



The system can extract:



```json

{

&#x20; "Business\_Type": "Restaurant",

&#x20; "Region": "Cairo",

&#x20; "Years\_in\_Business": 8,

&#x20; "Employee\_Count": 15,

&#x20; "Annual\_Revenue": 2000000

}

```



TAYA then moves directly to the next missing field.



> \*\*Taya:\*\* كم تبلغ مصروفاتك السنوية تقريبًا؟



\---



\# Multi-Field Extraction



TAYA is designed to accept multiple pieces of information in one response.



Example:



> عندي مطعم في القاهرة بقاله 8 سنين وعندي 15 موظف والإيرادات السنوية حوالي 2 مليون جنيه والمصاريف 900 ألف.



Expected extraction:



```json

{

&#x20; "Business\_Type": "Restaurant",

&#x20; "Region": "Cairo",

&#x20; "Years\_in\_Business": 8,

&#x20; "Employee\_Count": 15,

&#x20; "Annual\_Revenue": 2000000,

&#x20; "Annual\_Expenses": 900000

}

```



The conversation engine should then skip already collected fields.



\---



\# API



The application exposes the conversational pipeline through FastAPI.



The primary endpoint is:



```text

POST /chat

```



The endpoint accepts a session identifier:



```text

/chat?session\_id=<SESSION\_ID>

```



The request contains user audio.



The response contains TAYA's generated response and the corresponding audio information.



\---



\# API Flow



```text

POST /chat

&#x20;     │

&#x20;     ▼

Receive Audio

&#x20;     │

&#x20;     ▼

STT

&#x20;     │

&#x20;     ▼

Transcript

&#x20;     │

&#x20;     ▼

Taya Service

&#x20;     │

&#x20;     ▼

State Update

&#x20;     │

&#x20;     ▼

Next Response

&#x20;     │

&#x20;     ▼

TTS

&#x20;     │

&#x20;     ▼

Audio Response

```



\---



\# Audio Endpoint



Generated audio is served through the backend audio route.



Example:



```text

GET /audio/<audio\_file>

```



The frontend uses the generated audio resource for playback.



\---



\# Session Management



Every conversation is associated with a unique session ID.



Example:



```text

87335894-ab56-472b-969c-18d738e40e3a

```



The session identifier allows TAYA to maintain conversation state across multiple requests.



\---



\# Performance



The application logs timing information for each voice interaction.



Example:



```text

==================================================

TAYA VOICE PIPELINE

==================================================

STT:       1.740s

TAYA:      0.687s

TTS:       0.977s

TOTAL:     3.403s

\--------------------------------------------------

Transcript:  كفر الشيخ

Response:   بقالك كام سنة شغال في النشاط ده تقريبًا؟

Audio:      <generated-audio-file>.mp3

==================================================

```



The system measures:



```text

STT latency

TAYA latency

TTS latency

Total latency

```



This makes it possible to identify performance bottlenecks across the voice pipeline.



\---



\# Performance Optimization



The architecture makes it possible to independently optimize:



```text

STT

&#x20;↓

LLM

&#x20;↓

TTS

```



For example:



```text

Total Latency

=

STT Latency

\+

Taya/LLM Latency

\+

TTS Latency

```



This separation allows provider benchmarking and targeted optimization.



\---



\# Testing



The repository contains multiple provider and pipeline tests.



Examples include:



```text

test\_cloudflare.py

test\_cohere.py

test\_conversation.py

test\_elevenlabs\_auth.py

test\_elevenlabs\_connection.py

test\_elevenlabs\_tts.py

test\_factory.py

test\_fallback.py

test\_fallback\_failure.py

test\_fish\_tts.py

test\_gemini\_provider.py

test\_llm.py

test\_provider.py

test\_service.py

test\_stt\_benchmark.py

test\_stt\_evaluation.py

test\_taya.py

test\_tts\_fallback.py

test\_tts\_latency.py

test\_tts\_long\_benchmark.py

```



The tests cover multiple layers of the system:



```text

Provider Tests

&#x20;     ↓

Service Tests

&#x20;     ↓

Taya Tests

&#x20;     ↓

STT Evaluation

&#x20;     ↓

TTS Evaluation

&#x20;     ↓

Latency Benchmarks

```



\---



\# Taya Test



The conversational engine can be tested independently from the voice pipeline.



The test script is:



```text

test\_taya.py

```



This allows developers to test:



\- Feature extraction

\- Missing field detection

\- State management

\- Question generation

\- Conversation completion

\- Feature engineering



without requiring microphone input.



\---



\# Voice Pipeline Testing



The complete pipeline can be tested through the FastAPI application.



```text

Microphone

&#x20;   ↓

STT

&#x20;   ↓

Taya

&#x20;   ↓

TTS

&#x20;   ↓

Audio

```



This provides an end-to-end integration test of the actual user experience.



\---



\# Installation



\## 1. Clone the Repository



```bash

git clone <repository-url>

cd speech-api

```



\## 2. Create a Virtual Environment



Windows:



```bash

python -m venv .venv

```



\## 3. Activate the Environment



Command Prompt:



```cmd

.venv\\Scripts\\activate

```



PowerShell:



```powershell

.venv\\Scripts\\Activate.ps1

```



\## 4. Install Dependencies



```bash

pip install -r requirements.txt

```



\---



\# Environment Variables



Sensitive credentials must not be committed to Git.



Create a local:



```text

.env

```



file.



The required environment variables depend on the configured providers.



Typical categories include:



```text

LLM API credentials

STT API credentials

TTS API credentials

Provider configuration

Application configuration

```



Never commit:



```text

.env

```



to the repository.



The project uses `.gitignore` to prevent sensitive and generated files from being tracked.



\---



\# Running the Application



Start the FastAPI server using:



```bash

python -m uvicorn app.main:app --reload

```



The application will normally be available at:



```text

http://127.0.0.1:8000

```



The frontend can then be accessed through the application.



\---



\# Development Mode



When running with:



```bash

\--reload

```



Uvicorn automatically reloads the application when source files change.



Example:



```bash

python -m uvicorn app.main:app --reload

```



\---



\# Security Considerations



The application processes potentially sensitive business and tax-related information.



Important security requirements include:



\- Never commit API keys.

\- Never commit `.env`.

\- Avoid logging sensitive user data in production.

\- Use HTTPS in production.

\- Validate uploaded audio.

\- Validate structured model outputs.

\- Apply authentication and authorization before production deployment.

\- Apply rate limiting to public endpoints.

\- Use secure session management.

\- Restrict access to generated audio.

\- Avoid exposing internal provider errors to end users.



\---



\# Error Handling



The project includes dedicated exception handling:



```text

app/exceptions/speech\_exception.py

```



Provider failures should be isolated from the conversational layer whenever possible.



The architecture aims to distinguish between:



```text

User Input Errors

Provider Errors

STT Errors

LLM Errors

TTS Errors

Validation Errors

Application Errors

```



This allows the system to provide graceful fallback behavior instead of terminating the conversation.



\---



\# Fallback Strategy



The system is designed around resilience.



For example:



```text

&#x20;            Primary Provider

&#x20;                   │

&#x20;             ┌─────┴─────┐

&#x20;             │           │

&#x20;          Success      Failure

&#x20;             │           │

&#x20;             ▼           ▼

&#x20;          Response    Fallback

&#x20;                         │

&#x20;                         ▼

&#x20;                      Response

```



The same philosophy is applied to the TTS layer.



\---



\# Models and AI Components



The project is intentionally provider-agnostic.



The AI stack consists of three major components:



\## Speech Recognition



Speech-to-Text providers are integrated through the provider architecture.



Current provider integrations include:



```text

Cloudflare

Cohere

Groq

```



\## Language Model



The LLM layer is responsible for conversational processing and structured feature extraction.



The implementation is abstracted through:



```text

app/services/llm\_service.py

```



The exact model/provider configuration is controlled through the application configuration rather than hard-coded into the Taya state-management layer.



\## Speech Synthesis



TTS integrations include:



```text

ElevenLabs

Fish Audio

Gemini

Fallback TTS

```



\---



\# Why This Architecture?



A monolithic implementation could look like:



```text

Frontend

&#x20;  ↓

One AI API

&#x20;  ↓

Everything

```



TAYA instead uses:



```text

Frontend

&#x20;  ↓

API

&#x20;  ↓

Speech Service

&#x20;  ↓

Provider Layer

&#x20;  ↓

Taya Service

&#x20;  ↓

Conversation Controller

&#x20;  ↓

State Service

&#x20;  ↓

Feature Engineering

&#x20;  ↓

ML Model

```



This provides:



\### Modularity



Each component has a clear responsibility.



\### Replaceability



AI providers can be changed independently.



\### Testability



Services and providers can be tested separately.



\### Scalability



Additional providers and capabilities can be introduced without rewriting the entire system.



\### Reliability



Fallback mechanisms reduce single-provider dependency.



\---



\# Separation of Responsibilities



| Component | Responsibility |

|---|---|

| Frontend | Audio capture and playback |

| API | HTTP communication |

| Speech Service | Speech processing orchestration |

| STT Provider | Audio → Text |

| Taya Service | Conversational orchestration |

| Conversation Controller | Conversation state/flow |

| LLM Service | LLM communication |

| Extraction Prompt | Structured information extraction |

| State Service | Persistent session state |

| Question Bank | Conversational questions |

| Feature Engineering | Model-ready feature construction |

| TTS Router | TTS provider routing |

| TTS Provider | Text → Audio |

| Fallback Service | Failure recovery |



\---



\# Current Architecture



```text

┌──────────────────────────────────────────────────────────────┐

│                         FRONTEND                             │

│                                                              │

│                 Browser + Microphone + Audio                 │

└────────────────────────────┬─────────────────────────────────┘

&#x20;                            │

&#x20;                            ▼

┌──────────────────────────────────────────────────────────────┐

│                          FASTAPI                             │

│                                                              │

│                         /chat                                │

└────────────────────────────┬─────────────────────────────────┘

&#x20;                            │

&#x20;                            ▼

┌──────────────────────────────────────────────────────────────┐

│                       SPEECH SERVICE                         │

└────────────────────────────┬─────────────────────────────────┘

&#x20;                            │

&#x20;                            ▼

┌──────────────────────────────────────────────────────────────┐

│                         STT LAYER                            │

│                                                              │

│              Cloudflare / Cohere / Groq                      │

└────────────────────────────┬─────────────────────────────────┘

&#x20;                            │

&#x20;                            │ Transcript

&#x20;                            ▼

┌──────────────────────────────────────────────────────────────┐

│                       TAYA SERVICE                            │

│                                                              │

│  ┌────────────────────────────────────────────────────────┐  │

│  │ Conversation Controller                                │  │

│  └──────────────────────┬─────────────────────────────────┘  │

│                         │                                    │

│  ┌──────────────────────▼─────────────────────────────────┐  │

│  │ LLM / Information Extraction                           │  │

│  └──────────────────────┬─────────────────────────────────┘  │

│                         │                                    │

│  ┌──────────────────────▼─────────────────────────────────┐  │

│  │ State Service                                          │  │

│  └──────────────────────┬─────────────────────────────────┘  │

│                         │                                    │

│  ┌──────────────────────▼─────────────────────────────────┐  │

│  │ Missing Fields / Question Bank                         │  │

│  └──────────────────────┬─────────────────────────────────┘  │

└─────────────────────────┼────────────────────────────────────┘

&#x20;                         │

&#x20;                         ▼

┌──────────────────────────────────────────────────────────────┐

│                    FEATURE ENGINEERING                       │

│                                                              │

│                  Model-Ready Features                         │

└────────────────────────────┬─────────────────────────────────┘

&#x20;                            │

&#x20;                            ▼

┌──────────────────────────────────────────────────────────────┐

│                       ML MODEL                               │

│                  Tax Risk Assessment                         │

└──────────────────────────────────────────────────────────────┘



&#x20;                            │

&#x20;                            │ Taya Response

&#x20;                            ▼

┌──────────────────────────────────────────────────────────────┐

│                          TTS                                 │

│                                                              │

│       ElevenLabs / Fish Audio / Gemini / Fallback             │

└────────────────────────────┬─────────────────────────────────┘

&#x20;                            │

&#x20;                            ▼

&#x20;                       FRONTEND AUDIO

```



\---



\# Current Limitations



The current implementation is primarily focused on the conversational voice pipeline.



Areas that require additional production hardening include:



\- Persistent production-grade session storage.

\- Authentication and authorization.

\- Production database integration.

\- Secure audio storage.

\- Comprehensive observability.

\- Distributed deployment.

\- Production-grade rate limiting.

\- Advanced multilingual normalization.

\- More robust handling of ambiguous numerical responses.

\- Improved semantic validation of extracted values.



\---



\# Future Improvements



Potential future enhancements include:



\## Advanced Conversation Memory



Introduce persistent conversation storage.



```text

Session

&#x20;  ↓

Conversation History

&#x20;  ↓

Long-Term Context

```



\## Better Numerical Understanding



Improve handling of expressions such as:



```text

2 مليون

مليون ونصف

900 ألف

حوالي 2 مليون

```



and normalize them consistently.



\## Confidence-Based Extraction



Each extracted field could include a confidence score:



```json

{

&#x20; "Annual\_Revenue": {

&#x20;   "value": 2000000,

&#x20;   "confidence": 0.97

&#x20; }

}

```



Low-confidence values could trigger clarification questions.



\## Automatic Validation



For example:



```text

Annual Revenue >= Annual Expenses

```



could be validated before model inference.



\## Observability



Introduce:



\- Structured logging

\- Metrics

\- Tracing

\- Provider latency dashboards

\- Error monitoring



\## Production Deployment



Potential production architecture:



```text

Load Balancer

&#x20;     ↓

FastAPI Instances

&#x20;     ↓

Redis / Session Store

&#x20;     ↓

Database

&#x20;     ↓

AI Providers

```



\---



\# Development Workflow



Create a feature branch:



```bash

git checkout -b feature/<feature-name>

```



Check repository status:



```bash

git status

```



Stage changes:



```bash

git add .

```



Commit:



```bash

git commit -m "Describe the change"

```



Push:



```bash

git push -u origin feature/<feature-name>

```



\---



\# Example Git Workflow



```bash

git checkout -b feature/taya-voice-pipeline



git add .



git commit -m "Add Taya voice pipeline"



git push -u origin feature/taya-voice-pipeline

```



\---



\# Architecture Principles



The project follows several core engineering principles:



\### Single Responsibility



Each service should have one clear responsibility.



\### Separation of Concerns



Conversation logic, provider logic, state management, and feature engineering are separated.



\### Dependency Abstraction



External AI services are accessed through provider abstractions.



\### Fail Gracefully



Provider failures should not unnecessarily terminate the user conversation.



\### Validate Before Inference



The ML model should only receive a complete and valid feature representation.



\### Configuration Over Hard-Coding



Provider configuration and secrets should be managed through environment variables.



\---



\# Technology Stack



| Layer | Technology |

|---|---|

| Language | Python |

| API Framework | FastAPI |

| ASGI Server | Uvicorn |

| Async Runtime | AsyncIO |

| Frontend | HTML / JavaScript |

| STT | Provider-based architecture |

| LLM | Provider-based LLM service |

| TTS | ElevenLabs / Fish Audio / Gemini |

| Conversation Engine | Taya |

| Data Format | JSON |

| Configuration | Environment Variables |

| Testing | Python Test Suite |

| Version Control | Git / GitHub |



\---



\# Repository Goals



The primary goal of TAYA is to provide a natural voice-based interface for collecting structured tax-risk information.



Instead of:



```text

Form

&#x20;├── Business Type

&#x20;├── Region

&#x20;├── Revenue

&#x20;├── Expenses

&#x20;├── Tax

&#x20;├── VAT

&#x20;├── Audits

&#x20;└── Compliance

```



TAYA provides:



```text

Natural Conversation

&#x20;       ↓

AI Understanding

&#x20;       ↓

Structured Data

&#x20;       ↓

Feature Engineering

&#x20;       ↓

Tax Risk Model

```



This approach reduces the friction of traditional form-based data collection and creates a more natural user experience.



\---



\# Final Architecture Summary



```text

&#x20;                   USER

&#x20;                    │

&#x20;                    ▼

&#x20;             ┌─────────────┐

&#x20;             │  FRONTEND   │

&#x20;             └──────┬──────┘

&#x20;                    │

&#x20;                 AUDIO

&#x20;                    │

&#x20;                    ▼

&#x20;             ┌─────────────┐

&#x20;             │     STT     │

&#x20;             └──────┬──────┘

&#x20;                    │

&#x20;                 TEXT

&#x20;                    │

&#x20;                    ▼

&#x20;       ┌────────────────────────┐

&#x20;       │         TAYA           │

&#x20;       │                        │

&#x20;       │ Conversation Controller│

&#x20;       │ LLM                    │

&#x20;       │ Extraction             │

&#x20;       │ State Management       │

&#x20;       │ Question Bank         │

&#x20;       └───────────┬────────────┘

&#x20;                   │

&#x20;             STRUCTURED DATA

&#x20;                   │

&#x20;                   ▼

&#x20;       ┌────────────────────────┐

&#x20;       │ Feature Engineering    │

&#x20;       └───────────┬────────────┘

&#x20;                   │

&#x20;             MODEL FEATURES

&#x20;                   │

&#x20;                   ▼

&#x20;       ┌────────────────────────┐

&#x20;       │   TAX RISK MODEL       │

&#x20;       └────────────────────────┘



&#x20;                   │

&#x20;             TAYA RESPONSE

&#x20;                   │

&#x20;                   ▼

&#x20;             ┌─────────────┐

&#x20;             │     TTS     │

&#x20;             └──────┬──────┘

&#x20;                    │

&#x20;                  AUDIO

&#x20;                    │

&#x20;                    ▼

&#x20;                  USER

```



\---



\# Status



\*\*Project:\*\* TAYA Voice Pipeline



\*\*Architecture:\*\* Modular Provider-Based AI Architecture



\*\*Interface:\*\* Voice-first conversational interface



\*\*Backend:\*\* FastAPI



\*\*Speech:\*\* STT + TTS



\*\*Intelligence:\*\* LLM-powered conversational extraction



\*\*Output:\*\* Structured tax-risk features ready for downstream ML inference



\---



\# License



Add the appropriate project license here.



\---



\# Contributors



Add project contributors and maintainers here.

