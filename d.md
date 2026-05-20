curl -X POST ^
  -H "Authorization: Bearer YOUR_GOOGLE_OAUTH_TOKEN_HERE" ^
  -H "x-goog-user-project: ai-negotiation-copilot" ^
  -H "Content-Type: application/json" ^
  -d "{\"config\":{\"autoDecodingConfig\":{},\"languageCodes\":[\"en-US\"],\"model\":\"chirp_3\"},\"content\":\"\"}" ^
  "https://us-speech.googleapis.com/v2/projects/ai-negotiation-copilot/locations/us/recognizers/_:recognize"