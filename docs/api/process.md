# AgentProcess

Base class for all agents. Subclass it and implement `handle()`.

See [Core Concepts](../concepts.md) and [Getting Started](../getting-started.md) for usage examples.

---

::: agency.process.AgentProcess
    options:
      members:
        - on_start
        - handle
        - on_error
        - on_stop
        - send
        - ask
        - broadcast
        - reply
        - checkpoint
      show_source: true

---

::: agency.process.ProcessStatus
    options:
      show_source: false

---

::: agency.process.Mailbox
    options:
      show_source: true
