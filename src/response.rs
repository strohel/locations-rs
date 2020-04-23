//! OK and error response types to be used by endpoints.

use actix_web::{http::StatusCode, web::Json, ResponseError};

/// Result type to be used by endpoints. Either OK [Json] or error [ErrorResponse].
pub(crate) type JsonResult<T> = Result<Json<T>, ErrorResponse>;

/// Possible error endpoint responses.
#[derive(Debug, thiserror::Error)]
pub(crate) enum ErrorResponse {
    /// HTTP 400 Bad Request: client sent something wrong.
    #[error("Bad Request: {0}")]
    BadRequest(String),
    /// HTTP 404 Not Found: this path or entity does not exist.
    #[error("Not Found: {0}")]
    NotFound(String),
    /// HTTP 500 Internal Server Error: something went real wrong on the server.
    #[error("Internal Server Error: {0}")]
    InternalServerError(String),
}

/// Make actix-web understand our error responses.
impl ResponseError for ErrorResponse {
    fn status_code(&self) -> StatusCode {
        match self {
            Self::BadRequest(_) => StatusCode::BAD_REQUEST,
            Self::NotFound(_) => StatusCode::NOT_FOUND,
            Self::InternalServerError(_) => StatusCode::INTERNAL_SERVER_ERROR,
        }
    }
}

/// Convert Elasticsearch errors into internal server errors.
impl From<elasticsearch::Error> for ErrorResponse {
    fn from(err: elasticsearch::Error) -> Self {
        Self::InternalServerError(format!("Elasticsearch error: {}", err))
    }
}
