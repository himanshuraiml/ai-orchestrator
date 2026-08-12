# Hybrid Orchestration vs. Fully External LLM
## Impact Analysis: External Tokens · Execution Speed · Quality

> **Your Profile:** Mixed workload (4 simple / 4 medium / 2 hard per day) · Heavy context (50K–200K tokens) · 30s latency tolerance · Claude Code Pro ($20/month) baseline · Both interactive + batch · Hits context limits regularly

---

## 1. The Core Token Economics

### Where tokens actually go in "fully external" (Claude Code today)

Every time you use Claude Code on a large task, it consumes:

```
Input tokens  = system prompt + full conversation history + uploaded files + tool results
Output tokens = Claude's response + tool calls

Typical heavy task on Claude Code:
  System prompt:            ~2,000 tokens
  Conversation history:    ~15,000 tokens (grows per turn)
  Uploaded file/repo:      ~40,000–150,000 tokens
  ─────────────────────────────────────────────────
  Total input per call:    ~57,000–167,000 tokens
  Output per call:          ~1,000–8,000 tokens
  
  A 10-turn coding session on a large codebase:
  → ~500,000–1,500,000 tokens total
```

With Claude Code Pro ($20/month subscription), these tokens are hidden — but they are the reason you hit context limits and get degraded responses. **The limit is real even if the billing is not per-token.**

---

## 2. Hybrid System Token Impact

### Task routing under your profile (10 tasks/day)

| Task Tier | Count/day | Token Size | Hybrid Route | External Tokens |
|---|---|---|---|---|
| **Simple** (classify, short edit, summarize short doc) | 4 | 500–5K | Local only | **0** |
| **Medium** (code generation, PDF summary, research) | 4 | 5K–50K | Local → verify → escalate ~30% | ~30K avg (escalated only) |
| **Hard** (large repo, 100-page doc, multi-step research) | 2 | 50K–200K | Local for classification/chunking, Claude for synthesis | ~80K avg (compressed context) |

### External token reduction estimate

```
Fully external (Claude Code style):
  4 simple × 3,000 tokens avg   =  12,000
  4 medium × 25,000 tokens avg  = 100,000
  2 hard × 120,000 tokens avg   = 240,000
  ─────────────────────────────────────────
  Daily total:                  ~352,000 tokens to external LLM

Hybrid orchestration:
  4 simple → local only         =       0   (saved: 12,000)
  4 medium → 30% escalate only  =  30,000   (saved: 70,000)
  2 hard → compressed context   =  80,000   (saved: 160,000)
  ─────────────────────────────────────────
  Daily total:                  ~110,000 tokens to external LLM

  External token reduction:     ▼ ~69% fewer external tokens per day
```

### Why "hard" tasks still send tokens externally but much less

The critical trick is **context compression before escalation** (arch doc §92):

```
WITHOUT hybrid:
  100-page PDF → full 80,000 tokens → Claude

WITH hybrid:
  100-page PDF
    ↓ Local model: OCR + chunk + index (0 external tokens)
    ↓ Local model: classify which sections are relevant (0 external tokens)
    ↓ Retrieve: top 5 relevant sections (~8,000 tokens)
    ↓ Local model: generate initial draft (~0 external tokens)
    ↓ Claude receives: task + 8,000 tokens of relevant context + local draft
  
  External tokens: ~12,000 instead of 80,000 → 85% reduction per hard task
```

---

## 3. The Context Limit Problem — Solved

This is your biggest current pain point. Here's exactly why hybrid fixes it:

### Current pain (Claude Code fully external):

```
Turn 1:  [system] + [file 40K] + [response]     → 45K tokens used
Turn 3:  [system] + [file 40K] + [history 15K]  → 60K tokens used
Turn 7:  [system] + [file 40K] + [history 35K]  → 80K tokens used
Turn 10: [system] + [file 40K] + [history 50K]  → 95K tokens used → DEGRADED
Turn 12: CONTEXT LIMIT HIT → start fresh, lose all state
```

### Hybrid system fixes this with session memory + RAG:

```
Turn 1:  Local model reads full file (no external tokens)
Turn 1:  Chunks + indexes file into pgvector (one time cost)

Turn 3:  Query pgvector for relevant sections → 5K tokens retrieved
Turn 3:  Claude receives: task (500) + relevant context (5K) + session summary (1K)
         → Total: ~6.5K tokens, always bounded

Turn 7:  Same: 5K relevant context + compressed session summary
Turn 12: Same: never hits limit, session summary replaces raw history

Context growth: LINEAR → CONSTANT (bounded by retrieval budget, not history length)
```

---

## 4. Execution Speed — Honest Numbers

