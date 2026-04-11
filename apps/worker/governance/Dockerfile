FROM golang:1.22-alpine AS builder

WORKDIR /src

COPY go.mod ./
COPY cmd ./cmd
COPY internal ./internal
COPY pkg ./pkg

RUN go build -o /out/governance-proxy ./cmd

FROM alpine:3.20

RUN apk add --no-cache curl

WORKDIR /app

COPY --from=builder /out/governance-proxy /usr/local/bin/governance-proxy

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -fsS http://localhost:8090/health || exit 1

CMD ["governance-proxy"]
