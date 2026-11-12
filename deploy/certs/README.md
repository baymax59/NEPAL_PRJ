# Certificates (Step 14.2)

Put your organisation's certificate and private key for this server here, e.g. `site.crt` and `site.key`,
then set in `.env`:

    SITE_ADDRESS=cases.example.internal
    TLS=/certs/site.crt /certs/site.key

and restart: `docker compose --profile app up -d`.

Everything in this folder except this README is ignored by Git. **Never commit or e-mail a private key.**
Without files here, Caddy uses its own certificate authority (`TLS=internal`), which browsers don't trust
until they are told to (see docs/steps/14-2-https-and-hardening.md).
