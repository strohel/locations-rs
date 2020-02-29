//! Handlers for /city/* endpoints.

use crate::{
    response::{
        ErrorResponse::{InternalServerError, NotFound},
        JsonResponse, JsonResult,
    },
    Request,
};
use elasticsearch::GetParts;
use log::info;
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
    let city = CityResponse {
        countryISO: es_city.countryISO,
        id: es_city.id,
        isFeatured: false, // TODO: isFeatured is not yet in Elastic
        name: match query.language.as_str() {
            "cs" => es_city.name_cs,
            "de" => es_city.name_de,
            "en" => es_city.name_en,
            "pl" => es_city.name_pl,
            "sk" => es_city.name_sk,
            _ => es_city.name_en,
        },
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
    countryISO: String,
    id: u64,
    #[serde(rename = "name.cs")]
    name_cs: String,
    #[serde(rename = "name.de")]
    name_de: String,
    #[serde(rename = "name.en")]
    name_en: String,
    #[serde(rename = "name.pl")]
    name_pl: String,
    #[serde(rename = "name.sk")]
    name_sk: String,
    regionId: u64,
}
