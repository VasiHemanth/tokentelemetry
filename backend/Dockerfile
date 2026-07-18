FROM python:3.12-slim

WORKDIR /app

COPY requirements.lock requirements.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock

COPY . .

ENV TT_HOST=0.0.0.0
ENV TT_API_PORT=8000
EXPOSE 8000

CMD ["python", "main.py"]
