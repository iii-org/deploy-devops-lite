FROM dockerhub/library/maven:3.6.3-openjdk-15 as builder
COPY ./app /app
WORKDIR /app
#RUN ls && mvn clean install
RUN ls && mvn package spring-boot:repackage
FROM dockerhub/library/tomcat:jdk11
RUN ["rm", "-rf", "/usr/local/tomcat/webapps/ROOT"]
COPY --from=builder /app/target/*.jar /usr/local/tomcat/webapps/ROOT.jar
CMD ["java","-jar","/usr/local/tomcat/webapps/ROOT.jar"]
#RUN mvnw spring-boot:run
