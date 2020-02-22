// Make writing "unsafe" in code a compilation error. We should not need unsafe at all.
#![forbid(unsafe_code)]
// Turn on some extra Clippy (Rust code linter) warnings. Run `cargo clippy`.
#![warn(clippy::all, clippy::nursery)]

use async_std;
use env_logger::DEFAULT_FILTER_ENV;
use std::{env, io};

#[async_std::main]
async fn main() -> io::Result<()> {
    // Set default log level to info and then init logging.
    if env::var(DEFAULT_FILTER_ENV).is_err() {
        env::set_var(DEFAULT_FILTER_ENV, "info");
    }
    pretty_env_logger::init();

    let mut app = tide::new();
    app.middleware(tide::middleware::RequestLogger::new());
    app.at("/").get(|_| async move { "Hello, world!" });
    app.listen("127.0.0.1:8080").await
}
