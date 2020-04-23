//! Handlers for `/city/*` endpoints.

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
    /// Id of the city to get, positive integer.
    id: u64,
    /// Two-letter ISO 639-1 lowercase language code for response localization.
    language: String,
}

/// `City` API entity. All city endpoints respond with this payload (or a composition of it).
#[allow(non_snake_case)]
#[derive(Serialize)]
pub(crate) struct CityResponse {
    /// Id of the city, e.g. `123`.
    id: u64,
    /// Whether this city is marked as *featured*, e.g. `false`.
    isFeatured: bool,
    /// ISO 3166-1 alpha-2 country code, or a custom 4-letter code, e.g. `"CZ"`.
    countryIso: String,
    /// E.g. `"Plzeň"`.
    name: String,
    /// E.g. `"Plzeňský kraj"`.
    regionName: String,
}

/// The `/city/v1/get` endpoint. HTTP request: [`CityQuery`], response: [`CityResponse`].
///
/// Get city of given ID localized to given language.
pub(crate) async fn get(query: Query<CityQuery>, app: Data<AppState>) -> JsonResult<CityResponse> {
    let locations_es_repo = LocationsElasticRepository(app.get_ref());
    let es_city = locations_es_repo.get_city(query.id).await?;
    let es_region = locations_es_repo.get_region(es_city.regionId).await?;

    let name_key = format!("name.{}", query.language);
    let name = es_city.names.get(&name_key).ok_or_else(|| BadRequest(name_key.clone()))?;
    let region_name = es_region.names.get(&name_key).ok_or_else(|| BadRequest(name_key))?;

    let city = CityResponse {
        id: es_city.id,
        isFeatured: es_city.isFeatured,
        countryIso: es_city.countryIso,
        name: name.to_string(),
        regionName: region_name.to_string(),
    };
    Ok(Json(city))
}
