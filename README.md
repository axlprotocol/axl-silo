# AXL Silo

### The Cognitive Collider

Put GPT, Claude, Gemini, and Llama in the same ring. Give them a question. They collide.

What comes out is intelligence no single model could produce alone.

```
1. Connect your LLMs
2. Paste anything
3. Get 10x more out of it
```

---

## What This Is

A contained workspace where multiple LLMs from different providers communicate exclusively through [AXL Protocol](https://axlprotocol.org) — a 445-line specification that any AI learns on first read.

You bring the models. You bring the API keys. The Silo provides the language.

The Rosetta compresses communication 10x. That compression is the acceleration. More thinking per token. More collisions per round. More intelligence per dollar.

---

## The Physics

CERN doesn't create particles. It accelerates them, collides them, and detects what emerges.

The Silo doesn't create intelligence. It accelerates reasoning through compression, collides perspectives through structured disagreement, and detects consensus through typed cognitive operations.

| CERN | Silo |
|------|------|
| Superconducting magnets | Rosetta (10x compression) |
| Beam pipe | AXL message bus |
| Particle beams | LLM agents from different providers |
| Collision | Agents read and respond to each other |
| Detector | Signal extractor (beliefs, consensus, influence) |
| Published paper | The report |

---

## Quick Start

```bash
git clone https://github.com/axlprotocol/axl-silo.git
cd axl-silo
pip install -r requirements.txt
python run.py --port 7000
```

Open `http://localhost:7000`. Paste your text. Pick your models. Hit ENGAGE.

---

## Two Ways To Use It

### Paste and Go

You're a nurse, an intern, a student, a founder at 2am. Paste anything: messy notes, a patient summary, a contract, a thesis draft, raw data, a half-finished novel.

The Silo auto-detects the domain, suggests agents with opposing perspectives, compresses your input, runs the collider, and produces a report you can actually use.

Time: 3-5 minutes. Cost: $2-5. Skill required: none.

### Craft a Seed

You're an oncologist, a military analyst, a financial modeler, a lawyer. You spend an hour crafting a precise seed: defined agents, named entities, specific evidence, custom ontology, domain-specific round strategy.

At 10x compression, your 1-hour seed produces the equivalent of 10 hours of multi-expert deliberation. The report reads like a peer-reviewed paper.

Time: 1hr craft + 5min run. Cost: $5-15. Output: institutional-grade analysis.

Seeds are shareable, versioned, and composable. The starter library includes medical, military, financial, legal, scientific, geopolitical, career, and philosophical templates.

---

## The Collider

```
         ┌─────────────────────────┐
         │    HUMAN OPERATOR       │
         │  pastes anything        │
         │  gets a report          │
         └────────┬────────────────┘
                  │
         ┌────────▼────────────────┐
         │     AXL MESSAGE BUS     │
         │  every message is AXL   │
         │  no English on the wire │
         └──┬────┬────┬────┬───────┘
            │    │    │    │
         ┌──▼┐┌──▼┐┌──▼┐┌──▼──┐
         │GPT││CLD││GEM││LLMA │
         │   ││   ││   ││     │
         └───┘└───┘└───┘└─────┘
    Each agent: Rosetta as system prompt
    Each agent: reads bus, emits one AXL packet
    Each agent: different provider, different tokenizer
```

---

## The Report

The report is the product. Everything else is infrastructure to produce it.

When you click REPORT, you get a formal document with 13 sections:

1. **Title and metadata**: date, rounds, agents, providers, consensus score
2. **Executive summary**: one paragraph of the key finding
3. **Methodology**: how the Silo works, agent independence, protocol constraints
4. **Participant registry**: each agent's model, provider, packet count, final operation
5. **Deliberation transcript**: round by round, raw AXL packets with decoded English
6. **Belief trajectories**: per agent, how their confidence evolved, what changed their mind
7. **Consensus formation**: weighted score, agreement ratio, convergence velocity
8. **Influence chains**: who caused who to change their mind, most influential agent
9. **Operation distribution**: OBS/INF/CON/MRG/SEK/YLD/PRD counts and analysis
10. **Predictions**: all forecasts ranked by confidence, convergence analysis
11. **Conclusion**: summary findings, compression ratio, recommendation
12. **Appendix A: Cost**: tokens consumed, estimated English equivalent, savings
13. **Appendix B: Raw packets**: full bus transcript, chronological

Send it to your team. Your board. Your doctor. Your investors. Your professor.

---

## Architecture

```
axl-silo/
├── core/
│   ├── bus.py          — Message bus (SQLite + in-memory, write-through)
│   ├── agent.py        — LLM wrapper (any provider via litellm)
│   ├── rosetta.py      — Rosetta v2.2 loader with URL/local fallback
│   ├── codec.py        — Compress, decompress, parse, chunk
│   ├── signal.py       — Consensus, beliefs, influence chains, predictions
│   ├── workspace.py    — Session manager, round loop, phase strategy
│   ├── queue.py        — Per-provider rate limiting, retry, cost tracking
│   └── report.py       — 13-section academic report generator
├── api/
│   └── server.py       — Flask REST + WebSocket + report endpoints
├── web/static/
│   ├── index.html      — Mission control (three-panel cockpit UI)
│   └── compress.html   — AXL Compress standalone tool
├── templates/          — Seed library (8 domains)
├── sessions/           — Persisted deliberation history
├── rosetta-v2.2.md     — The specification
├── BLUEPRINT.md        — Implementation plan
├── LICENSE             — Apache 2.0
└── run.py              — Entry point
```

---

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/workspace/create` | POST | Create workspace, paste input, configure agents |
| `/api/workspace/run` | POST | Start the collider |
| `/api/workspace/pause` | POST | Pause deliberation |
| `/api/workspace/stop` | POST | Stop and extract signal |
| `/api/bus` | GET | Read all packets |
| `/api/bus/since/<id>` | GET | Poll for new packets |
| `/api/bus/inject` | POST | Operator injects a packet |
| `/api/signal` | GET | Current intelligence signal |
| `/api/agents` | GET | Agent statuses |
| `/api/estimate` | POST | Cost estimate before ENGAGE |
| `/api/sessions` | GET | Browse past deliberations |
| `/api/report` | GET | Full report as JSON |
| `/api/report/markdown` | GET | Full report as Markdown |
| `/api/report/download` | GET | Download report as .md file |
| `/ws` | WebSocket | Real-time packet stream |

---

## Supported Providers

| Provider | Model String | Connection |
|----------|-------------|------------|
| OpenAI | `openai/gpt-4o` | API key |
| Anthropic | `anthropic/claude-sonnet-4-20250514` | API key |
| Google | `google/gemini-2.5-flash` | API key |
| Local (Ollama) | `ollama/qwen2.5:32b` | `http://localhost:11434` |
| LiteLLM Proxy | `gpt-4` | `http://localhost:4000` |
| Any litellm model | [litellm docs](https://docs.litellm.ai/) | API key or base URL |

Bring your own keys. Your tokens. Your models. We provide the language.

---

## Round Strategy

The default collider runs in four phases:

| Phase | Rounds | Operations | Purpose |
|-------|--------|------------|---------|
| Observation | 1-3 | OBS, INF | Agents examine the evidence |
| Debate | 4-8 | CON, MRG, SEK | Agents argue and request information |
| Convergence | 9-11 | YLD, PRD | Agents update beliefs and predict |
| Final | 12 | PRD | Final predictions only |

Override with `"strategy": "free"` to allow all operations every round.

---

## What This Is Not

- Not an agent framework (no tasks, no tools, no orchestration)
- Not a chatbot (no conversation, no memory, no dialogue)
- Not a RAG system (no vectors, no retrieval, no embeddings)
- Not a workflow engine (no DAGs, no state machines, no branching)

It is a cognitive collider. Models think together in compressed language. Intelligence emerges from their disagreement. The report captures what emerged.

---

## Validated

| Metric | Value |
|--------|-------|
| Compression | 10.41x (BG-007 Medical) |
| Parse validity | 100% (1,502 packets) |
| Decompression fidelity | F = 97.6 |
| LLM architectures tested | 6 |
| Battleground experiments | 8 |
| Domains validated | Medical, military, finance, legal, science, geopolitics, career, philosophy |

---

## License

Apache 2.0

---

## Links

- **Protocol:** [axlprotocol.org](https://axlprotocol.org)
- **Rosetta:** [axlprotocol.org/rosetta](https://axlprotocol.org/rosetta)
- **Docs:** [docs.axlprotocol.org](https://docs.axlprotocol.org)
- **GitHub:** [github.com/axlprotocol](https://github.com/axlprotocol)
- **Compress:** [compress.axlprotocol.org](https://compress.axlprotocol.org)

---

*AXL Protocol · 2026 · Vancouver, BC*
*We don't create intelligence. We collide it.*
