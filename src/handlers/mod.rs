//! Module for endpoint handlers (also known as controllers), also contains utils for handlers.

use serde::Serialize;
use tide::ResultExt;

pub(crate) mod city;
pub(crate) mod fallback;

/// Helper trait so that endpoints can conveniently convert compatible types to [tide::Result].
trait IntoOkResponse {
    fn into_ok_response(self) -> tide::Result;
}

/// Ability to convert anything serializable by serde into [tide::Result].
impl<T: Serialize + Send> IntoOkResponse for T {
    fn into_ok_response(self) -> tide::Result {
        tide::Response::new(200).body_json(&self).server_err()
    }
}
