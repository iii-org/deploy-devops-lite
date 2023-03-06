FROM dockerhub/library/php:7.4.30-cli-alpine3.15

COPY app /var/www/html
WORKDIR /var/www/html
EXPOSE 80
CMD ["php", "-S", "0.0.0.0:80"]