### Speed profile for Qwen2.5-coder 7B Q8 on Apple Silicon (16GB)

```
Token generation speed: ~25–40 tokens/sec (Apple M1/M2)
                        ~40–60 tokens/sec (Apple M3/M4)

Time-to-first-token:    ~1–3 seconds (model loaded) / ~8–15 seconds (model cold start)
```

### Speed comparison by task tier

#### Simple tasks (classification, short completion)

| Approach | Time | Notes |
|---|---|---|
| Claude Code (external) | **0.5–2 seconds** | API round trip, pre-loaded |
| Hybrid (local) | **3–8 seconds** | Local generation, 200-500 tokens output |
| **Verdict** | External wins | Local is 3–4× slower on trivial tasks |

> **But:** With Claude Code Pro, simple tasks still eat your daily context budget. With local, they're free and unlimited.

#### Medium tasks (code gen, doc summary, 5K–50K context)

| Approach | Time | Notes |
|---|---|---|
| Claude Code (with 30K context) | **8–25 seconds** | API + large input processing |
| Hybrid (local, no escalation) | **15–40 seconds** | Local generation, chunked context |
| Hybrid (local → escalation) | **25–60 seconds** | Local attempt + Claude review |
| **Verdict** | Roughly similar | Within your 30s tolerance for non-escalated |

#### Hard tasks (large repos, 100+ page docs, 50K–200K context)

| Approach | Time | Notes |
|---|---|---|
| Claude Code (150K context) | **45–180 seconds** | Large input → slow API processing → response |
| Gemini CLI (1M context) | **60–300 seconds** | Massive context, high TTFT |
| Hybrid (local chunks + compressed → Claude) | **60–150 seconds** | Local preprocessing: 30–60s, Claude call: 20–60s |
| **Verdict** | **Hybrid wins or ties** | And doesn't hit context limits |

---

## 5. The Latency Breakdown in Hybrid Mode

For a typical medium task in your system:

```
Phase                          Time       Who does it
─────────────────────────────────────────────────────────────
Task parsing + classification  1–2s       Local (phi4)
DAG planning                   2–5s       Local (phi4) or GPT-mini
Context retrieval (pgvector)   0.1–0.5s   PostgreSQL
Local model execution          10–30s     Qwen2.5-coder 7B
Verification (schema/Python)   0.5–2s     Python (deterministic)

IF no escalation needed:
  Total:                       ~14–40s    ✅ within your 30s target

IF escalation to Claude:
  + lesson retrieval            0.5s
  + build compressed context    1s
  + Claude API call             5–20s
  Total:                       ~20–65s    ⚠️ slightly over for hard tasks
```

**Key insight:** The 30-second target is met for ~70% of tasks (simple + non-escalated medium). Hard tasks run 60–150 seconds regardless of approach — but hybrid does it without context limit failures.

---

## 6. Where Hybrid is Slower and Why It's Worth It

Hybrid adds latency in 3 places the fully-external approach doesn't have:

### 1. DAG planning overhead (+2–5 seconds)
```
Fully external: User prompt → Claude → answer
Hybrid:         User prompt → local planner → DAG → execute
                              (2–5 extra seconds)
```
**Payoff:** The plan is inspectable, resumable, and parallel-executable. A 3-step parallel workflow saves more time than the planning overhead.

### 2. Local model attempt before escalation (+10–30 seconds overhead when escalation needed)
```
Hybrid:  Local attempt (15s) → verify (1s) → "not good enough" → Claude (15s) = 31s
External: → Claude directly (15s)
          = 16s extra when local fails
```
**Payoff:** When local succeeds (70% of tasks), you save the Claude call entirely. The 16-second penalty on the 30% that escalate is justified by the 100% savings on the 70% that don't.

### 3. Embedding + chunking on first file ingestion (+5–30 seconds one-time per file)
```
First upload of a 100-page PDF:
  OCR:           10–30s
  Chunking:      2–5s
  Embedding:     5–15s (nomic-embed-text local)
  Indexing:      1–2s
  Total:         18–52s (one-time)

Subsequent queries on same file: 0.1–0.5s (pgvector lookup)
```
**Payoff:** If you query the same document 5+ times (typical research workflow), you save 5× the API call cost of sending the full document each time.

---

## 7. Expected Monthly Impact vs. Claude Code Pro

### Scenario A: You stay on Claude Code Pro subscription

```
Today (Claude Code only):
  Daily context budget frequently exhausted
  Forced to restart sessions → lose state
  Context degradation on long sessions
  Cost: $20/month (fixed)

With hybrid (Claude Code Pro still used, but via API for escalation):
  Local handles ~65–70% of tasks
  Claude handles ~30–35% but with compressed context
  Context limit pain: eliminated (RAG keeps context bounded)
  Cost: $20/month Pro subscription
       + $0–5/month API overage (for escalated tasks via API)
  Total: ~$20–25/month

Net gain: Same cost, no context limits, better session continuity
```

