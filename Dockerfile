FROM python:3.12-slim AS builder

RUN apt-get -qq update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --prefix="/install" -r requirements.txt

FROM python:3.12-slim

RUN apt-get -qq update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Download AWS RDS global SSL certificate bundle
RUN mkdir -p /certs \
    && curl -fsSL https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem \
       -o /certs/global-bundle.pem

ENV PYTHONUNBUFFERED=1

WORKDIR /authservice

COPY --from=builder /install /usr/local
COPY auth_server.py .

ENV PORT=8081
EXPOSE 8081

ENTRYPOINT ["python", "auth_server.py"]
