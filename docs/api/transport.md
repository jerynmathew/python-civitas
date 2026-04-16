# Transport

The pluggable message delivery layer. Swap transports by changing one line
in your topology YAML — agent code is unchanged.

See [Transports](../transports.md) for a full guide with architecture diagrams.

---

## Protocol

::: civitas.transport.Transport
    options:
      show_source: false

---

## Implementations

::: civitas.transport.inprocess.InProcessTransport
    options:
      show_source: true

---

::: civitas.transport.zmq.ZMQTransport
    options:
      show_source: true

---

::: civitas.transport.nats.NATSTransport
    options:
      show_source: true

---

## Worker

::: civitas.worker.Worker
    options:
      members:
        - from_config
        - start
        - stop
      show_source: true
