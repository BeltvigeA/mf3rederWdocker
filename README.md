# FastAPI GCode Service

This service exposes a FastAPI endpoint that accepts a `.3mf` or `.gcode.3mf` file, extracts metadata, and returns a base64 image along with selected G-code values.

## Running locally

```bash
pip install -r requirements.txt "uvicorn[standard]"
./scripts/startServer.sh
```

To enable HTTP/2 locally, set the `HTTP2_CERT_FILE` and `HTTP2_KEY_FILE` environment variables to the paths of your TLS certificate and private key before running the startup script:

```bash
HTTP2_CERT_FILE=certs/server.crt HTTP2_KEY_FILE=certs/server.key ./scripts/startServer.sh
```

## Build and run with Docker

```bash
docker build -t mf3-reader-gcode .
docker run -p 8080:8080 \
  -e HTTP2_CERT_FILE=/certs/server.crt \
  -e HTTP2_KEY_FILE=/certs/server.key \
  -v "$(pwd)/certs:/certs:ro" \
  mf3-reader-gcode
```

## Deploy to Google Cloud Run using Docker

```bash
gcloud builds submit --tag gcr.io/PROJECT_ID/gcode-service
gcloud run deploy gcode-service \
  --image gcr.io/PROJECT_ID/gcode-service \
  --region REGION \
  --allow-unauthenticated
```

Deploying the refreshed image is sufficient—Cloud Run terminates TLS at the load balancer and forwards HTTP/2 traffic to the container over the internal network, so no additional certificate configuration is required inside the service.

## Endpoint

`POST /process` with form-data field `gcode3mf` containing the file. The response JSON includes:

- `plateImage`: base64 encoded `plate_1.png` from the `metadata` folder
- `values`: dictionary with keys like `model printing time`, `total filament weight`, etc.

## Testing

```bash
pip install -r requirements.txt pytest flake8
flake8
pytest
```
