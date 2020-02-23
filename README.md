# locations-rs (Locations Service in Rust)

Little proof-of-concept webservice in Rust, using experimental [Tide](https://github.com/http-rs/tide) web framework.

## Build, Build Documentation, Run

To develop, [install Rust locally](https://www.rust-lang.org/tools/install), and then use
[Cargo](https://doc.rust-lang.org/cargo/) to do all development work:

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
