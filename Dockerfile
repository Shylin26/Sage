FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    gcc \
    git \
    curl \
    golang-go \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN cd server && go build -o sage-server .

COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

EXPOSE 8000
CMD ["./entrypoint.sh"]
