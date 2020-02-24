//! Handlers for /city/* endpoints.

use crate::{handlers::IntoOkResponse, Request};
use elasticsearch::GetParts;
use log::info;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tide::ResultExt;

/// Query for the `/city/v1/get` endpoint.
#[derive(Deserialize)]
struct CityQuery {
    id: u64,
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

    let es_resp_body = es_response.read_body::<Value>().await.server_err()?;
    info!("Elasticsearch response body: {:}.", es_resp_body);

    let city = CityResponse {
        country_iso: "CZ".to_string(),
        id: query.id,
        is_featured: true,
        name: "Synthesised City".to_string(),
        region_name: "Fake Region".to_string(),
    };
    city.into_ok_response()
}
