//! Stateless Locations repository backed by Elasticsearch.

use crate::{
    response::{
        ErrorResponse::{InternalServerError, NotFound},
        HandlerResult,
    },
    stateful::elasticsearch::WithElastic,
};
use actix_web::http::StatusCode;
use dashmap::DashMap;
use elasticsearch::{
    http::response::Response as EsResponse, Error as EsError, GetParts::IndexTypeId,
    SearchParts::Index,
};
use log::{debug, error};
use once_cell::sync::Lazy;
use serde::{de::DeserializeOwned, Deserialize, Serialize};
use serde_json::{json, to_string_pretty, Value as JsonValue};
use single::Single;
use std::{collections::HashMap, fmt};
use validator::Validate;
use validator_derive::Validate; // redundant use due to https://github.com/Keats/validator/issues/78

const REGION_INDEX: &str = "region";
const CITY_INDEX: &str = "city";
const EXCLUDED_FIELDS: &[&str] = &["centroid", "geometry", "population"];

/// Language for response localization. Serialized as two-letter ISO 639-1 lowercase language code.
#[derive(Clone, Copy, Debug, Deserialize)]
#[serde(rename_all = "lowercase")]
pub(crate) enum Language {
    CS,
    DE,
    EN,
    PL,
    SK,
}

impl Language {
    pub(crate) fn name_key(self) -> String {
        format!("name.{:?}", self).to_lowercase()
    }
}

/// Simple structure to represent a geo point, with latitude and longitude in decimal degrees.
#[derive(Clone, Copy, Debug, Deserialize, Serialize, Validate)]
pub(crate) struct Coordinates {
    #[validate(range(min = -90.0, max = 90.0))]
    pub(crate) lat: f64,
    #[validate(range(min = -180.0, max = 180.0))]
    pub(crate) lon: f64,
}

impl Coordinates {
    /// Return [GeoJSON](http://geojson.org) representation of these coordinates as [serde_json::Value].
    fn geojson(self) -> JsonValue {
        json!({"type": "Point", "coordinates": [self.lon, self.lat]}) // Yes, it is [lon, lat].
    }
}

/// Repository of Elastic City, Region Locations entities. Thin wrapper around app state.
pub(crate) struct LocationsElasticRepository<'a, S: WithElastic>(pub(crate) &'a S);

