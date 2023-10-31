FROM dockerhub/bitnami/laravel:8-debian-10

# 將使用者需要安裝的清單放到opt資料夾內
COPY ./apt-package.txt /opt/
RUN cd /opt/ && \
    cat apt-package.txt | xargs apt install -y

# Setup working directory
WORKDIR /var/www

# create laravel latest version project
COPY app /var/www
RUN composer install
RUN cp .env.example .env
RUN php artisan key:generate

# Run service
EXPOSE 80
CMD php artisan serve --port=80 --host=0.0.0.0 
