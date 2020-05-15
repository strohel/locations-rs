//! Little proof-of-concept webservice in Rust, using Actix web framework.

// Make writing "unsafe" in code a compilation error. We should not need unsafe at all.
#![forbid(unsafe_code)]
// Warn on generally recommended lints that are not enabled by default.
#![warn(future_incompatible, rust_2018_idioms, unused, macro_use_extern_crate)]
// Warn when we write more code than necessary.
#![warn(unused_lifetimes, single_use_lifetimes, unreachable_pub, trivial_casts)]
// Warn when we don't implement (derive) commonly needed traits. May be too strict.
#![warn(missing_copy_implementations, missing_debug_implementations)]
// Turn on some extra Clippy (Rust code linter) warnings. Run `cargo clippy`.
#![warn(clippy::all)]

use crate::stateful::elasticsearch::WithElastic;
use actix_web::{
    http::StatusCode,
    middleware::{errhandlers::ErrorHandlers, Logger},
    web::{get, Data},
    App, HttpServer,
};
use elasticsearch::Elasticsearch;
use env_logger::DEFAULT_FILTER_ENV;
use std::{env, io};

mod error;
/// Module for endpoint handlers (also known as controllers). This module also serves as an HTTP
/// REST API documentation for clients.
mod handlers {
    pub(crate) mod city;
}
mod response;
/// Module for stateless services (that may depend on stateful ones from [stateful] module).
mod services {
    pub(crate) mod locations_repo;
}
/// Module for "stateful" services - those that need initialisation on startup and a living state.
mod stateful {
    pub(crate) mod elasticsearch;
}

#[actix_rt::main]
async fn main() -> io::Result<()> {
    // Set default log level to info and then init logging.
    if env::var(DEFAULT_FILTER_ENV).is_err() {
        env::set_var(DEFAULT_FILTER_ENV, "info");
    }
    pretty_env_logger::init_timed();

    let app_state_data = Data::new(AppState::new().await);
    HttpServer::new(move || {
        App::new()
            .app_data(app_state_data.clone())
            .wrap(
                ErrorHandlers::new()
                    .handler(StatusCode::BAD_REQUEST, error::json_error)
                    .handler(StatusCode::NOT_FOUND, error::json_error)
                    .handler(StatusCode::INTERNAL_SERVER_ERROR, error::json_error),
            )
            .wrap(Logger::default())
            .route("/city/v1/get", get().to(handlers::city::get))
            .route("/city/v1/featured", get().to(handlers::city::featured))
            .route("/city/v1/search", get().to(handlers::city::search))
    })
    .bind("0.0.0.0:8080")?
    .run()
    .await
}

struct AppState {
    elasticsearch: Elasticsearch,
}

impl AppState {
    async fn new() -> Self {
        let elasticsearch = stateful::elasticsearch::new().await;

        Self { elasticsearch }
    }
}

impl WithElastic for AppState {
    fn elasticsearch(&self) -> &Elasticsearch {
        &self.elasticsearch
    }
}
