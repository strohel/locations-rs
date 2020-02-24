//! Little proof-of-concept webservice in Rust, using experimental [tide] web framework.

// Make writing "unsafe" in code a compilation error. We should not need unsafe at all.
#![forbid(unsafe_code)]
// Warn on generally recommended lints that are not enabled by default.
#![warn(future_incompatible, rust_2018_idioms, unused, macro_use_extern_crate)]
// Warn when we write more code than necessary.
#![warn(unused_lifetimes, single_use_lifetimes, unreachable_pub, trivial_casts)]
// Warn when we don't implement (derive) commonly needed traits. May be too strict.
#![warn(missing_copy_implementations, missing_debug_implementations)]
// Turn on some extra Clippy (Rust code linter) warnings. Run `cargo clippy`.
#![warn(clippy::all, clippy::nursery)]

use elasticsearch::{http::transport::Transport, Elasticsearch};
use env_logger::DEFAULT_FILTER_ENV;
use log::info;
use std::{env, io};

mod handlers;

/// Convenience type alias to be used by handlers.
type Request = tide::Request<AppState>;

#[tokio::main]
async fn main() -> io::Result<()> {
    // Set default log level to info and then init logging.
    if env::var(DEFAULT_FILTER_ENV).is_err() {
        env::set_var(DEFAULT_FILTER_ENV, "info");
    }
    pretty_env_logger::init();

    let mut app = tide::with_state(AppState::new().await);
    app.middleware(tide::middleware::RequestLogger::new());

    app.at("/city/v1/get").get(handlers::city::get);

    app.at("/").all(handlers::fallback::not_found);
    app.at("/*").all(handlers::fallback::not_found);

    app.listen("127.0.0.1:8080").await
}

struct AppState {
    elasticsearch: Elasticsearch,
}

impl AppState {
    async fn new() -> Self {
        let es_url = format!(
            "http://{}:{}/",
            env::var("GOOUT_ELASTIC_HOST").unwrap(),
            env::var("GOOUT_ELASTIC_PORT").unwrap()
        );
        let es_transport = Transport::single_node(&es_url).unwrap();
        let elasticsearch = Elasticsearch::new(es_transport);

        let es_result = elasticsearch.ping().send().await;
        let es_resp = es_result.map_err(|e| format!("Cannot ping Elasticsearch: {}.", e)).unwrap();
        info!("Elasticsearch ping status: {}.", es_resp.status_code());

        Self { elasticsearch }
    }
}
