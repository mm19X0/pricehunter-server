# PriceHunter server

## Run locally

```powershell
cd server
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
$env:REFRESH_API_KEY = "use-a-long-random-secret"
uvicorn main:app --host 0.0.0.0 --port 8000
```

The API is available at `http://localhost:8000`. Product history is returned by
`GET /products/{product_id}/history`; its `ts` values are Unix timestamps in
seconds. `POST /refresh` requires the `X-API-Key` header and the server-side
`REFRESH_API_KEY` environment variable. Do not put that key in the Android app.
Product results support `limit` (up to 3,000) and `offset` for paging; the app
loads each page so larger catalogues are not truncated.

## Cloud deployment

The Docker Compose setup runs the API, persists SQLite in a named volume, and
puts Caddy in front to obtain and renew HTTPS certificates automatically:

1. Use a cloud VM with Docker Compose installed, a stable public IP, and inbound
   ports 80/443 open. A domain or subdomain must point to that IP.
2. In `server`, create a local `.env` file (it is git-ignored):

   ```dotenv
   API_DOMAIN=api.your-domain.example
   REFRESH_API_KEY=replace-with-a-long-random-secret
   ```

3. Run `docker compose up -d --build`, then check
   `https://api.your-domain.example/health`.
4. Set `PRICEHUNTER_API_BASE_URL` to that HTTPS URL when building the Android app.
   The build defaults to a placeholder URL, so set this to the deployed HTTPS
   endpoint before producing an APK.

For an Android debug build, run `gradle assembleDebug` with that environment
variable set. For a Play release, create a private upload keystore and pass its
path and credentials as `PRICEHUNTER_SIGNING_STORE_FILE`,
`PRICEHUNTER_SIGNING_STORE_PASSWORD`, `PRICEHUNTER_SIGNING_KEY_ALIAS`, and
`PRICEHUNTER_SIGNING_KEY_PASSWORD` when running `gradle assembleRelease`. Keep
the keystore and passwords out of source control and backups accessible to
others; losing the signing key can prevent future updates. Google Play
App Signing and Play Console distribution help establish app authenticity, but
a signing key alone cannot guarantee a Play Protect verdict or remove warnings
for APKs installed from outside the Play Store. The refresh API key is an
administrative server secret and must never be embedded in the Android app.

This config keeps the database on a persistent Docker volume. Free hosting plans
do not guarantee 24/7 availability; many free app-hosting plans sleep, and VM
free-tier capacity depends on provider, region, and account eligibility. A VM
also needs ongoing monitoring and backups. No cloud account or deployment
credentials are available in this project, so deployment itself must be
completed in the account owner's cloud console.

## Stores and coverage

The app lists Sigma Computer, El Nour Tech, CompuMarts, El Badr Group, and
Maximum Hardware. Live catalogue adapters cover El Nour Tech's read-only API,
CompuMarts' public Shopify product feed, and the OpenCart catalogues for El Badr
Group and Maximum Hardware. Sigma's product API rejects unauthenticated product
requests, but its public category pages render product names, images, prices,
availability, and pagination in the page HTML. The Sigma adapter reads those
public storefront pages across the public category list instead of calling the
restricted products endpoint. Do not treat sample products in the app as live
store inventory.
