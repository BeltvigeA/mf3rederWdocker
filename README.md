# FastAPI GCode Service

This service exposes a FastAPI endpoint that accepts a `.3mf` or `.gcode.3mf` file, extracts metadata, and returns a base64 image along with selected G-code values.

## Running locally

```bash
pip install -r requirements.txt
uvicorn main:apiApp --host 0.0.0.0 --port 8080
```

## Build and run with Docker

```bash
docker build -t gcode-service .
docker run -p 8080:80 gcode-service
```

## Deploy to Google Cloud Run using Docker

```bash
gcloud builds submit --tag gcr.io/PROJECT_ID/gcode-service
gcloud run deploy gcode-service \
  --image gcr.io/PROJECT_ID/gcode-service \
  --region REGION \
  --allow-unauthenticated
```

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
