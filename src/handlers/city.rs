//! Handlers for /city/* endpoints.

use crate::{handlers::IntoOkResponse, Request};
use serde::{Deserialize, Serialize};

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

    let city = CityResponse {
        country_iso: "CZ".to_string(),
        id: query.id,
        is_featured: true,
        name: "Synthesised City".to_string(),
        region_name: "Fake Region".to_string(),
    };
    city.into_ok_response()
}
