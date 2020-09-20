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
// Rocket v0.4 needs this nightly feature
#![feature(decl_macro)]

use crate::stateful::elasticsearch::WithElastic;
use elasticsearch::Elasticsearch;
use env_logger::DEFAULT_FILTER_ENV;
use log::info;
use rocket::{catchers, State};
use rocket_okapi::{
    handlers::RedirectHandler,
    routes_with_openapi,
    swagger_ui::{make_swagger_ui, SwaggerUIConfig},
};
use std::{cell::RefCell, env, future::Future, rc::Rc, thread};
use tokio::runtime::{self, Runtime};

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

fn main() {
    // Set default log level to info and then init logging.
    if env::var(DEFAULT_FILTER_ENV).is_err() {
        env::set_var(DEFAULT_FILTER_ENV, "info");
    }
    pretty_env_logger::init_timed();

    let app_state = App::new();

    rocket::ignite()
        .manage(app_state)
        .register(catchers![response::not_found, response::internal_server_error])
        .mount(
            "/",
            routes_with_openapi![
                handlers::city::get,
                handlers::city::featured,
                handlers::city::search,
                handlers::city::closest,
                handlers::city::associated_featured,
            ],
        )
        // I was unable to customize OpenAPI spec location, so just redirect to it:
        .mount("/", vec![RedirectHandler::to("/openapi.json").into_route("/api-docs")])
        .mount(
            "/docs",
            make_swagger_ui(&SwaggerUIConfig {
                url: "/openapi.json".to_owned(),
                ..Default::default()
            }),
        )
        .launch();
}

struct App {}

thread_local! {
    // RefCell because Runtime::block_on() needs mutable reference.
    static RT: RefCell<Runtime> = RefCell::new(create_async_rt());
    // Rc because we want the Elasticsearch reference to escape LocalKey::with().
    static ES: Rc<Elasticsearch> = Rc::new(stateful::elasticsearch::new_pingless());
}

type AppState<'a> = State<'a, App>;

impl App {
    fn new() -> Self {
        // Don't use thread-local variables here - main thread is not reused for Rocket workers.
        create_async_rt().block_on(stateful::elasticsearch::new()); // Ping Elastic or panic.

        Self {}
    }

    /// Run given future in async runtime and block current thread until it resolves.
    fn block_on<F: Future>(&self, future: F) -> F::Output {
        RT.with(|rt_cell| rt_cell.borrow_mut().block_on(future))
    }
}

fn create_async_rt() -> Runtime {
    info!("Creating basic Tokio runtime from {:?}", thread::current());
    runtime::Builder::new()
        .basic_scheduler()
        .enable_all()
        .build()
        .expect("Tokio runtime can be created")
}

impl WithElastic for AppState<'_> {
    fn elasticsearch(&self) -> Rc<Elasticsearch> {
        ES.with(|es| Rc::clone(es))
    }
}
