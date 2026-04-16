# Supervisor

Monitors child agents and supervisors. Applies restart strategies on failure.

See [Supervision](../supervision.md) for a full guide.

---

::: civitas.supervisor.Supervisor
    options:
      members:
        - start
        - stop
        - add_remote_child
        - all_agents
        - all_supervisors
      show_source: true

---

::: civitas.supervisor.RestartStrategy
    options:
      show_source: false

---

::: civitas.supervisor.BackoffPolicy
    options:
      show_source: false
