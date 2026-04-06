# Runtime

Assembles and manages the full Agency runtime. Wires transport, registry,
serializer, tracer, plugins, and the supervision tree.

See [Deployment](../deployment.md) and [Topology & CLI](../topology.md) for usage.

---

::: agency.runtime.Runtime
    options:
      members:
        - from_config
        - start
        - stop
        - ask
        - send
        - get_agent
        - all_agents
        - print_tree
      show_source: true

---

::: agency.components.ComponentSet
    options:
      members:
        - inject
      show_source: true

---

::: agency.components.build_component_set
    options:
      show_source: true
