# AXL SILO — Architecture Specification
# The Particle Accelerator for Large Language Models

## What This Is

A contained workspace where multiple LLMs from different providers
communicate ONLY through AXL Protocol. The operator brings their own
API keys. The Silo provides the ring — the Rosetta that makes those
models talk to each other at 10x compression, the containment that
keeps the deliberation structured, and the detection layer that
extracts the emergent signal.

You don't sell compute. You sell the language.

## The CERN Metaphor (Architecturally Accurate)

CERN doesn't create particles. It accelerates particles that already
exist, smashes them together in a controlled environment, and detects
what emerges from the collision.

The Silo doesn't create LLMs. OpenAI, Anthropic, Google, Meta created
them. The Silo puts them in a ring, compresses their communication
by 10x so they move faster, collides their reasoning in a contained
deliberation, and detects the emergent intelligence that no single
model could produce alone.

## Architecture Layers

```
┌─────────────────────────────────────────────────────┐
│                   LAYER 4: WEB UI                    │
│  The operator cockpit. What the customer sees.       │
│  Live bus feed, decoded packets, stats, controls.    │
│  HTML + JS + WebSocket. No framework dependency.     │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                   LAYER 3: API                        │
│  Flask REST + WebSocket endpoints.                    │
│  /workspace/create, /workspace/run, /bus/read,       │
│  /bus/inject, /agent/status, /signal                 │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                   LAYER 2: WORKSPACE                  │
│  Manages a deliberation session. Owns the round      │
│  loop, agent orchestration, timing, and the          │
│  extraction of the final signal.                     │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                   LAYER 1: CORE                       │
│  bus.py     — Message bus (ordered packet list)      │
│  agent.py   — LLM agent wrapper (Rosetta injection)  │
│  rosetta.py — Rosetta loader + prompt builder        │
│  codec.py   — AXL compress / decompress              │
│  signal.py  — Extract consensus signal from bus      │
└─────────────────────────────────────────────────────┘
```

## Data Flow

1. Operator creates a workspace with a seed (question + agents)
2. Workspace loads the Rosetta and creates N agents
3. Each agent connects to a different LLM provider via litellm
4. Round loop begins:
   a. Each agent reads the bus (last N messages)
   b. Agent calls its LLM with: Rosetta + bus history + "respond in AXL"
   c. Agent posts ONE AXL packet to the bus
   d. Bus broadcasts to all connected WebSocket clients
   e. Web UI shows the raw packet + decoded English
5. After all rounds complete, signal extractor produces the consensus
6. Operator sees: the prediction, confidence, evidence chain, and which
   agents agreed/disagreed/changed their minds

## File Structure

```
axl-silo/
├── core/
│   ├── __init__.py
│   ├── bus.py          — Message bus
│   ├── agent.py        — LLM agent wrapper
│   ├── rosetta.py      — Rosetta loader
│   ├── codec.py        — Compress / decompress
│   ├── signal.py       — Consensus signal extractor
│   └── workspace.py    — Session manager (round loop)
├── api/
│   ├── __init__.py
│   └── server.py       — Flask + WebSocket
├── web/
│   └── static/
│       ├── index.html   — Main application
│       ├── app.js       — WebSocket + UI logic
│       └── style.css    — Styling
├── seeds/
│   ├── medical-ovarian.md
│   ├── military-invasion.md
│   ├── finance-btc.md
│   └── personal-career.md
├── config/
│   └── default.yaml
├── rosetta-v2.1.md      — The Rosetta specification
├── requirements.txt
├── README.md
└── run.py               — Entry point
```

## Agent Configuration

Each workspace defines its agents. The operator can mix providers:

```yaml
workspace:
  name: "Medical Diagnosis"
  seed: "seeds/medical-ovarian.md"
  rounds: 12
  agents:
    - name: "Dr.Chen"
      role: "Gynecologic oncologist"
      model: "openai/gpt-4o"
      provider: "openai"
    - name: "Dr.Patel"
      role: "Reproductive endocrinologist"
      model: "anthropic/claude-sonnet-4-20250514"
      provider: "anthropic"
    - name: "Dr.Yamamoto"
      role: "Radiologist"
      model: "google/gemini-2.5-flash"
      provider: "google"
    - name: "NCCN_Guidelines"
      role: "Clinical guidelines database"
      model: "ollama/qwen2.5:32b"
      provider: "local"
```

## Key Design Decisions

1. NO FRAMEWORK. No LangChain. No CrewAI. No AutoGen.
   Raw LLM calls via litellm. The framework IS the Rosetta.

2. BRING YOUR OWN KEYS. The customer provides API keys.
   We never touch their tokens. We provide the language.

3. EVERY MESSAGE IS AXL. No English on the bus. Ever.
   The UI decodes for the human. The bus is pure protocol.

4. MULTI-PROVIDER BY DEFAULT. The power is in the collision.
   GPT + Claude + Gemini + Llama in the same ring.

5. THE ROSETTA IS THE ONLY SHARED CODE between agents.
   No agent knows about any other agent's implementation.
   The protocol IS the interoperability layer.
