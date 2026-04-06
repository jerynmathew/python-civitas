# MessageBus

Central message router. Routes messages from sender to recipient by name,
delegates physical delivery to the Transport, and generates tracing spans.

See [Architecture](../architecture.md#message-flow--end-to-end) for the routing
resolution order.

---

::: agency.bus.MessageBus
    options:
      members:
        - setup_agent
        - route
        - request
        - lookup_all
      show_source: true

---

::: agency.registry.LocalRegistry
    options:
      members:
        - register
        - register_remote
        - deregister
        - lookup
        - lookup_all
      show_source: true

---

::: agency.registry.RoutingEntry
    options:
      show_source: false