### Scenario B: You switch to API-only (pay per token)

```
Current equivalent without hybrid:
  ~352,000 tokens/day external
  Claude Sonnet 3.5: $3/MTok input, $15/MTok output
  ~350K input + 30K output/day
  ≈ $1.05 + $0.45 = ~$1.50/day = ~$45/month

With hybrid:
  ~110,000 tokens/day external (after local handles 65%)
  ~110K input + 12K output/day
  ≈ $0.33 + $0.18 = ~$0.51/day = ~$15/month

Monthly saving: ~$30/month (67% reduction)
Annual saving:  ~$360/year

Against: local infra cost ≈ $0 (your Mac is already on)
```

---

## 8. The Escalation Rate is the Key Variable

Your entire token/speed profile hinges on **what % of tasks the local model handles acceptably**:

| Escalation Rate | External tokens/day | Daily avg latency | Quality level |
|---|---|---|---|
| 10% escalate (optimistic) | ~40K tokens | 15–25s avg | May be too aggressive, quality dips |
| **30% escalate (realistic target)** | **~110K tokens** | **20–35s avg** | **80–90% quality on local tasks** |
| 50% escalate (conservative) | ~180K tokens | 25–45s avg | High quality throughout |
| 80% escalate (pessimistic) | ~280K tokens | 30–55s avg | Near-Claude quality, less benefit |

**Your system improves this automatically over time:**
```
Month 1: 50% escalation (local model cold, no lessons yet)
Month 3: 35% escalation (lesson memory kicks in, routing improves)
Month 6: 25% escalation (contextual bandit optimized, prompt policies evolved)
Month 12: ~20% escalation (mature lesson store, well-tuned routing)
```

This is why the RL + lesson system matters — it's not just architectural elegance. It directly reduces the escalation rate over time, compounding your token savings.

---

## 9. Summary Table

| Metric | Fully External (Claude Code) | Hybrid (Your System) | Delta |
|---|---|---|---|
| External tokens/day | ~352K | ~110K | **▼ 69%** |
| Context limit failures | Regular (you confirmed this) | Eliminated | **✅ Fixed** |
| Simple task latency | 0.5–2s | 3–8s | **▲ 3–4× slower** |
| Medium task latency | 8–25s | 15–40s | **▲ ~1.5× slower** |
| Hard task latency | 45–180s | 60–150s | **≈ Same** |
| Session continuity | Breaks at limit | Persistent via RAG | **✅ Fixed** |
| Monthly cost (API) | ~$45 | ~$15 | **▼ 67%** |
| Improves over time | No | Yes (lesson + bandit) | **✅ Compounding** |
| Works offline/private | No | Yes (local model) | **✅ Fixed** |
| Context degradation | Yes (end of long sessions) | No (bounded by budget) | **✅ Fixed** |

---

## 10. The Honest Tradeoffs

### Where hybrid genuinely loses:
1. **Simple task latency** — local is 3–4× slower for trivial tasks. If you need sub-2-second responses on simple questions, fully external wins.
2. **Initial complexity** — you're building the system. Claude Code is just installed.
3. **First-query on new files** — the one-time ingestion cost adds 20–50 seconds.
4. **Local model quality floor** — Qwen 7B at Q8 is good but not Claude-level. ~80–85% quality on tasks it handles solo.

### Where hybrid definitively wins:
1. **Context limit exhaustion** — completely eliminated.
2. **Heavy context tasks** — compressing 150K → 12K before Claude call is a massive gain.
3. **Private/sensitive data** — stays local, never leaves your Mac.
4. **Cost at scale** — 67% reduction in external tokens once system is operational.
5. **Session continuity** — the lesson + RAG memory makes the system smarter each day, not just stateless.
6. **Rate limit resilience** — local model never rate-limits.

---

## 11. Recommendation: Where to Set the Escalation Threshold

Given your profile (heavy context, 30s tolerance, 80–90% quality bar), the optimal initial escalation policy:

```yaml
escalate_to_cloud_if:
  local_confidence < 0.65          # local model unsure
  OR task_type = hard              # complexity threshold
  OR context_tokens > 30000        # too large for local 7B
  OR privacy = cloud_ok            # user explicitly allows
  AND privacy != private           # never cloud for private data

compress_before_escalation:
  max_context_tokens_to_cloud: 15000   # never send more than 15K, retrieve instead
  always_include: task + local_draft + specific_uncertainty
```

This gives you the **~30% escalation rate** which is the sweet spot for your quality bar and budget.
