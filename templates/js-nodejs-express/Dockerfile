# FROM node:alpine
FROM dockerhub/library/node:alpine

COPY app /usr/app
WORKDIR /usr/app
RUN npm install express --save
EXPOSE 3000
CMD node app.js
