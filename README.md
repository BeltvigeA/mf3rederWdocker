# FastAPI GCode Service

This service exposes a FastAPI endpoint that accepts a `.gcode.3mf` file, extracts metadata, and returns a base64 image along with selected G-code values.

## Running locally

```bash
pip install -r requirements.txt
uvicorn main:apiApp --host 0.0.0.0 --port 8080
```

## Deploying to Cloud Run without a Dockerfile

Google Cloud Run can build this service directly from source using [Cloud Buildpacks](https://cloud.google.com/run/docs/deploying-source-code). Ensure you are authenticated with `gcloud` and run:

```bash
gcloud run deploy gcode-service --source . --region REGION --allow-unauthenticated
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
