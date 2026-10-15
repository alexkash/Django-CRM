FROM python:3.12-slim-bookworm
WORKDIR /tools
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY export.py table-policy.json ./
ENTRYPOINT ["python", "/tools/export.py"]
