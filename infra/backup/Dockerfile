# Backup and restore tools (P16.4): the same pg_dump/pg_restore major version as the server, age for
# encryption, the AWS CLI for any S3-compatible second storage. Runs as a non-root user.
FROM postgres:16-alpine
# gosu is not needed here (the job runs as `backup`), and the base image's copy is an old Go build
# (CVE-2025-68121), so it goes.
RUN apk add --no-cache age aws-cli curl tzdata \
 && rm -f /usr/local/bin/gosu \
 && adduser -D -u 10001 backup \
 && install -d -o backup -g backup /home/backup/mirror
COPY backup.sh restore.sh scheduler.sh /usr/local/bin/
USER backup
WORKDIR /home/backup
# Nightly at 02:30 IST (21:00 UTC). `docker compose run --rm backup backup.sh` runs one now.
ENTRYPOINT []
CMD ["scheduler.sh"]
