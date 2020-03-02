//! Handlers for /city/* endpoints.

use crate::{
    response::{ErrorResponse::BadRequest, JsonResponse, JsonResult},
    services::locations_repo::LocationsElasticRepository,
    Request,
};
use serde::{Deserialize, Serialize};

/// Query for the `/city/v1/get` endpoint.
#[derive(Deserialize)]
struct CityQuery {
    id: u64,
    language: String, // TODO: serde can probably limit to 2 chars
}

/// All city endpoints respond with this payload (or a composition of it).
#[allow(non_snake_case)]
#[derive(Serialize)]
pub(crate) struct CityResponse {
    countryISO: String,
    id: u64,
    isFeatured: bool,
    name: String,
    regionName: String,
}

/// The `/city/v1/get` endpoint. HTTP input: [CityQuery].
pub(crate) async fn get(req: Request) -> JsonResult<CityResponse> {
    let query: CityQuery = req.query()?;

    let locations_es_repo = req.state(); // can be typed to `impl LocationsElasticRepository` in future Rust
    let es_city = locations_es_repo.get_city(query.id).await?;

    let name_key = format!("name.{}", query.language);
    let name = es_city.names.get(&name_key).ok_or_else(|| BadRequest(name_key))?;

    let city = CityResponse {
        countryISO: es_city.countryISO,
        id: es_city.id,
        isFeatured: false, // TODO: isFeatured is not yet in Elastic
        name: name.to_string(),
        regionName: format!("Region#{}", es_city.regionId), // TODO
    };
    Ok(JsonResponse(city))
}
