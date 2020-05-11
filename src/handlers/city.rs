//! Handlers for `/city/*` endpoints.

use crate::{
    response::{ErrorResponse, ErrorResponse::BadRequest, JsonResult},
    services::locations_repo::{ElasticCity, Language, LocationsElasticRepository},
    stateful::elasticsearch::WithElastic,
    AppState,
};
use actix_web::web::{Data, Json, Query};
use futures::{stream::FuturesOrdered, TryStreamExt};
use serde::{Deserialize, Serialize};

/// Query for the `/city/v1/get` endpoint.
#[derive(Deserialize)]
pub(crate) struct CityQuery {
    /// Id of the city to get, positive integer.
    id: u64,
    language: Language,
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

    Ok(Json(es_city.into_resp(app.get_ref(), query.language).await?))
}

/// Query for the `/city/v1/featured` endpoint.
#[derive(Deserialize)]
pub(crate) struct FeaturedQuery {
    language: Language,
}

/// A list of `City` API entities.
#[derive(Serialize)]
pub(crate) struct MultiCityResponse {
    cities: Vec<CityResponse>,
}

/// The `/city/v1/featured` endpoint. HTTP request: [`FeaturedQuery`], response: [`MultiCityResponse`].
///
/// Returns a list of all featured cities.
pub(crate) async fn featured(
    query: Query<FeaturedQuery>,
    app: Data<AppState>,
) -> JsonResult<MultiCityResponse> {
    let locations_es_repo = LocationsElasticRepository(app.get_ref());
    let es_cities = locations_es_repo.get_featured_cities().await?;

    // Fetch needed regions concurrently, maintaining order. Somewhat redundant with region cache.
    let city_futures: FuturesOrdered<_> =
        es_cities.into_iter().map(|it| it.into_resp(app.get_ref(), query.language)).collect();

    Ok(Json(MultiCityResponse { cities: city_futures.try_collect().await? }))
}

impl ElasticCity {
    /// Transform ElasticCity into CityResponse, fetching the region.
    async fn into_resp<T: WithElastic>(
        self,
        app: &T,
        language: Language,
    ) -> Result<CityResponse, ErrorResponse> {
        let locations_es_repo = LocationsElasticRepository(app);
        let es_region = locations_es_repo.get_region(self.regionId).await?;

        let name_key = language.name_key();
        let name = self.names.get(&name_key).ok_or_else(|| BadRequest(name_key.clone()))?;
        let region_name = es_region.names.get(&name_key).ok_or_else(|| BadRequest(name_key))?;

        Ok(CityResponse {
            id: self.id,
            isFeatured: self.isFeatured,
            countryIso: self.countryIso,
            name: name.to_string(),
            regionName: region_name.to_string(),
        })
    }
}
