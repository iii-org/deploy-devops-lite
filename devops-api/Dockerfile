FROM dockerhub/library/python:3.9.14-slim
RUN apt-get update && apt-get install -y --no-install-recommends git curl
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENTRYPOINT ["apis/gunicorn.sh"]