"""Remote eval exporters — M2.6.

Each class implements the EvalExporter protocol and translates EvalEvent
into the target platform's expected format.  Install the matching extra to
use:

    pip install 'civitas[arize]'      # Arize Phoenix via OTEL OTLP
    pip install 'civitas[langfuse]'   # Langfuse (open-source / cloud)
    pip install 'civitas[braintrust]' # Braintrust
    pip install 'civitas[langsmith]'  # LangSmith
    pip install 'civitas[fiddler]'    # Fiddler AI observability (two-way)

All exporters are lazy-import: the matching SDK is only imported on
__init__, so importing this module without the extras installed is safe.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from civitas.evalloop import EvalEvent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ArizeExporter
# ---------------------------------------------------------------------------


class ArizeExporter:
    """Forward EvalEvents to Arize Phoenix as OTEL GenAI spans via OTLP.

    Requires: pip install 'civitas[arize]'

    Args:
        endpoint: OTLP gRPC endpoint of the Phoenix collector.
                  Defaults to the Phoenix local default (port 6006).
        service_name: Value for the OTEL service.name resource attribute.
    """

    def __init__(
        self,
        endpoint: str = "http://localhost:6006/v1/traces",
        service_name: str = "civitas",
    ) -> None:
        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            from opentelemetry.sdk.resources import SERVICE_NAME, Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
        except ImportError as exc:
            raise ImportError(
                "civitas[arize] is required for ArizeExporter. "
                "Install with: pip install 'civitas[arize]'"
            ) from exc

        resource = Resource({SERVICE_NAME: service_name})
        provider = TracerProvider(resource=resource)
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
        self._tracer = trace.get_tracer("civitas.eval", tracer_provider=provider)

    async def export(self, event: EvalEvent) -> None:
        with self._tracer.start_as_current_span(f"civitas.eval.{event.event_type}") as span:
            span.set_attribute("gen_ai.agent.name", event.agent_name)
            span.set_attribute("civitas.eval.event_type", event.event_type)
            span.set_attribute("civitas.eval.trace_id", event.trace_id)
            span.set_attribute("civitas.eval.message_id", event.message_id)
            for key, val in event.payload.items():
                if isinstance(val, str | int | float | bool):
                    span.set_attribute(f"civitas.eval.payload.{key}", val)


# ---------------------------------------------------------------------------
# LangfuseExporter
# ---------------------------------------------------------------------------


class LangfuseExporter:
    """Forward EvalEvents to Langfuse as traces.

    Requires: pip install 'civitas[langfuse]'

    Args:
        public_key: Langfuse public key.
        secret_key: Langfuse secret key.
        host: Langfuse host. Defaults to cloud endpoint.
    """

    def __init__(
        self,
        public_key: str,
        secret_key: str,
        host: str = "https://cloud.langfuse.com",
    ) -> None:
        try:
            from langfuse import Langfuse
        except ImportError as exc:
            raise ImportError(
                "civitas[langfuse] is required for LangfuseExporter. "
                "Install with: pip install 'civitas[langfuse]'"
            ) from exc

        self._client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)

    async def export(self, event: EvalEvent) -> None:
        trace = self._client.trace(
            id=event.trace_id or None,
            name=f"civitas.{event.event_type}",
            metadata={"agent_name": event.agent_name, **event.payload},
        )
        trace.generation(
            name=event.event_type,
            input=event.payload,
            metadata={"agent_name": event.agent_name},
        )


# ---------------------------------------------------------------------------
# BraintrustExporter
# ---------------------------------------------------------------------------


class BraintrustExporter:
    """Forward EvalEvents to Braintrust.

    Requires: pip install 'civitas[braintrust]'

    Args:
        api_key: Braintrust API key.
        project: Braintrust project name. Defaults to "civitas".
    """

    def __init__(self, api_key: str, project: str = "civitas") -> None:
        try:
            import braintrust
        except ImportError as exc:
            raise ImportError(
                "civitas[braintrust] is required for BraintrustExporter. "
                "Install with: pip install 'civitas[braintrust]'"
            ) from exc

        self._logger: Any = braintrust.init_logger(project=project, api_key=api_key)

    async def export(self, event: EvalEvent) -> None:
        self._logger.log(
            input=event.payload,
            metadata={
                "agent_name": event.agent_name,
                "event_type": event.event_type,
                "trace_id": event.trace_id,
            },
        )


# ---------------------------------------------------------------------------
# LangSmithExporter
# ---------------------------------------------------------------------------


class LangSmithExporter:
    """Forward EvalEvents to LangSmith as traced runs.

    Requires: pip install 'civitas[langsmith]'

    Args:
        api_key: LangSmith API key.
        project: LangSmith project name. Defaults to "civitas".
    """

    def __init__(self, api_key: str, project: str = "civitas") -> None:
        try:
            from langsmith import Client
        except ImportError as exc:
            raise ImportError(
                "civitas[langsmith] is required for LangSmithExporter. "
                "Install with: pip install 'civitas[langsmith]'"
            ) from exc

        self._client: Any = Client(api_key=api_key)
        self._project = project

    async def export(self, event: EvalEvent) -> None:
        self._client.create_run(
            project_name=self._project,
            name=event.event_type,
            run_type="chain",
            inputs=event.payload,
            extra={
                "agent_name": event.agent_name,
                "trace_id": event.trace_id,
                "message_id": event.message_id,
            },
        )


# ---------------------------------------------------------------------------
# FiddlerExporter
# ---------------------------------------------------------------------------


class FiddlerExporter:
    """Forward EvalEvents to Fiddler AI for production ML observability.

    Requires: pip install 'civitas[fiddler]'

    This exporter is one-way (export). Receiving guardrail signals back from
    Fiddler via webhook is not yet implemented — see M4.2 for planned
    two-way support once the Fiddler webhook API is stable.

    Args:
        url: Fiddler instance URL (e.g. "https://myorg.fiddler.ai").
        token: Fiddler API token.
        org_id: Fiddler organisation ID.
        project_id: Fiddler project ID.
        model_id: Fiddler model ID events are published under.
    """

    def __init__(
        self,
        url: str,
        token: str,
        org_id: str,
        project_id: str,
        model_id: str,
    ) -> None:
        try:
            import fiddler
        except ImportError as exc:
            raise ImportError(
                "civitas[fiddler] is required for FiddlerExporter. "
                "Install with: pip install 'civitas[fiddler]'"
            ) from exc

        self._client: Any = fiddler.Fiddler(url=url, token=token, org_id=org_id)
        self._project_id = project_id
        self._model_id = model_id

    async def export(self, event: EvalEvent) -> None:
        row: dict[str, Any] = {
            "agent_name": event.agent_name,
            "event_type": event.event_type,
            "timestamp": event.timestamp,
            **event.payload,
        }
        self._client.publish_event(
            project_id=self._project_id,
            model_id=self._model_id,
            event=row,
        )
