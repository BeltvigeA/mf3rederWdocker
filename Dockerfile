FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

RUN pip install --no-cache-dir fastapi uvicorn python-multipart

COPY . .

RUN python -m compileall .

EXPOSE 8080

CMD ["uvicorn", "main:apiApp", "--host", "0.0.0.0", "--port", "8080"]