// Actual implementation of Locations repository on any app state that impleents [WithElasticsearch].
impl<S: WithElastic> LocationsElasticRepository<'_, S> {
    /// Get [ElasticCity] from Elasticsearch given its `id`. Async.
    pub(crate) async fn get_city(&self, id: u64) -> HandlerResult<ElasticCity> {
        self.get_entity(id, CITY_INDEX, "City").await
    }

    /// Get [ElasticRegion] from Elasticsearch given its `id`. Async.
    pub(crate) async fn get_region(&self, id: u64) -> HandlerResult<ElasticRegion> {
        static CACHE: Lazy<DashMap<u64, ElasticRegion>> = Lazy::new(DashMap::new);

        if let Some(record) = CACHE.get(&id) {
            return Ok(record.value().clone());
        }

        let entity: ElasticRegion = self.get_entity(id, REGION_INDEX, "Region").await?;
        CACHE.insert(id, entity.clone());
        Ok(entity)
    }

    /// Get a list of featured cities. Async.
    pub(crate) async fn get_featured_cities(&self) -> HandlerResult<Vec<ElasticCity>> {
        self.search_city(
            json!({
                "query": {
                    "term": {
                        "isFeatured": true,
                    }
                },
                "sort": [
                    "countryIso",
                    { "population": "desc" },
                ],
            }),
            1000,
        )
        .await
    }

    /// Search for cities. Optionally limit to a country given its ISO code.
    pub(crate) async fn search(
        &self,
        query: &str,
        language: Language,
        country_iso: Option<&str>,
    ) -> HandlerResult<Vec<ElasticCity>> {
        let name_key = language.name_key();

        self.search_city(
            json!({
                "query": {
                    "function_score": {
                        "query": {
                            "bool": {
                                "must": [{
                                    "multi_match": {
                                        "query": query,
                                        "fields": [
                                            // Match against the specified language with diacritics.
                                            // Use the highest boost (8) because these three fields are most specific.
                                            format!("{}.autocomplete^8.0", name_key),
                                            format!("{}.autocomplete._2gram^8.0", name_key),
                                            format!("{}.autocomplete._3gram^8.0", name_key),
                                            // Match against ascii versions of the name to match queries without diacritics.
                                            // Lower boost by factor of two, to prefer cities that matched with diacritics.
                                            format!("{}.autocomplete_ascii^4.0", name_key),
                                            format!("{}.autocomplete_ascii._2gram^4.0", name_key),
                                            format!("{}.autocomplete_ascii._3gram^4.0", name_key),
                                            // Match against all language mutations with diacritics.
                                            // Lower the boost by factor of 4 to prefer matches in specified language.
                                            "name.all.autocomplete^2.0",
                                            "name.all.autocomplete._2gram^2.0",
                                            "name.all.autocomplete._3gram^2.0",
                                            // Match against ascii version of all language mutations.
                                            // Lower the boost by factor of 8 because this is the least specific field.
                                            "name.all.autocomplete_ascii^1.0",
                                            "name.all.autocomplete_ascii._2gram^1.0",
                                            "name.all.autocomplete_ascii._3gram^1.0",
                                        ],
                                        "type": "bool_prefix",
                                    }
                                }],
                                "filter": match country_iso {
                                    Some(iso_code) => json!([{
                                        "term": {
                                            "countryIso": iso_code
                                        }}]),
                                    None => json!([])
                                },
                            }
                        },
                        // Boost cities with higher population.
                        "functions": [{
                            "field_value_factor": {
                                "field": "population",
                                // Take logarithm of the city's population to account for human's logarithmic perception of size.
                                // Add 2 before taking the logarithm to make the score function strictly positive,
                                // because it's multiplied with the MultiMatch score.
                                "modifier": "ln2p",
                                // For missing values assume 500 humans live there.
                                "missing": 500,
                            }
                        }],
                    }
                },
            }),
            10,
        )
        .await
    }

    /// Get a city closest to given geo `coords`, optionally filter by `is_featured`.
    pub(crate) async fn get_closest_city(
        &self,
        coords: Coordinates,
        is_featured: Option<bool>,
    ) -> HandlerResult<ElasticCity> {
        let query = json!({
            "query": {
                "bool": {
                    "must": match is_featured {
                        // Either include all featured cities,
                        Some(is_featured) => json!({"term": {"isFeatured": is_featured}}),
                        // or positively select *all* cities. This needs to be present, because bool
                        // query apparently requires at least one positive match regardless of
                        // `minimum_should_match`.
                        None => json!({"match_all": {}}),
                    },
                    // Boost cities intersecting with `coords`.
                    "should": {
                        "geo_shape": {
                            "geometry": {
                                "shape": coords.geojson()
                            },
                            "boost": 1, // Elastic doesn't seem to add boost from geo query, fix it.
                        }
                    },
                }
            },
            "sort": [
                // First order by score. There will be just 2 distinct values, one for cities with
                // point-in-polygon intersection and second for cities without it.
                "_score",
                // Otherwise order by distance of the city from coords.
                {
                    "_geo_distance": {
                        "centroid": coords
                    }
                },
            ]
        });
        let cities = self.search_city(query, 1).await?;

        // Extract the single city from response. Both no and multiple cities are unexpected.
        cities.into_iter().single().map_err(|e| InternalServerError(e.to_string()))
    }

    async fn get_entity<T: fmt::Debug + DeserializeOwned>(
        &self,
        id: u64,
        index_name: &str,
        entity_name: &str,
    ) -> HandlerResult<T> {
        let es = self.0.elasticsearch();

        let response = es
            .get(IndexTypeId(index_name, "_source", &id.to_string()))
            ._source_excludes(EXCLUDED_FIELDS)
            .send()
            .await?;

        if response.status_code() == StatusCode::NOT_FOUND {
            return Err(NotFound(format!("{}#{} not found.", entity_name, id)));
        }

        let response = self.logged_error_for_status(None, response).await?;
        let response_body = response.json::<T>().await?;
        debug!("Elasticsearch response body: {:?}.", response_body);

        Ok(response_body)
    }

    async fn search_city(&self, body: JsonValue, size: i64) -> HandlerResult<Vec<ElasticCity>> {
        let es = self.0.elasticsearch();

        let response = es
            .search(Index(&[CITY_INDEX]))
            .body(&body)
            ._source_excludes(EXCLUDED_FIELDS)
            .size(size)
            .send()
            .await?;
        let response = self.logged_error_for_status(Some(&body), response).await?;
        let response_body = response.json::<SearchResponse<ElasticCity>>().await?;
        debug!("Elasticsearch response body: {:?}.", response_body);

        Ok(response_body.hits.hits.into_iter().map(|hit| hit._source).collect())
    }

    async fn logged_error_for_status(
        &self,
        body: Option<&JsonValue>,
        response: EsResponse,
    ) -> Result<EsResponse, EsError> {
        // This is somewhat convoluted to satisfy Rust lifetime rules. As response.text() takes
        // ownership of the response, we in turn also need to take its ownership. We need to use
        // error_for_status_code_ref() (rather than the non-_ref variant) for the same reason.
        match response.error_for_status_code_ref() {
            Ok(_) => Ok(response),
            Err(e) => {
                let request = body.and_then(|val| to_string_pretty(val).ok()).unwrap_or_default();
                let resp_text = response.text().await.unwrap_or_default();
                error!("Elasticsearch: {}. Request:\n{}\nresponse: {}", e, request, resp_text);
                Err(e)
            }
        }
    }
}

/// City entity mapped from Elasticsearch.
#[allow(non_snake_case)]
#[derive(Debug, Deserialize)]
pub(crate) struct ElasticCity {
    pub(crate) id: u64,
    pub(crate) regionId: u64,
    pub(crate) isFeatured: bool,
    pub(crate) countryIso: String,
    pub(crate) timezone: String,

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
