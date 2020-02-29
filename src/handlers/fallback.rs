//! Fallback handler, as [tide] provides only very rudimentary fallback (with no body text).

use crate::{response::ErrorResponse, Request};

pub(crate) async fn not_found(req: Request) -> ErrorResponse {
    ErrorResponse::NotFound(format!("Resource {} does not exist.", req.uri()))
}
