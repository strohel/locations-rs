//! Elasticsearch client with a connection pool.

use elasticsearch::{http::transport::Transport, Elasticsearch};
use log::info;
use std::env;

/// Trait to be implemented by application states that contain stateful Elasticsearch client.
pub(crate) trait WithElastic {
    /// Get reference to stateful Elasticsearch client.
    fn elasticsearch(&self) -> &Elasticsearch;
}

/// Construct Elasticsearch client. Reads `GOOUT_ELASTIC_HOST`, `GOOUT_ELASTIC_PORT` env variables.
///
/// # Panics
///
/// Panics if the env variables are not set.
/// Panics if it is not possible to ping Elasticsearch server using given coordinates.
pub(crate) async fn new() -> Elasticsearch {
    let es_url = format!(
        "http://{}:{}/",
        env::var("GOOUT_ELASTIC_HOST").expect("GOOUT_ELASTIC_HOST env variable"),
        env::var("GOOUT_ELASTIC_PORT").expect("GOOUT_ELASTIC_PORT env variable")
    );
    let es_transport = Transport::single_node(&es_url).unwrap();
    let elasticsearch = Elasticsearch::new(es_transport);

    let es_result = elasticsearch.ping().send().await;
    let es_resp = es_result.map_err(|e| format!("Cannot ping Elasticsearch: {}.", e)).unwrap();
    info!("Elasticsearch ping status: {}.", es_resp.status_code());

    elasticsearch
}
