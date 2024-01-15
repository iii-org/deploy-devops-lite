FROM dockerhub/library/python:3.9.12-alpine
RUN pip install django==3.1.7

COPY ./app /app
WORKDIR /app
EXPOSE 8080

CMD ["python", "manage.py", "runserver", "0.0.0.0:8080", "--noreload"]
