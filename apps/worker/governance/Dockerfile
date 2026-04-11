FROM golang:1.22-alpine AS builder

WORKDIR /src

COPY go.mod ./
COPY cmd ./cmd
COPY internal ./internal
COPY pkg ./pkg

RUN go build -o /out/governance-proxy ./cmd

FROM alpine:3.20

WORKDIR /app

COPY --from=builder /out/governance-proxy /usr/local/bin/governance-proxy

EXPOSE 8090

CMD ["governance-proxy"]
