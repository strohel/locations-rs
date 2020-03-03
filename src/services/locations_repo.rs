//! Stateless Locations repository backed by Elasticsearch.

use crate::{
    response::{
        ErrorResponse,
        ErrorResponse::{InternalServerError, NotFound},
    },
    stateful::elasticsearch::WithElasticsearch,
};
use async_trait::async_trait;
use elasticsearch::{Elasticsearch, GetParts::IndexTypeId};
use log::debug;
use serde::{
    de::{DeserializeOwned, IgnoredAny},
    Deserialize,
};
use std::{collections::HashMap, fmt};

/// Public interface of the Locations ES repository.
#[async_trait]
pub(crate) trait LocationsElasticRepository {
    /// Get [ElasticCity] from Elasticsearch given its `id`. Async.
    async fn get_city(&self, id: u64) -> Result<ElasticCity, ErrorResponse>;

    /// Get [ElasticRegion] from Elasticsearch given its `id`. Async.
    async fn get_region(&self, id: u64) -> Result<ElasticRegion, ErrorResponse>;
}

/// City entity mapped from Elasticsearch.
#[allow(non_snake_case)]
#[derive(Debug, Deserialize)]
pub(crate) struct ElasticCity {
    pub(crate) centroid: [f64; 2],
    pub(crate) countryISO: String,
    geometry: IgnoredAny, // Consume the key so that it doesn't appear in `names`, but don't parse.
    pub(crate) id: u64,
    pub(crate) regionId: u64,

    #[serde(flatten)] // captures rest of fields, see https://serde.rs/attr-flatten.html
    pub(crate) names: HashMap<String, String>,
}

/// Region entity mapped from Elasticsearch.
#[allow(non_snake_case)]
#[derive(Debug, Deserialize)]
pub(crate) struct ElasticRegion {
    pub(crate) centroid: [f64; 2],
    pub(crate) countryISO: String,
    geometry: IgnoredAny, // Consume the key so that it doesn't appear in `names`, but don't parse.
    pub(crate) id: u64,

    #[serde(flatten)] // captures rest of fields, see https://serde.rs/attr-flatten.html
    pub(crate) names: HashMap<String, String>,
}

/// Implementation of [LocationsElasticRepository] for any `T` that implements [WithElasticsearch].
#[async_trait]
impl<S: WithElasticsearch + Send + Sync> LocationsElasticRepository for S {
    async fn get_city(&self, id: u64) -> Result<ElasticCity, ErrorResponse> {
        get_entity(self.elasticsearch(), id, "city", "City").await
    }

    async fn get_region(&self, id: u64) -> Result<ElasticRegion, ErrorResponse> {
        get_entity(self.elasticsearch(), id, "region", "Region").await
    }
}

async fn get_entity<T: fmt::Debug + DeserializeOwned>(
    es: &Elasticsearch,
    id: u64,
    index_name: &str,
    entity_name: &str,
) -> Result<T, ErrorResponse> {
    let response = es.get(IndexTypeId(index_name, "_source", &id.to_string())).send().await?;

    let response_code = response.status_code().as_u16();
    debug!("Elasticsearch response status: {}.", response_code);
    if response_code == 404 {
        return Err(NotFound(format!("{}#{} not found.", entity_name, id)));
    }
    if response_code != 200 {
        return Err(InternalServerError(format!("ES response {}.", response_code)));
    }

    let response_body = response.read_body::<T>().await?;
    debug!("Elasticsearch response body: {:?}.", response_body);

    Ok(response_body)
}
