# locations-rs (Locations Service in Rust)

Little proof-of-concept webservice in Rust, using [Actix](https://actix.rs/) web framework.

The service implements [an API specification](api-spec.md) of one feature for
[goout.net platform](https://goout.net/). It was shadow-developed alongside main implementation in
Kotlin [http4k](https://www.http4k.org/) made by [@**goodhoko**](https://github.com/goodhoko) at
[GoOut](https://www.startupjobs.cz/startup/goout-s-r-o) for comparison and joy.

## Build, Build Documentation, Run

To play/develop:

1. [Install Rust locally](https://www.rust-lang.org/tools/install), preferrably using [rustup](https://rustup.rs/).
   - Due to alpha Elasticsearch client, *nightly* Rust compiler is needed. This is how to
     [install it with `rustup`](https://github.com/rust-lang/rustup/blob/master/README.md#working-with-nightly-rust):
     - `rustup toolchain install nightly`
     - `rustup default nightly`
2. Use [Cargo](https://doc.rust-lang.org/cargo/) to do all development work:

- Build: `cargo build`
  - The executable binary is built at `target/debug/locations-rs`
  - Pass `--release` to compile with optimizations (into `target/release/`)
- Build & Run: `cargo run`
- Run tests (when there are any): `cargo test`
- Check the code compiles (faster than build): `cargo check`
  - Run additional code analysis, superset of check: `cargo clippy`
  - Some issues can be automatically fixed with: `cargo fix`
- Check code formatting: `cargo fmt -- --check`
  - Automatically fix code formatting: `cargo fmt`
- Build documentation: `cargo doc --no-deps`
  - Point your browser to `target/doc/locations-rs/index.html`
- Do most of the above at once whenever any file changes using [cargo watch](https://crates.io/crates/cargo-watch):
  `cargo watch -x clippy -x test -x 'fmt -- --check' -x 'doc --no-deps' -x run`

## Runtime Dependencies

The locations service needs an Elasticsearch instance to operate. The instance should contain
indices `city` and `region` filled with some data. The `GOOUT_ELASTIC_HOST` and `GOOUT_ELASTIC_PORT`
(usually `9200`) environment variables need to point to the instance.

This repository contains [`elasticsearch`](elasticsearch) directory with ready-made dockerized
Elasticsearch instance pre-filled with data. Simply set `GOOUT_ELASTIC_HOST` to a host that runs the
Docker image. Note that if both locations and Elasticsearch run in separate Docker containers, one
needs to point locations to *host* address like `172.17.0.1` (`GOOUT_ELASTIC_HOST` of `127.0.0.1` or
`0.0.0.0` won't work).

The directory also contains mapping definitions of the 2 indices and example data.
