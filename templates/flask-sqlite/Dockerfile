FROM dockerhub/library/python:3.8

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY app /app

EXPOSE 5000
CMD python3 -u app.py
