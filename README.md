# Driver-Hub Matching Service

FastAPI micro-service that automatically assigns new driver applicants to their nearest delivery hub (e.g. Walmart store) based on a street address.  
It receives an address (via REST call or Typeform webhook), geocodes it with **HERE API**, finds the closest hub from a dynamic list (CSV, Google Sheet or Postgres), and notifies both the applicant and an admin via email and/or webhook.

---

## ✨ Features

* 🔗 **API first** – lightweight FastAPI app ready for serverless.
* 🗺 **HERE Geocoding** – no Google Maps dependency.
* 📏 **Accurate distance** – Haversine formula via `haversine`/`geopy`.
* 🏪 **Pluggable data sources** – CSV, Google Sheets, Postgres.
* 📣 **Notifications** – SendGrid, Mailgun or generic webhook.
* ☁️ **Serverless ready** – tested on AWS Lambda (API Gateway) & Cloud Run.
* 🔄 **Easily extensible** – clear folder layout, Pydantic models, services layer.

---

## 📂 Project Structure

```
.
├── app/
│   ├── api/               # FastAPI routers
│   ├── core/              # Config & settings
│   ├── models/            # Pydantic DTOs
│   ├── services/          # Geocoding, locations & notifications
│   └── main.py            # ASGI entry-point
├── data/locations.csv     # Sample hub list (80+ rows)
├── requirements.txt
├── .env.example           # Copy → .env and fill in secrets
└── README.md
```

---

## 🚀 Quick Start (Local)

### 1. Clone & install

```bash
git clone https://github.com/your-org/driver-hub-matching.git
cd driver-hub-matching
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env and add your HERE, SendGrid/Mailgun keys, etc.
```

### 3. Run development server

```bash
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000/docs for an interactive Swagger UI.

---

## 🛠 Usage Examples

### Match a single address

```bash
curl -X POST http://127.0.0.1:8000/api/v1/match \
  -H "Content-Type: application/json" \
  -d '{
        "address": "1600 Pennsylvania Ave NW, Washington, DC 20500",
        "email": "driver@example.com",
        "name": "Alex Driver"
      }'
```

Response:

```json
{
  "input_address": "...",
  "geocoded_address": "...",
  "geocoded_coordinates": {"latitude": 38.8977, "longitude": -77.0365},
  "matched_location": { "id": "loc_029", "name": "Washington DC Walmart", ... },
  "distance_km": 3.2,
  "distance_miles": 2.0,
  "processing_time_ms": 152.34,
  "timestamp": "2025-06-16T12:34:56.789Z"
}
```

### Batch match up to 100 addresses

```
POST /api/v1/match/batch
[
  { "address": "...", "email": "..."},
  { "address": "...", "email": "..."}
]
```

### Typeform webhook

Configure Typeform to call `/api/v1/webhooks/typeform` and add the secret in `.env` (`TYPEFORM_WEBHOOK_SECRET`). The service will:

1. Verify the signature.
2. Extract address/email/name/phone.
3. Compute nearest hub.
4. Send email and/or webhook notification in the background.

---

## ⚙️ Configuration Reference

All settings come from environment variables (see `.env.example`):

| Variable | Description |
|----------|-------------|
| `HERE_API_KEY` | HERE REST geocoding key (**required**) |
| `DATA_SOURCE_TYPE` | `csv`, `google_sheets` or `postgres` |
| `CSV_FILE_PATH` | Path to CSV file (if `csv`) |
| `GOOGLE_SHEETS_ID` / `GOOGLE_CREDENTIALS_JSON` | Sheet ID & service account JSON (if `google_sheets`) |
| `DATABASE_URL` | SQLAlchemy URL (if `postgres`) |
| `NOTIFICATION_METHOD` | `email`, `webhook` or `both` |
| `SENDGRID_API_KEY` / `MAILGUN_API_KEY` | Email provider keys |
| `WEBHOOK_URL` / `WEBHOOK_SECRET` | Outgoing notification webhook |
| `TYPEFORM_WEBHOOK_SECRET` | Secret to validate incoming Typeform calls |

---

## 🧪 Testing

```bash
pytest
```

Tests use `httpx.AsyncClient` to hit the FastAPI app in memory and mock HERE API responses.

---

## ☁️ Deployment

### AWS Lambda (API Gateway)

1. Build a **Lambda container image**:

   ```bash
   docker build -t driver-hub-matching .
   aws ecr create-repository --repository-name driver-hub-matching
   # tag & push ...
   aws lambda create-function \
     --function-name driver-hub-matching \
     --package-type Image \
     --code ImageUri=<ECR_URI>:latest \
     --memory-size 512 --timeout 30 \
     --environment Variables={HERE_API_KEY=..., ...}
   ```

2. Attach an API Gateway HTTP API → Lambda proxy integration.

### Google Cloud Run

```bash
gcloud builds submit --tag gcr.io/<PROJECT_ID>/driver-hub-matching
gcloud run deploy driver-hub-matching \
  --image gcr.io/<PROJECT_ID>/driver-hub-matching \
  --platform managed --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars HERE_API_KEY=...,NOTIFICATION_METHOD=email,...
```

### Other Targets

Because the app is standard ASGI, it also works on:

* **Fly.io** (`fly launch`)
* **Azure Container Apps**
* **Heroku** (with `gunicorn`)

---

## 📈 Scaling Tips

* Increase `locations.csv` to 500+ rows – no code change needed.
* Switch to Postgres for easier updates: set `DATA_SOURCE_TYPE=postgres`.
* Enable **connection pooling** on Cloud Run (e.g. `pgbouncer` sidecar).
* Use AWS Secrets Manager or GCP Secret Manager instead of `.env`.

---

## 🤝 Contributing

1. Fork & clone repository.
2. Create a feature branch (`feat/my-feature`).
3. Run `make lint && pytest`.
4. Submit a pull request 🎉.

---

## 📜 License

MIT © 2025 Your Company
