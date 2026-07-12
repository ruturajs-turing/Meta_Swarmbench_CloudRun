FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends openssh-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .

CMD ["bash", "-lc", "test -f /data/ssh_host_ed25519_key || ssh-keygen -q -t ed25519 -N '' -f /data/ssh_host_ed25519_key; python app.py"]
