use crate::Request;
use http::StatusCode;
use log::warn;
use tide::IntoResponse;

pub(crate) async fn fallback_endpoint(req: Request) -> impl IntoResponse {
    warn!("Responding HTTP 404 Not Found to '{}'.", req.uri());

    format!("Resource {} does not exist.\n", req.uri()).with_status(StatusCode::NOT_FOUND)
}
