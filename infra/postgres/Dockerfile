FROM postgres:16-alpine
# The official image's gosu is a Go binary built with an old toolchain (CVE-2025-68121 in Go's crypto/tls;
# Trivy stopped release v0.1.0 on it). It is deleted (a whiteout, which scanners honour; a symlink over it
# would leave the old file visible in the base layer) and su-exec, which does the same job in C with the
# same arguments, answers to `gosu` further along the PATH. The image's entrypoint is unchanged.
RUN apk add --no-cache su-exec && rm -f /usr/local/bin/gosu && ln -s /sbin/su-exec /usr/bin/gosu \
 && gosu nobody true
COPY init/ /docker-entrypoint-initdb.d/
