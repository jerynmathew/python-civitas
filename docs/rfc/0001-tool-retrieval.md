# RFC 0001 — Selective Tool Retrieval for LLM Systems

**Status:** Draft
**Author:** Jeryn Mathew Varghese
**Created:** 2026-04
**Discussion:** *(to be submitted — MCP GitHub Discussions, Hacker News)*

---

## Summary

This RFC proposes a standard interface for **selective tool retrieval** in LLM systems: instead of passing all available tool schemas to the LLM on every call, the LLM receives a single `find_tools` meta-tool and retrieves only the schemas it needs, on demand. This resolves a fundamental scalability problem in tool-augmented LLM architectures.

---

## Motivation

### The problem

Every LLM API call that includes tools pays token cost for the full schema of every registered tool — name, description, parameter definitions — regardless of whether the LLM uses them:

```
LLM request = system prompt + messages + [tool_1_schema, tool_2_schema, ... tool_N_schema]
Token cost  = O(messages) + O(N × avg_schema_size)
```

This creates three compounding problems as tool sets grow:

**1. Token cost scales linearly with tool count.**
A modest set of 50 tools with an average schema size of 300 tokens costs 15,000 tokens per call — before a single user message. At $15/M tokens (GPT-4o), that's $0.225 per call in schema overhead alone, recurring on every turn.

**2. Selection accuracy degrades beyond ~20–30 tools.**
LLM benchmarks consistently show that tool selection accuracy drops as the tool list grows. The model attends to fewer candidates, confuses similar tools, and occasionally calls the wrong one. Smaller context windows on faster/cheaper models make this worse.

**3. Context window ceiling.**
There is a hard upper bound. A system with 200+ tools — common in enterprise integrations — cannot physically fit all schemas in a single context window alongside a meaningful conversation history.

### Why existing approaches don't solve this

**Static tool lists** are the status quo. All major LLM APIs (OpenAI, Anthropic, Google) accept a `tools` array. There is no standard mechanism for dynamic or selective tool loading.

**MCP `list_tools`** returns all tools from a connected server. It solves discovery from a single source but returns everything — no filtering, no retrieval by query, no cross-source aggregation.

**Manual tool subsetting** (developers pre-selecting tools per agent) doesn't scale — it requires code changes per new tool and breaks when agents need to compose across domains.

---

## Proposed interface

### The `find_tools` meta-tool

A compliant tool retrieval gateway exposes exactly one tool to the LLM:

```json
{
  "name": "find_tools",
  "description": "Search for available tools by capability. Returns tool schemas matching the query. Call this before using any tool you haven't retrieved yet.",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": {
        "type": "string",
        "description": "Natural language description of what you want to do"
      },
      "limit": {
        "type": "integer",
        "description": "Maximum number of tools to return (default: 5)",
        "default": 5
      }
    },
    "required": ["query"]
  }
}
```

The gateway returns a list of tool schemas in the standard format of the host LLM API (OpenAI function calling, Anthropic tool use, etc.). The LLM then calls the retrieved tool directly in the next turn.

### Interaction flow

```
Turn 1 — LLM receives: system prompt + user message + [find_tools schema]
Turn 1 — LLM calls:    find_tools(query="search the web for recent AI news")
Turn 1 — Gateway returns: [web_search schema]

Turn 2 — LLM calls:    web_search(query="recent AI news", num_results=5)
Turn 2 — Gateway executes web_search, returns results

Turn 2 — LLM responds to user with the results
```

Token cost comparison for a 50-tool system (300 tokens/schema avg):

| Approach | Schema tokens per call | Tool calls to complete task |
|----------|----------------------|---------------------------|
| Static list (all tools) | 15,000 | 1 |
| `find_tools` retrieval | ~300 (find_tools) + ~300 (retrieved) | 2 |

For tasks requiring 1–3 tools (the vast majority), retrieval saves 14,000+ tokens per call. For tasks requiring many tools, the LLM makes multiple `find_tools` calls — still cheaper than sending all schemas upfront.

### The `use_tool` optional shorthand

For systems where a two-turn round-trip is undesirable, a compliant gateway may additionally expose:

```json
{
  "name": "use_tool",
  "description": "Find and execute a tool in a single step.",
  "input_schema": {
    "type": "object",
    "properties": {
      "query": { "type": "string", "description": "What you want to do" },
      "params": { "type": "object", "description": "Parameters to pass to the matched tool" }
    },
    "required": ["query", "params"]
  }
}
```

The gateway resolves the query to a tool, validates params against the schema, executes it, and returns the result. This reduces round-trips at the cost of the LLM not seeing the schema before calling — suitable when the LLM has previously retrieved and cached the schema.

---

## Gateway requirements

