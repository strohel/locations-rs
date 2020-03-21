# Build image; Elasticsearch client currently requires nightly Rust.
FROM rustlang/rust:nightly-buster as build

RUN rustc --version

# Download the target for static linking.
RUN rustup target add x86_64-unknown-linux-musl

RUN apt update && apt install -y --no-install-recommends musl-tools

# Download statically linked version of dumb-init, the one from Debian is dynamically linked.
ARG DUMB_INIT_VERSION=1.2.2
ADD https://github.com/Yelp/dumb-init/releases/download/v${DUMB_INIT_VERSION}/dumb-init_${DUMB_INIT_VERSION}_amd64 /dumb-init
# Add executable bit; this is the reason this needs to be in build step, there is no chmod in production image.
RUN chmod a+x /dumb-init

# Copy everything, depend on .dockerignore only including relevant files.
COPY ./ ./

# Compile in release mode and put the binary into /install/.
RUN cargo install --path . --root /install --target x86_64-unknown-linux-musl

# Production image. See https://alexbrand.dev/post/how-to-package-rust-applications-into-minimal-docker-containers/
FROM scratch

COPY --from=build /dumb-init /

COPY --from=build /install/bin/locations-rs /

# Use dumb-init to correctly handle signals in PID 1.
ENTRYPOINT ["/dumb-init", "--"]

CMD ["/locations-rs"]
