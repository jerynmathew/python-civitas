# Supervisor

Monitors child agents and supervisors. Applies restart strategies on failure.

See [Supervision](../supervision.md) for a full guide.

---

::: agency.supervisor.Supervisor
    options:
      members:
        - start
        - stop
        - add_remote_child
        - all_agents
        - all_supervisors
      show_source: true

---

::: agency.supervisor.RestartStrategy
    options:
      show_source: false

---

::: agency.supervisor.BackoffPolicy
    options:
      show_source: false
