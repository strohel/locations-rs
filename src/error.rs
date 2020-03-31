//! Module that implements our JSON error handling for actix-web.

use actix_web::{
    body::ResponseBody,
    dev::{Body, ServiceResponse},
    middleware::errhandlers::ErrorHandlerResponse,
    HttpResponse,
};
use serde::Serialize;

/// Process errors from all handlers including the default handler, convert them to JSON.
pub(crate) fn json_error(
    mut sres: ServiceResponse<Body>,
) -> Result<ErrorHandlerResponse<Body>, actix_web::Error> {
    let response = sres.response_mut();
    let body = match response.take_body() {
        ResponseBody::Body(body) | ResponseBody::Other(body) => body,
    };

    // Use existing body as message, otherwise just pretty-printed HTTP code.
    let message = match body {
        Body::None | Body::Empty => response.status().to_string(),
        Body::Bytes(bytes) => String::from_utf8(bytes.to_vec()).expect("valid UTF-8 we've encoded"),
        Body::Message(_) => panic!("did not expect Body::Message()"),
    };

    #[derive(Serialize)]
    struct ErrorPayload {
        message: String,
    }

    let body = serde_json::to_string(&ErrorPayload { message })?;
    *response = HttpResponse::build(response.status()).content_type("application/json").body(body);
    Ok(ErrorHandlerResponse::Response(sres))
}
