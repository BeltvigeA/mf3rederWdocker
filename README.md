# Gcode Metadata API

This FastAPI service accepts `.gcode.3mf` files, converts them to `.zip`, retrieves the `plate_1` image, and extracts key metadata from `gcode_1`.

## Local Run (no Docker)

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

## Deploy to Google Cloud Run without Dockerfile

```bash
gcloud run deploy gcode-api --source .
```
