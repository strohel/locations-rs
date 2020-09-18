//! OK and error response types to be used by endpoints.

use rocket::{
    catch,
    http::Status,
    request::FormParseError,
    response,
    response::{status::Custom, Responder},
    Request,
};
use rocket_contrib::json::Json;
use serde::Serialize;
use validator::ValidationErrors;

/// Convenience alias for [Result] whose error is [ErrorResponse], to be used by supportive code.
pub(crate) type HandlerResult<T> = Result<T, ErrorResponse>;

/// Result type to be used by endpoints. Either OK [Json] or error [ErrorResponse].
pub(crate) type JsonResult<T> = HandlerResult<Json<T>>;

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

/// Make Rocket understand our error responses.
impl<'r> Responder<'r> for ErrorResponse {
    fn respond_to(self, req: &Request<'_>) -> response::Result<'r> {
        let http_status = match self {
            Self::BadRequest(_) => Status::BadRequest,
            Self::NotFound(_) => Status::NotFound,
            Self::InternalServerError(_) => Status::InternalServerError,
        };

        #[derive(Serialize)]
        struct ErrorPayload {
            message: String,
        }

        let payload = ErrorPayload { message: self.to_string() };
        let response = Custom(http_status, Json(payload));
        response.respond_to(req)
    }
}

/// Convert Elasticsearch errors into internal server errors.
impl From<elasticsearch::Error> for ErrorResponse {
    fn from(err: elasticsearch::Error) -> Self {
        Self::InternalServerError(format!("Elasticsearch error: {}", err))
    }
}

/// Convert from [validator] errors into bad requests.
impl From<ValidationErrors> for ErrorResponse {
    fn from(err: ValidationErrors) -> Self {
        Self::BadRequest(err.to_string())
    }
}

impl<'f> From<FormParseError<'f>> for ErrorResponse {
    fn from(err: FormParseError<'f>) -> Self {
        Self::BadRequest(format!("{:?}", err))
    }
}

#[catch(404)]
pub(crate) fn not_found(req: &Request<'_>) -> ErrorResponse {
    ErrorResponse::NotFound(req.uri().to_string())
}

#[catch(500)]
pub(crate) fn internal_server_error() -> ErrorResponse {
    ErrorResponse::InternalServerError("Something went wrong.".into())
}
