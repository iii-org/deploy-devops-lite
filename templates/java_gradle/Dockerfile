FROM dockerhub/iiiorg/java_8_gradle_5.6:latest as build-stage
COPY app /usr/src/app
WORKDIR /usr/src/app
RUN ./gradlew clean build --info 


FROM dockerhub/library/httpd:2.4
WORKDIR /usr/local/apache2/htdocs
RUN rm /etc/localtime; ln -s /usr/share/zoneinfo/Asia/Taipei /etc/localtime 
RUN rm -rf *
RUN echo "Include conf/extra/httpd-autoindex.conf" >> /usr/local/apache2/conf/httpd.conf
COPY --from=build-stage /usr/src/app /usr/local/apache2/htdocs/
CMD ["httpd-foreground"]
