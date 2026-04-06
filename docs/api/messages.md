# Message

The standard message envelope passed between agents and through the runtime.

See [Messaging](../messaging.md) for routing semantics and payload rules.

---

::: agency.messages.Message
    options:
      show_source: true

---

## System message types

Messages with types prefixed `_agency.` are reserved for runtime internals.
Application code must not use this prefix.

::: agency.messages.SYSTEM_MESSAGE_TYPES
    options:
      show_source: false
