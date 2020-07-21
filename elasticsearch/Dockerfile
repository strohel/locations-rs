FROM elasticsearch:7.8.0

COPY index-mapping-*.json /
COPY index-data-*.ndjson /

# Start the elasticsearch server temporarily so that we import out indices
RUN env discovery.type=single-node /usr/local/bin/docker-entrypoint.sh eswrapper \
    # Wait for ES server to start (up to 60 seconds)
    & for in in $(seq 30); do curl -s localhost:9200/ > /dev/null && break || sleep 2; done \
    # Ensure it has started
    && curl -sS --fail localhost:9200/ \
    # Import mappings
    && curl -sS --fail localhost:9200/city_v1?format=yaml -X PUT -H "Content-Type: application/json" --data-binary @/index-mapping-city_v1.json \
    && curl -sS --fail localhost:9200/region_v1?format=yaml -X PUT -H "Content-Type: application/json" --data-binary @/index-mapping-region_v1.json \
    # Import data
    && curl -sS --fail localhost:9200/_bulk?format=yaml -X POST -H "Content-Type: application/x-ndjson" --data-binary @/index-data-city.ndjson \
    && curl -sS --fail localhost:9200/_bulk?format=yaml -X POST -H "Content-Type: application/x-ndjson" --data-binary @/index-data-region.ndjson \
    # Terminate the ES server gracefully
    && kill %1
