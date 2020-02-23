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

use async_std;
use env_logger::DEFAULT_FILTER_ENV;
use std::{env, io};

mod errors;

type Request = tide::Request<()>;

#[async_std::main]
async fn main() -> io::Result<()> {
    // Set default log level to info and then init logging.
    if env::var(DEFAULT_FILTER_ENV).is_err() {
        env::set_var(DEFAULT_FILTER_ENV, "info");
    }
    pretty_env_logger::init();

    let mut app = tide::new();
    app.middleware(tide::middleware::RequestLogger::new());

    app.at("/").all(errors::fallback_endpoint);
    app.at("/*").all(errors::fallback_endpoint);

    app.listen("127.0.0.1:8080").await
}
