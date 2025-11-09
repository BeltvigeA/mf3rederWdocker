FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python -m compileall .

RUN chmod +x scripts/startServer.sh

EXPOSE 8080

CMD ["scripts/startServer.sh"]


