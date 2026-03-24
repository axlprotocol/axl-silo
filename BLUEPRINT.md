# AXL SILO — Implementation Blueprint
## The Language Accelerator for LLMs
### BG-Engine Analysis · 2026-03-24

---

## 1. MY UNDERSTANDING

The Silo is not an agent framework. It is a **particle accelerator for reasoning**.

LangChain, CrewAI, AutoGen — they orchestrate agents to complete tasks.
The Silo creates a space where models **think together** using a shared compressed language.

The key insight from our experiments (BG-003 through Science Replication):
- 10.41x compression is real and repeatable across domains
- Compressed communication changes debate structure (monologues → dialogue)
- Agents change their minds more often in AXL than in English
- Multi-model disagreement is productive — it's signal, not noise

The Silo productizes this. The customer brings their models. We bring the language.

**The product is the report.** Everything else (bus, agents, UI) is infrastructure to produce the report. The report is what the customer keeps, shares, prints, acts on.

---

## 2. ARCHITECTURE ANALYSIS — WHAT'S RIGHT

The four-layer architecture is clean:
```
CORE  → Does the thinking (Python, no framework)
API   → Exposes the thinking (Flask + WebSocket)
UI    → Shows the thinking (HTML + JS + WebSocket)
CONFIG → Runs the thinking (entry point)
```

The bus-centric design is correct. Every message passes through one ordered pipe. Agents read from it, write to it. The operator reads from it. The signal extractor reads from it. The report reads from it. **One source of truth.**

The multi-provider default is the differentiator. Nobody else does "GPT argues with Claude while Gemini synthesizes" in a structured, measurable protocol.

---

## 3. WHAT'S MISSING — ADDITIONS TO THE BLUEPRINT

### 3a. Persistence (SQLite bus)

The bus MUST be persistent. If the server crashes at round 8, the customer loses everything. Use SQLite — one table, one row per packet:

```sql
CREATE TABLE bus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round INTEGER NOT NULL,
    agent_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    raw_axl TEXT NOT NULL,
    op TEXT,
    confidence INTEGER,
    subject TEXT,
    relation TEXT,
    tokens_in INTEGER DEFAULT 0,
    tokens_out INTEGER DEFAULT 0,
    latency_ms INTEGER DEFAULT 0,
    timestamp TEXT NOT NULL
);
```

This gives us querying for free: "all CON packets", "all YLD packets", "packets by agent X", "packets in round 5". The signal extractor becomes SQL queries instead of list iteration.

### 3b. Input Compression Pipeline

"Input is anything" is the hardest engineering problem in the blueprint. A 50,000-word enterprise report needs to become AXL seed packets. The pipeline:

```
Raw text (any format, any length)
  → Chunker (split into 2,000-token chunks with 200-token overlap)
  → Per-chunk: 1 LLM call → "Compress to 3-5 AXL OBS packets"
  → Deduplicate (same observation from different chunks)
  → Order by confidence
  → First 20-30 packets become the seed (round 0 on the bus)
  → Agents read them and start deliberating
```

Short input (<500 words): skip chunking, compress directly in 1 call.
Long input (>10K words): chunk + parallelize compression calls.
**The compression step is itself a cost** — must show in estimate.

### 3c. Cost Estimation Before Run

Before ENGAGE, show:
```
ESTIMATED COST:
  Seed compression: ~$0.15 (3 chunks)
  12 rounds × 5 agents: 60 LLM calls
    2× Claude Sonnet: ~$1.80
    2× GPT-4o:        ~$1.20
    1× Gemini Flash:  ~$0.30
  Report generation:   ~$0.50
  TOTAL ESTIMATED:     ~$3.95
```

### 3d. Session History

Completed sessions persist as directories:
```
sessions/
├── 2026-03-24_medical_diagnosis/
│   ├── bus.db          (SQLite — the raw truth)
│   ├── config.json     (agents, models, rounds, input)
│   ├── report.md       (the product)
│   ├── report.json     (structured data)
│   └── signal.json     (final intelligence snapshot)
```

The UI has a HISTORY tab to browse past sessions, re-read reports, replay bus feeds.

### 3e. Auto-Generated Agent Personas

When the customer pastes messy text, don't make them name agents. Detect the domain and auto-suggest:

```
Input detected as: Medical case study
Suggested agents:
  ◉ Oncologist (Claude Sonnet) — disease specialist
  ◉ Radiologist (GPT-4o) — imaging interpretation
  ◉ Pathologist (Gemini Flash) — tissue analysis
  ◉ Patient Advocate (Claude Sonnet) — patient perspective
  ◉ Devil's Advocate (GPT-4o) — challenges consensus

  [Accept]  [Customize]  [Add Agent]
```

