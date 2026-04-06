# Transport

The pluggable message delivery layer. Swap transports by changing one line
in your topology YAML — agent code is unchanged.

See [Transports](../transports.md) for a full guide with architecture diagrams.

---

## Protocol

::: agency.transport.Transport
    options:
      show_source: false

---

## Implementations

::: agency.transport.inprocess.InProcessTransport
    options:
      show_source: true

---

::: agency.transport.zmq.ZMQTransport
    options:
      show_source: true

---

::: agency.transport.nats.NATSTransport
    options:
      show_source: true

---

## Worker

::: agency.worker.Worker
    options:
      members:
        - from_config
        - start
        - stop
      show_source: true
