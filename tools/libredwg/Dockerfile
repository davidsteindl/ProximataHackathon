FROM debian:bookworm-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential ca-certificates curl xz-utils python3 && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN curl -fsSL https://ftp.gnu.org/gnu/libredwg/libredwg-0.13.3.tar.xz -o source.tar.xz && tar -xf source.tar.xz --strip-components=1
RUN ./configure --disable-shared --disable-bindings && make -j2 && make install

FROM debian:bookworm-slim
COPY --from=build /usr/local/bin/dwg2dxf /usr/local/bin/dwg2dxf
WORKDIR /data
ENTRYPOINT ["dwg2dxf"]

