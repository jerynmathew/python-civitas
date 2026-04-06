FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
COPY agency/ agency/
COPY examples/ examples/

RUN pip install --no-cache-dir -e ".[nats,anthropic]"

ENTRYPOINT ["agency", "run"]
