# Vertex AI Deployment Guide

## What Changed

Your code now automatically handles both development (Gemini API) and production (Vertex AI) modes:

- **Development**: Uses `GEMINI_API_KEY` with model names like `gemini-live-2.5-flash-native-audio`
- **Production**: Uses Vertex AI with IAM auth and model names like `google/gemini-live-2.5-flash-native-audio`

## Deployment Steps

### 1. Set Environment Variables in Cloud Run

```bash
gcloud run services update negotiation-backend \
  --region=us-central1 \
  --update-env-vars="GEMINI_MODEL=gemini-live-2.5-flash-native-audio,GEMINI_MODEL_FALLBACK=gemini-2.5-flash,GOOGLE_GENAI_USE_VERTEXAI=True,GOOGLE_CLOUD_PROJECT=ai-negotiation-copilot,GOOGLE_CLOUD_LOCATION=us-central1"
```

**Note**: Don't include the `google/` prefix in the environment variables - the code adds it automatically when `GOOGLE_GENAI_USE_VERTEXAI=True`.

### 2. Enable Vertex AI API

```bash
gcloud services enable aiplatform.googleapis.com
```

### 3. Grant IAM Permissions

Get your Cloud Run service account:

```bash
gcloud run services describe negotiation-backend \
  --region=us-central1 \
  --format="value(spec.template.spec.serviceAccountName)"
```

Grant Vertex AI User role:

```bash
gcloud projects add-iam-policy-binding ai-negotiation-copilot \
  --member="serviceAccount:YOUR_SERVICE_ACCOUNT@ai-negotiation-copilot.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"
```

### 4. Redeploy

```bash
cd backend
gcloud builds submit --tag us-central1-docker.pkg.dev/ai-negotiation-copilot/negotiation-app/backend:latest .

gcloud run deploy negotiation-backend \
  --image=us-central1-docker.pkg.dev/ai-negotiation-copilot/negotiation-app/backend:latest \
  --region=us-central1 \
  --allow-unauthenticated \
  --port=8080 \
  --memory=2Gi \
  --cpu=2 \
  --timeout=3600 \
  --min-instances=1 \
  --set-env-vars="GOOGLE_CLOUD_PROJECT=ai-negotiation-copilot,GOOGLE_CLOUD_LOCATION=us-central1,GOOGLE_GENAI_USE_VERTEXAI=true,GEMINI_MODEL=gemini-2.0-flash-exp,LOG_LEVEL=INFO,CORS_ORIGINS=*"
```

### 5. Verify Deployment

Check the logs:

```bash
gcloud run services logs read negotiation-backend --region=us-central1 --limit=50
```

You should see:
- `[ListenerAgent] Using Vertex AI in us-central1`
- `Gemini Live session opened with model: google/gemini-live-2.5-flash-native-audio`

Test the health endpoint:

```bash
curl https://negotiation-backend-219079068693.us-central1.run.app/health
```

## Models Used

| Component | Development (Gemini API) | Production (Vertex AI) |
|---|---|---|
| Live AI Primary | `gemini-live-2.5-flash-native-audio` | `google/gemini-live-2.5-flash-native-audio` |
| Live AI Fallback | `gemini-2.5-flash` | `google/gemini-2.5-flash` |
| Listener Agent | `gemini-2.5-flash` | `google/gemini-2.5-flash` |

## Troubleshooting

**Error: "model not found"**
- Check that `GOOGLE_GENAI_USE_VERTEXAI=True` is set
- Verify Vertex AI API is enabled
- Confirm the model is available in your region

**Error: "permission denied"**
- Check IAM permissions for the service account
- Ensure `roles/aiplatform.user` is granted

**Error: "invalid credentials"**
- Cloud Run automatically provides credentials via metadata server
- No need to set `GOOGLE_APPLICATION_CREDENTIALS` in Cloud Run

## Cost Comparison

Both Gemini API and Vertex AI use the same pricing for the same models. Vertex AI provides:
- Better security (IAM-based auth)
- Higher quotas
- Private data (Google never trains on your data)
- Unified GCP billing
