# Backup and restore tools (P16.4): the same pg_dump/pg_restore major version as the server, age for
# encryption, the AWS CLI for any S3-compatible second storage. Runs as a non-root user.
FROM postgres:16-alpine
RUN apk add --no-cache age aws-cli curl tzdata \
 && adduser -D -u 10001 backup \
 && install -d -o backup -g backup /home/backup/mirror
COPY backup.sh restore.sh scheduler.sh /usr/local/bin/
USER backup
WORKDIR /home/backup
# Nightly at 02:30 IST (21:00 UTC). `docker compose run --rm backup backup.sh` runs one now.
ENTRYPOINT []
CMD ["scheduler.sh"]
