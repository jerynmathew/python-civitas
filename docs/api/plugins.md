# Plugins

Structural protocols — implement the right methods and any class qualifies.
No base class, no registration decorator.

See [Plugins](../plugins.md) for a full authoring guide.

---

## ModelProvider

::: civitas.plugins.model.ModelProvider
    options:
      show_source: false

---

::: civitas.plugins.model.ModelResponse
    options:
      show_source: false

---

::: civitas.plugins.model.ToolCall
    options:
      show_source: false

---

## Implementations

::: civitas.plugins.anthropic.AnthropicProvider
    options:
      members:
        - chat
      show_source: true

---

<!-- LiteLLMProvider: Phase 2 stub — autodoc reference removed until class is implemented -->

---

## ToolProvider & ToolRegistry

::: civitas.plugins.tools.ToolProvider
    options:
      show_source: false

---

::: civitas.plugins.tools.ToolRegistry
    options:
      members:
        - register
        - get
        - all_tools
        - schemas
      show_source: true

---

## StateStore

::: civitas.plugins.state.StateStore
    options:
      show_source: false

---

::: civitas.plugins.state.InMemoryStateStore
    options:
      show_source: true

---

::: civitas.plugins.sqlite_store.SQLiteStateStore
    options:
      members:
        - get
        - set
        - delete
        - close
      show_source: true

---

## Plugin Loading

::: civitas.plugins.loader.load_plugins_from_config
    options:
      show_source: true
