# Observability

Automatic OTEL tracing for every message, LLM call, tool invocation, and
supervisor restart. No instrumentation required.

See [Observability](../observability.md) for setup guides and the full span
attribute reference.

---

## Tracer

::: civitas.observability.tracer.Tracer
    options:
      members:
        - start_span
        - start_send_span
        - start_receive_span
        - start_llm_span
        - end_llm_span
        - start_tool_span
        - end_tool_span
        - new_trace_id
        - flush
      show_source: true

---

## SpanQueue

::: civitas.observability.span_queue.SpanQueue
    options:
      show_source: true

---

::: civitas.observability.span_queue.SpanData
    options:
      show_source: false

---

## Export Backends

::: civitas.observability.export_backend.ExportBackend
    options:
      show_source: false

---

::: civitas.observability.export_backend.ConsoleBackend
    options:
      show_source: true

---

::: civitas.observability.export_backend.FanOutBackend
    options:
      show_source: true
