//! Handlers for /city/* endpoints.

use crate::{
    response::{
        ErrorResponse::{BadRequest, InternalServerError, NotFound},
        JsonResponse, JsonResult,
    },
    Request,
};
use elasticsearch::GetParts;
use log::info;
use serde::{de::IgnoredAny, Deserialize, Serialize};
use std::collections::HashMap;

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

    let es = &req.state().elasticsearch;
    let es_response = es.get(GetParts::IndexId("city", &query.id.to_string())).send().await?;

    let es_resp_code = es_response.status_code().as_u16();
    info!("Elasticsearch response status: {}.", es_resp_code);
    if es_resp_code == 404 {
        return Err(NotFound(format!("City#{} not found.", query.id)));
    }
    if es_resp_code != 200 {
        return Err(InternalServerError(format!("ES response {}.", es_resp_code)));
    }

    let response_body = es_response.read_body::<ElasticGetResponse<ElasticCity>>().await?;
    info!("Elasticsearch response body: {:?}.", response_body);

    let es_city = response_body._source;
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

#[derive(Debug, Deserialize)]
struct ElasticGetResponse<T> {
    _source: T,
}

#[allow(non_snake_case)]
#[derive(Debug, Deserialize)]
struct ElasticCity {
    centroid: [f64; 2],
    countryISO: String,
    geometry: IgnoredAny, // Consume the key do that it doesn't appear in `names`, but don't parse.
    id: u64,
    regionId: u64,

    #[serde(flatten)] // captures rest of fields, see https://serde.rs/attr-flatten.html
    names: HashMap<String, String>,
}