One LLM call to analyze input and propose agents. Cost: ~$0.02.

---

## 4. WHAT COULD FAIL — RISK ANALYSIS

### Risk 1: Agent English Leakage (SEVERITY: HIGH)

Every experiment we ran showed this. Claude is the worst — writes packet then adds paragraph explaining it. GPT sometimes writes preamble.

**Mitigation (three layers):**
1. System prompt: "YOU HAVE FAILED THE PROTOCOL" language (proven in BG-007)
2. User message per round: "RESPOND IN AXL ONLY. ONE LINE." (proven effective)
3. Post-processing: find first line containing `π:` or `|OP.`, truncate rest

The parser must be LENIENT on input (handle messy responses) and STRICT on output (only clean packets go on the bus). If parsing fails entirely, log raw response and skip the turn — don't crash.

### Risk 2: Cross-Provider Format Inconsistency (SEVERITY: MEDIUM)

Gemini might produce `pi:` instead of `π:`. GPT might add spaces around `|`. Ollama models might hallucinate new operation codes.

**Mitigation:**
- codec.py normalizes: `pi:` → `π:`, strip spaces around `|`
- Validate operation codes: if not in known set, mark as `UNK`
- Confidence must be integer 0-99: clamp and cast
- If a field doesn't parse, store null but keep raw packet

### Risk 3: Rate Limiting (SEVERITY: MEDIUM)

5 agents, 3 providers, 12 rounds = 60 calls. OpenAI free tier allows 3 RPM.

**Mitigation:**
- queue.py tracks per-provider call timestamps
- Before each call: check RPM window. If exceeded, sleep.
- Exponential backoff on 429: 1s, 2s, 4s, 8s, give up at 30s
- Show status in UI: "OpenAI: 2/3 RPM used, next call in 8s"
- If provider fails 3x consecutive, mark agent OFFLINE, continue without

### Risk 4: WebSocket Reliability (SEVERITY: LOW)

Browser connections drop on mobile, tab switch, network change.

**Mitigation:**
- JS client: auto-reconnect with backoff (1s, 2s, 4s)
- On reconnect: GET /api/bus/since/<last_id> to catch up
- Show connection status: green dot = LIVE, red = RECONNECTING

### Risk 5: Report Quality (SEVERITY: MEDIUM)

200 AXL packets. Report LLM must read all and produce coherent analysis.

**Mitigation:**
- Signal extractor pre-computes beliefs, consensus, influence chains (~2K tokens)
- Report LLM gets the SIGNAL, not the raw bus
- Transcript section: mechanical rendering, no LLM needed
- Only exec summary + conclusion need LLM calls (2 calls total)

### Risk 6: "Input Is Anything" Edge Cases (SEVERITY: HIGH)

Customer pastes PDF with headers, footers, page numbers, legal boilerplate.

**Mitigation:**
- Pre-clean: strip obvious noise (page numbers, repeated headers)
- Chunker: overlap by 200 tokens so context isn't lost at boundaries
- Per-chunk prompt: "Extract factual claims. Ignore formatting artifacts."
- If input < 500 words: skip chunking
- If compression produces < 3 packets: warn "input may lack substance for deliberation"

---

## 5. IMPLEMENTATION PLAN — FILE BY FILE, IN ORDER

### Phase 1: Foundation (build first, everything depends on these)

**File 1: `codec.py` (~120 lines)**
- `AXLPacket` dataclass: agent, op, confidence, subject, relation, evidence, temporal, raw
- `parse(raw: str) → AXLPacket` — regex parser, handles malformed input
- `decode(packet: AXLPacket) → str` — human-readable English
- `compress(text: str, config) → list[AXLPacket]` — LLM call to compress input to OBS packets
- `strip_english(raw: str) → str` — extract AXL from noisy LLM response
- Test against real BG-007 packets before proceeding

**File 2: `rosetta.py` (~40 lines)**
- `load(path_or_url) → str` — load + cache
- `build_system_prompt(name, role, rosetta) → str`
- `build_round_message(context) → str`

**File 3: `bus.py` (~100 lines)**
- `Bus` class with SQLite backend
- `post(packet, round, agent_id, provider, tokens, latency)`
- `get_all()`, `get_since(id)`, `get_context(last_n=20)`, `get_round(n)`
- Thread-safe, observable (callback list for WebSocket broadcast)

### Phase 2: Agent Loop

