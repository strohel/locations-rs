//! Handlers for /city/* endpoints.

use crate::{handlers::IntoOkResponse, Request};
use elasticsearch::GetParts;
use log::{error, info};
use serde::{Deserialize, Serialize};
use tide::ResultExt;

/// Query for the `/city/v1/get` endpoint.
#[derive(Deserialize)]
struct CityQuery {
    id: u64,
    language: String, // TODO: serde can probably limit to 2 chars
}

/// All city endpoints respond with this payload (or a composition of it).
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct CityResponse {
    #[serde(rename = "countryISO")]
    country_iso: String,
    id: u64,
    is_featured: bool,
    name: String,
    region_name: String,
}

/// The `/city/v1/get` endpoint. HTTP input: [CityQuery], output: [CityResponse].
pub(crate) async fn get(req: Request) -> tide::Result {
    let query: CityQuery = req.query()?;

    let es = &req.state().elasticsearch;
    let es_response =
        es.get(GetParts::IndexId("city", &query.id.to_string())).send().await.server_err()?;

    let es_resp_code = es_response.status_code().as_u16();
    info!("Elasticsearch response status: {}.", es_resp_code);
    if es_resp_code == 404 {
        return Ok(tide::Response::new(404).body_string(format!("City#{} not found.\n", query.id)));
    }
    if es_resp_code != 200 {
        return Ok(tide::Response::new(500).body_string(format!("ES response {}.\n", es_resp_code)));
    }

    let response_body_res = es_response.read_body::<ElasticGetResponse<ElasticCity>>().await;
    let response_body = response_body_res
        .map_err(|e| {
            error!("Failed to read ES response: {}", e);
            e
        })
        .server_err()?;
    info!("Elasticsearch response body: {:?}.", response_body);

    let es_city = response_body._source;
    let city = CityResponse {
        country_iso: es_city.country_iso,
        id: es_city.id,
        is_featured: es_city.is_featured,
        name: match query.language.as_str() {
            "cs" => es_city.name_cs,
            "de" => es_city.name_de,
            "en" => es_city.name_en,
            "pl" => es_city.name_pl,
            "sk" => es_city.name_sk,
            _ => es_city.name_en,
        },
        region_name: format!("Region#{}", es_city.region_id), // TODO
    };
    city.into_ok_response()
}

#[derive(Debug, Deserialize)]
struct ElasticGetResponse<T> {
    _source: T,
}

#[derive(Debug, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ElasticCity {
    #[serde(rename = "countryISO")]
    country_iso: String,
    id: u64,
    #[serde(default)] // TODO: isFeatured is not yet in Elastic, fall-back to default of false
    is_featured: bool,
    #[serde(rename = "name.cs")] // TODO: serde surely has better way to do this
    name_cs: String,
    #[serde(rename = "name.de")]
    name_de: String,
    #[serde(rename = "name.en")]
    name_en: String,
    #[serde(rename = "name.pl")]
    name_pl: String,
    #[serde(rename = "name.sk")]
    name_sk: String,
    region_id: u64,
}
