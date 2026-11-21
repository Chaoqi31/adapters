FROM python:3.13-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# FrontierFinance grader (Apache-2.0), pinned, in an isolated virtualenv used only
# by the verifier: upstream samaya-ai/frontier-finance @ 8b71342 plus one
# compatibility change in judges.py for newer judge models (the parity fork,
# where the original side runs the same commit). Installed from upstream's
# uv.lock so the judge SDK versions match the ones the grader was written
# against: newer anthropic releases reject the temperature argument the grader passes.
ARG FRONTIER_FINANCE_COMMIT=e28747624053c3caca98489db9144c7c9372b34c
RUN pip install --no-cache-dir uv==0.9.18 \
    && git clone https://github.com/Chaoqi31/frontier-finance.git /tmp/frontier-finance \
    && git -C /tmp/frontier-finance checkout ${FRONTIER_FINANCE_COMMIT} \
    && cd /tmp/frontier-finance \
    && UV_PROJECT_ENVIRONMENT=/opt/ff-grader uv sync --frozen --no-dev --extra all --no-editable \
    && rm -rf /tmp/frontier-finance /root/.cache

WORKDIR /app
