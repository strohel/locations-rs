This folder contains everything needed to run an Elasticsearch instance with indexes and data necessary for the web service. Note that the
data sample is not sufficient to run a production service - it is only a limited subset necessary to run the test suite.

Run `docker-compose up` to build (if not already done) and run the docker image. It will listen on
port 9200 (which will be forwarded from local host into the container).
