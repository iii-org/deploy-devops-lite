FROM python:3.9.18

RUN apt update && apt-get install -y libpq-dev
RUN pip install Flask==2.1.0 Flask-SQLAlchemy==2.4.4 psycopg2==2.8.6 Jinja2==3.0.3 Werkzeug==2.0.3 SQLAlchemy==1.3.8

COPY app /app
WORKDIR /app

EXPOSE 5000
CMD python3 -u app.py
