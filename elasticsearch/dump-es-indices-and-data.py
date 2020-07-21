#!/usr/bin/env python3

"""Dump Elasticsearch indexes and a subset of data from a live server into JSON
files."""

import json
import os

from elasticsearch import Elasticsearch


CITY_IDS = (101748063, 101748109, 101748111, 101748113, 101748125, 101752117,
            101752181, 101752223, 101752777, 101758551, 101780925, 101825503,
            101833261, 101909779, 1108800123, 1125935959)


def main():
    es = Elasticsearch([os.environ['GOOUT_ELASTIC_HOST']],
                       port=int(os.environ['GOOUT_ELASTIC_PORT']))
    dump_index_mapping(es, "city")
    dump_index_mapping(es, "region")

    cities = dump_data(es, "city", CITY_IDS)
    region_ids = sorted(set(city['regionId'] for city in cities))
    dump_data(es, "region", region_ids)


def dump_index_mapping(es, index):
    resp = es.indices.get(index)
    ((name, definition),) = resp.items()  # expect a single definition in resp

    # Remove informational keys not supported when importing
    del definition['settings']['index']['creation_date']
    del definition['settings']['index']['provided_name']
    del definition['settings']['index']['uuid']
    del definition['settings']['index']['version']

    with open(f'index-mapping-{name}.json', 'w') as f:
        json.dump(definition, f, indent='  ')
    print(f'Index {index} definition dumped into {f.name}.')


def dump_data(es, index, ids):
    body = {'query': {'ids': {'values': ids}}}
    resp = es.search(body, index, params={'size': len(ids)})

    documents = [hit['_source'] for hit in resp['hits']['hits']]

    document_ids = sorted(d['id'] for d in documents)
    ids = sorted(ids)
    assert ids == document_ids, (ids, document_ids)

    # The output format is suitable for Elasticsearch Bulk API
    # https://www.elastic.co/guide/en/elasticsearch/reference/7.6/docs-bulk.html
    with open(f'index-data-{index}.ndjson', 'w') as f:
        for document in documents:
            json.dump({"index": {"_index": index, "_id": document['id']}}, f)
            f.write('\n')
            json.dump(document, f)
            f.write('\n')
        print(f'Written {len(documents)} documents into {f.name}.')
    return documents


if __name__ == '__main__':
    main()
