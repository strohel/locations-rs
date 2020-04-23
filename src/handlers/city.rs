//! Handlers for /city/* endpoints.

use crate::{
    response::{ErrorResponse::BadRequest, JsonResult},
    services::locations_repo::LocationsElasticRepository,
    AppState,
};
use actix_web::web::{Data, Json, Query};
use serde::{Deserialize, Serialize};

/// Query for the `/city/v1/get` endpoint.
#[derive(Deserialize)]
pub(crate) struct CityQuery {
    id: u64,
    language: String,
}

/// All city endpoints respond with this payload (or a composition of it).
#[allow(non_snake_case)]
#[derive(Serialize)]
pub(crate) struct CityResponse {
    countryIso: String,
    id: u64,
    isFeatured: bool,
    name: String,
    regionName: String,
}

/// The `/city/v1/get` endpoint. Request: [CityQuery], response: [CityResponse].
pub(crate) async fn get(query: Query<CityQuery>, app: Data<AppState>) -> JsonResult<CityResponse> {
    let locations_es_repo = LocationsElasticRepository(app.get_ref());
    let es_city = locations_es_repo.get_city(query.id).await?;
    let es_region = locations_es_repo.get_region(es_city.regionId).await?;

    let name_key = format!("name.{}", query.language);
    let name = es_city.names.get(&name_key).ok_or_else(|| BadRequest(name_key.clone()))?;
    let region_name = es_region.names.get(&name_key).ok_or_else(|| BadRequest(name_key))?;

    let city = CityResponse {
        countryIso: es_city.countryIso,
        id: es_city.id,
        isFeatured: es_city.isFeatured,
        name: name.to_string(),
        regionName: region_name.to_string(),
    };
    Ok(Json(city))
}
