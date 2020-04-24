//! Stateless Locations repository backed by Elasticsearch.

use crate::{
    response::{ErrorResponse, ErrorResponse::NotFound},
    stateful::elasticsearch::WithElastic,
};
use actix_web::http::StatusCode;
use dashmap::DashMap;
use elasticsearch::{GetParts::IndexTypeId, SearchParts::Index};
use log::debug;
use once_cell::sync::Lazy;
use serde::{de::DeserializeOwned, Deserialize};
use serde_json::json;
use std::{collections::HashMap, fmt};

const REGION_INDEX: &str = "region";
const CITY_INDEX: &str = "city";
const EXCLUDED_FIELDS: &[&str] = &["centroid", "geometry"];

/// Repository of Elastic City, Region Locations entities. Thin wrapper around app state.
pub(crate) struct LocationsElasticRepository<'a, S: WithElastic>(pub(crate) &'a S);

// Actual implementation of Locations repository on any app state that impleents [WithElasticsearch].
impl<S: WithElastic> LocationsElasticRepository<'_, S> {
    /// Get [ElasticCity] from Elasticsearch given its `id`. Async.
    pub(crate) async fn get_city(&self, id: u64) -> Result<ElasticCity, ErrorResponse> {
        self.get_entity(id, CITY_INDEX, "City").await
    }

    /// Get [ElasticRegion] from Elasticsearch given its `id`. Async.
    pub(crate) async fn get_region(&self, id: u64) -> Result<ElasticRegion, ErrorResponse> {
        static CACHE: Lazy<DashMap<u64, ElasticRegion>> = Lazy::new(DashMap::new);

        if let Some(record) = CACHE.get(&id) {
            return Ok(record.value().clone());
        }

        let entity: ElasticRegion = self.get_entity(id, REGION_INDEX, "Region").await?;
        CACHE.insert(id, entity.clone());
        Ok(entity)
    }

    /// Get a list of featured cities. Async.
    pub(crate) async fn get_featured_cities(&self) -> Result<Vec<ElasticCity>, ErrorResponse> {
        let es = self.0.elasticsearch();

        let response = es
            .search(Index(&[CITY_INDEX]))
            .body(json!({
                "query": {
                    "term": {
                        "isFeatured": true,
                    }
                }
            }))
            ._source_excludes(EXCLUDED_FIELDS)
            .size(1000)
            .send()
            .await?
            .error_for_status_code()?;
        let response_body = response.read_body::<SearchResponse<ElasticCity>>().await?;
        debug!("Elasticsearch response body: {:?}.", response_body);

        Ok(response_body.hits.hits.into_iter().map(|hit| hit._source).collect())
    }

    async fn get_entity<T: fmt::Debug + DeserializeOwned>(
        &self,
        id: u64,
        index_name: &str,
        entity_name: &str,
    ) -> Result<T, ErrorResponse> {
        let es = self.0.elasticsearch();

        let response = es
            .get(IndexTypeId(index_name, "_source", &id.to_string()))
            ._source_excludes(EXCLUDED_FIELDS)
            .send()
            .await?;

        if response.status_code() == StatusCode::NOT_FOUND {
            return Err(NotFound(format!("{}#{} not found.", entity_name, id)));
        }

        response.error_for_status_code_ref()?;
        let response_body = response.read_body::<T>().await?;
        debug!("Elasticsearch response body: {:?}.", response_body);

        Ok(response_body)
    }
}

/// City entity mapped from Elasticsearch.
#[allow(non_snake_case)]
#[derive(Debug, Deserialize)]
pub(crate) struct ElasticCity {
    pub(crate) id: u64,
    pub(crate) regionId: u64,
    #[serde(default)] // Default to false as isFeatured is not filled in for non-featured cities.
    pub(crate) isFeatured: bool,
    pub(crate) countryIso: String,

    #[serde(flatten)] // captures rest of fields, see https://serde.rs/attr-flatten.html
    pub(crate) names: HashMap<String, String>,
}

/// Region entity mapped from Elasticsearch.
#[allow(non_snake_case)]
#[derive(Clone, Debug, Deserialize)]
pub(crate) struct ElasticRegion {
    pub(crate) id: u64,
    pub(crate) countryIso: String,

    #[serde(flatten)] // captures rest of fields, see https://serde.rs/attr-flatten.html
    pub(crate) names: HashMap<String, String>,
}

#[derive(Debug, Deserialize)]
struct SearchResponse<T> {
    hits: HitsResponse<T>,
}

#[derive(Debug, Deserialize)]
struct HitsResponse<T> {
    hits: Vec<Hit<T>>,
}

#[derive(Debug, Deserialize)]
struct Hit<T> {
    _source: T,
}
