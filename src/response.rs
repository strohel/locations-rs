//! OK and error response types to be used by endpoints.

use http::status::StatusCode;
use log::{log, Level};
use serde::Serialize;
use tide::{IntoResponse, QueryParseError, Response};

/// Result type to be used by endpoints. Either OK [JsonResponse] or error [ErrorResponse].
pub(crate) type JsonResult<T> = Result<JsonResponse<T>, ErrorResponse>;

/// Wrapper for OK endpoint responses.
pub(crate) struct JsonResponse<T: Serialize + Send>(pub(crate) T);

/// Make Tide framework understand our OK responses.
impl<T: Serialize + Send> IntoResponse for JsonResponse<T> {
    fn into_response(self) -> Response {
        Response::new(200)
            .body_json(&self.0)
            .unwrap_or_else(|e| ErrorResponse::from(e).into_response())
    }
}

/// Wrapper for error endpoint responses.
#[derive(Debug, thiserror::Error)]
pub(crate) enum ErrorResponse {
    #[error("Bad Request: {0}")]
    BadRequest(String),
    #[error("Not Found: {0}")]
    NotFound(String),
    #[error("Internal Server Error: {0}")]
    InternalServerError(String),
}

impl ErrorResponse {
    fn status(&self) -> StatusCode {
        match self {
            Self::BadRequest(_) => StatusCode::BAD_REQUEST,
            Self::NotFound(_) => StatusCode::NOT_FOUND,
            Self::InternalServerError(_) => StatusCode::INTERNAL_SERVER_ERROR,
        }
    }

    fn severity(&self) -> Level {
        match self {
            Self::BadRequest(_) | Self::NotFound(_) => Level::Warn,
            Self::InternalServerError(_) => Level::Error,
        }
    }
}

/// Make Tide framework understand our error responses.
impl IntoResponse for ErrorResponse {
    fn into_response(self) -> Response {
        #[derive(Serialize)]
        struct ErrorPayload {
            message: String,
        }

        let status = self.status();
        let message = self.to_string();
        log!(self.severity(), "Responding with HTTP {}: {}", status, message);
        JsonResponse(ErrorPayload { message }).with_status(status).into_response()
    }
}

/// Convert Tide query parse error into bad request.
impl From<QueryParseError> for ErrorResponse {
    fn from(err: QueryParseError) -> Self {
        Self::BadRequest(err.to_string())
    }
}

/// Convert Elasticsearch errors into internal server errors.
impl From<elasticsearch::Error> for ErrorResponse {
    fn from(err: elasticsearch::Error) -> Self {
        Self::InternalServerError(format!("Elasticsearch error: {}", err))
    }
}

/// Convert Serde (serialization, deserialization) errors into internal server errors.
impl From<serde_json::Error> for ErrorResponse {
    fn from(err: serde_json::Error) -> Self {
        Self::InternalServerError(format!("Serde JSON error: {}", err))
    }
}
