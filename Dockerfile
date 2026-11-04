# amk as a container image: make build.docker fills the context with an assimilated executable per arch beside its aliases, since docker execs an entrypoint without the shell an ape needs.
ARG BASE=debian:bookworm-slim

FROM ${BASE} AS amk
ARG TARGETARCH
COPY ${TARGETARCH}/ /usr/local/bin/
WORKDIR /work
ENTRYPOINT ["amk"]

# The generator for GraphQLite's Cypher parser: bison 3 and flex, which the build runs here so the host needs neither; never published.
FROM ${BASE} AS parser
RUN apt-get update -qq \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends bison flex \
 && rm -rf /var/lib/apt/lists/*

# The tools make smoke uses beyond amk, and a stock make to drive it as the host does, since amk would put its payload tools on every recipe's PATH; never published.
FROM amk AS smoke
RUN apt-get update -qq \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq --no-install-recommends make unzip procps \
 && rm -rf /var/lib/apt/lists/*