**File 4: `agent.py` (~100 lines)**
- `Agent` class: name, role, model, provider, api_key, api_base, temperature
- `respond(context) → AXLPacket` — prompt → litellm → parse
- Error handling: on failure return None, log, skip turn

**File 5: `queue.py` (~60 lines)**
- `ProviderQueue`: rpm_limit, call_timestamps, backoff
- `wait_if_needed()`, `record_call()`, `get_stats()`

**File 6: `workspace.py` (~150 lines)**
- `Workspace`: owns bus, agents, queues, state machine
- `create()` — compress input, create agents, seed bus
- `run()` — threaded round loop with pause/resume/stop
- `inject()` — operator posts packet

### Phase 3: Intelligence

**File 7: `signal.py` (~150 lines)**
- `beliefs()` — per-agent trajectory
- `consensus()` — weighted PRD confidence
- `operations()` — op distribution
- `influence_chains()` — YLD→RE: trace
- `predictions()` — ranked PRD list
- `summary()` — everything in one dict

**File 8: `report.py` (~200 lines)**
- 12 sections: exec summary, methodology, participants, transcript, beliefs, consensus, influence, ops, predictions, conclusion, cost appendix, raw appendix
- 2 LLM calls (summary + conclusion), everything else mechanical
- Output: Markdown + JSON

### Phase 4: API + UI

**File 9: `server.py` (~180 lines)**
- Flask REST + WebSocket
- All endpoints from blueprint
- Serves static/index.html
- CORS enabled

**File 10: `static/index.html` (~650 lines)**
- Three-panel layout + setup overlay
- WebSocket client with auto-reconnect
- Dark theme, operation color coding
- Setup: paste input, add agents, estimate cost, ENGAGE

### Phase 5: Entry

**File 11: `run.py` (~30 lines)**
- argparse: --port 7000, --host 0.0.0.0
- Dependency check, banner, start server

**File 12: `requirements.txt`**
```
flask>=3.0
flask-sock>=0.7
litellm>=1.40
pyyaml>=6.0
```

---

## 6. WHAT I'D BUILD DIFFERENTLY

### 6a. Streaming Responses
Stream tokens via litellm. The UI shows packets appearing character by character. The moment `π:` appears, the bus knows a packet is forming. Dramatic and useful.

### 6b. Agent Temperature Variance
Devil's advocate: temp=0.9 (creative). Data analyst: temp=0.2 (precise). Synthesizer: temp=0.5 (balanced). Default varies by detected role.

### 6c. Operator Translation
Inject bar has a "translate" mode. Operator types English, system compresses to AXL, shows preview, operator confirms, posts to bus.

### 6d. Round Strategy
- Rounds 1-3: OBS + INF only (observation phase)
- Rounds 4-8: CON + MRG + SEK (debate phase)
- Rounds 9-11: YLD + PRD (convergence phase)
- Round 12: Final PRD only (prediction phase)

Enforce via round-specific system prompt: "This is the debate phase. Use CON or MRG."

### 6e. Provider Health Dashboard
Real-time latency, error rate, cost per provider. Shown in the RIGHT panel. Operational intelligence for the operator.

---

## 7. LINE COUNT SUMMARY

```
codec.py       120 lines   Packet parser, decoder, compressor
rosetta.py      40 lines   Loader, cache, prompt builder
bus.py         100 lines   SQLite message bus, observable
agent.py       100 lines   LLM wrapper, response parsing
queue.py        60 lines   Rate limiter, cost tracker
workspace.py   150 lines   Session manager, round loop
signal.py      150 lines   Intelligence extraction
report.py      200 lines   Academic report generator
server.py      180 lines   Flask REST + WebSocket
index.html     650 lines   Three-panel UI + setup overlay
run.py          30 lines   Entry point
─────────────────────────────────────────
TOTAL        1,780 lines   Complete product. No frameworks.
```

---

## 8. DEPENDENCIES

```bash
pip install flask flask-sock litellm pyyaml
```

Four packages. SQLite is stdlib. Rosetta loads from URL.

---

## 9. WHAT THIS IS NOT

- NOT an agent framework (no tasks, no tools, no orchestration)
- NOT a chatbot (no conversation, no memory, no dialogue)
- NOT a RAG system (no vectors, no retrieval, no embeddings)
- NOT a workflow engine (no DAGs, no state machines, no branching)

It is a **deliberation accelerator**. Models think together in compressed language. Intelligence emerges from their disagreement. The report captures what emerged.

The Silo is to LLMs what CERN is to particles. We don't create intelligence. We collide it.

---

*BG-Engine · Battlegrounds Server · 137.184.164.190*
*Awaiting build authorization.*
