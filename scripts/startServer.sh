#!/bin/sh
set -e

if [ -n "$HTTP2_CERT_FILE" ] && [ -n "$HTTP2_KEY_FILE" ]; then
  echo "Starting uvicorn with HTTP/2 and TLS"
  exec uvicorn main:apiApp --host 0.0.0.0 --port 8080 --http h2 --ssl-certfile "$HTTP2_CERT_FILE" --ssl-keyfile "$HTTP2_KEY_FILE"
else
  echo "Starting uvicorn with HTTP/1.1"
  exec uvicorn main:apiApp --host 0.0.0.0 --port 8080
fi
