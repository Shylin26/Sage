FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    gcc \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN curl -OL https://go.dev/dl/go1.22.0.linux-arm64.tar.gz \
    && tar -C /usr/local -xzf go1.22.0.linux-arm64.tar.gz \
    && rm go1.22.0.linux-arm64.tar.gz

ENV PATH=$PATH:/usr/local/go/bin

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN cd server && go build -o sage-server .

COPY entrypoint.sh .
RUN chmod +x entrypoint.sh

EXPOSE 8000
CMD ["./entrypoint.sh"]
