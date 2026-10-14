FROM postgres:16-alpine
# The official image's gosu is a Go binary built with an old toolchain (CVE-2025-68121 in Go's crypto/tls;
# Trivy stopped release v0.1.0 on it). su-exec does the same job in C (switch user, then exec) and takes the
# same arguments, so the image's entrypoint is unchanged.
RUN apk add --no-cache su-exec && ln -sf /sbin/su-exec /usr/local/bin/gosu && gosu nobody true
COPY init/ /docker-entrypoint-initdb.d/
