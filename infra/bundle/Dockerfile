# The release's server files (P18.8): what root runs on the server comes from here, never from the deploy
# user. scorecode-deploy pulls this image for a version and copies /bundle out (docker create + cp); it is
# never run. Built from the repository root: docker build -f infra/bundle/Dockerfile .
FROM scratch
COPY compose.prod.yml /bundle/compose.prod.yml
COPY infra/ops /bundle/infra/ops
COPY infra/monitoring /bundle/infra/monitoring
CMD ["/bundle/none"]
