# Plugins

Structural protocols — implement the right methods and any class qualifies.
No base class, no registration decorator.

See [Plugins](../plugins.md) for a full authoring guide.

---

## ModelProvider

::: agency.plugins.model.ModelProvider
    options:
      show_source: false

---

::: agency.plugins.model.ModelResponse
    options:
      show_source: false

---

::: agency.plugins.model.ToolCall
    options:
      show_source: false

---

## Implementations

::: agency.plugins.anthropic.AnthropicProvider
    options:
      members:
        - chat
      show_source: true

---

::: agency.plugins.litellm.LiteLLMProvider
    options:
      members:
        - chat
      show_source: true

---

## ToolProvider & ToolRegistry

::: agency.plugins.tools.ToolProvider
    options:
      show_source: false

---

::: agency.plugins.tools.ToolRegistry
    options:
      members:
        - register
        - get
        - all_tools
        - schemas
      show_source: true

---

## StateStore

::: agency.plugins.state.StateStore
    options:
      show_source: false

---

::: agency.plugins.state.InMemoryStateStore
    options:
      show_source: true

---

::: agency.plugins.sqlite_store.SQLiteStateStore
    options:
      members:
        - get
        - set
        - delete
        - close
      show_source: true

---

## Plugin Loading

::: agency.plugins.loader.load_plugins_from_config
    options:
      show_source: true
