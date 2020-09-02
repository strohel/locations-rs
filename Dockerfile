# Build image.
FROM rust:1.45 as build

RUN rustc --version

# Copy everything, depend on .dockerignore only including relevant files.
COPY ./ ./

# Compile in release mode and put the binary into /install/.
RUN cargo install --path . --root /install

# Production image. Shrinking possibility: https://alexbrand.dev/post/how-to-package-rust-applications-into-minimal-docker-containers/
FROM bitnami/minideb:buster

# Install runtime dependencies; install_packages provided by https://github.com/bitnami/minideb
RUN install_packages dumb-init libssl1.1 libcurl4

COPY --from=build /install/bin/locations-rs /

# Use dumb-init to correctly handle signals in PID 1.
ENTRYPOINT ["/usr/bin/dumb-init", "--"]

CMD ["/locations-rs"]