A compliant tool retrieval gateway MUST:

1. Expose `find_tools(query, limit?)` returning tool schemas in the host API's native format
2. Support keyword-based retrieval as the baseline (no embedding dependency required)
3. Execute retrieved tools when called directly by name after retrieval
4. Return a structured error when a tool name is unrecognised (not a silent failure)

A compliant gateway SHOULD:

5. Support embedding-based retrieval for higher recall (optional, declared via capability advertisement)
6. Aggregate tools from multiple sources (local registry, MCP servers, remote APIs)
7. Cache retrieved schemas per session to avoid redundant `find_tools` calls
8. Expose its own interface via MCP (`list_tools` returns only `find_tools`; `call_tool` handles both retrieval and execution)

A compliant gateway MUST NOT:

9. Return the full tool list when `find_tools` is called with an empty query (defeats the purpose)
10. Require LLM-specific SDK changes — the interface uses the standard tool calling format of the host API

---

## Relationship to MCP

MCP (Model Context Protocol) defines the wire protocol for tool discovery and execution between LLM hosts and tool servers. This RFC operates at a layer above MCP:

```
LLM (sees only find_tools)
      ↓
Tool Retrieval Gateway          ← this RFC defines this interface
      ↓
MCP protocol (list_tools, call_tool)   ← MCP defines this
      ↓
Tool servers (local, remote, Composio, etc.)
```

MCP's `list_tools` is how the gateway discovers and registers tools from connected servers. This RFC's `find_tools` is how the LLM selects from those registered tools without receiving all of them at once. The two protocols are complementary, not competing.

A gateway that implements this RFC and exposes itself via MCP enables a fully composable stack: any MCP-compatible LLM host can connect to the gateway and immediately gain selective retrieval without any code changes.

---

## Discovery backends

The RFC does not mandate a specific retrieval algorithm. Implementations must support at minimum:

**Keyword backend (required)**
BM25 or simple TF-IDF over tool names and descriptions. No vector database dependency. Adequate for well-named tool sets.

**Embedding backend (optional)**
Dense vector similarity over tool descriptions. Higher recall for fuzzy queries ("something that sends messages" → `send_slack_message`, `send_email`, `post_tweet`). Requires a vector store.

Implementations SHOULD advertise which backends are available via a `gateway.capabilities` endpoint or MCP resource.

---

## Drawbacks

**Extra round-trip for first use.** The LLM must call `find_tools` before calling the actual tool — adding one turn to the first use of any new tool in a session. Mitigated by schema caching within a session.

**Retrieval can miss.** A poorly-named tool or an ambiguous query may return the wrong schema. The LLM must handle "no matching tool found" gracefully. Keyword backends have lower recall than embedding backends for cross-domain queries.

**LLM prompt engineering required.** The system prompt must instruct the LLM to call `find_tools` before attempting any tool call. Without this, models default to calling tools they hallucinate exist. This is a training/prompting concern, not a protocol concern.

---

## Alternatives considered

**Chunked tool lists** — send tools in batches across turns. Rejected: still sends schemas the LLM doesn't need; doesn't solve the selection accuracy problem.

**Tool routing at the agent level** — the developer manually assigns tool subsets per agent. Rejected: doesn't scale; requires code changes per new tool; breaks composability.

**Fine-tuning for tool routing** — train the model to select tools without seeing schemas. Rejected: requires expensive retraining per new tool set; not practical for dynamic tool registries.

**RAG over tool descriptions** — retrieve tool names only, then fetch schema on demand. Viable; this RFC effectively standardises that approach with a defined interface.

---

## Unresolved questions

1. **Schema caching protocol** — should the gateway define a standard way for the LLM host to signal "I already have this schema cached, don't resend"? Or is session-scoped caching sufficient?

2. **Multi-tool retrieval** — should `find_tools` return a ranked list (LLM picks) or execute retrieval + ranking and return only the top result? Current proposal returns a list; the LLM selects.

3. **Auth propagation** — when a retrieved tool requires per-user OAuth (e.g. Gmail), how does the gateway pass user identity from the LLM request through to the tool executor? Out of scope for this RFC; deferred to a credential propagation RFC.

4. **Tool versioning** — if a tool schema changes, how does the LLM know its cached schema is stale? Should `find_tools` responses include a schema version or ETag?

5. **Streaming tool results** — should the gateway support streaming responses from long-running tools? Not addressed in this draft.

---

## Reference implementation

[Fabrica](https://github.com/civitas-io/civitas-forge) is the reference implementation of this RFC. It is framework-agnostic — Civitas connects to it as one integration among many. Contributions and alternative implementations are welcome.

---

## Changelog

| Date | Change |
|------|--------|
| 2026-04 | Initial draft |
