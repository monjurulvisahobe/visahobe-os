# VisaHoBe — All-in-One Visa Agency OS

**Your Dream Abroad Starts Here**

One Flask app. Port 5001. 100% free stack. No paid API. Ready to deploy.

## What's inside

| Feature | Endpoint |
|---|---|
| Chat parser (Bangla/English intents) | POST /api/minimal/chat |
| Candidate CRM + CSV export | /api/candidates, /api/candidates/export |
| Lead manager with auto follow-up | /api/leads |
| Job portal admin + public page + apply | /api/jobs, /jobs, /api/apply |
| Agency finder + scam checker | /api/find-agencies, /api/check-agency |
| Email center (Gmail SMTP 500/day) | /api/generate-email |
| Post designer | /api/create-post |
| Reels script factory | /api/generate-video-script |
| Document AI (CV/Agreement/Cover Letter) | /api/generate-doc |
| Profit tracker | /api/transactions |
| Realistic human-like voice (Edge TTS, free unlimited) | /api/voice/generate, /api/voice/chat |
| AI chat (Gemini 2.0 Flash free + rule-based fallback) | /api/chat |
| WhatsApp Cloud API webhook (1000/month free) | /api/whatsapp-webhook |
| Real-time settings (no restart) | /api/settings, /api/settings/save, /api/settings/test/<service> |
| Full backup | /api/backup |

## Works WITHOUT any keys (day one)

- Rule-based AI using `data/knowledge_base.json` as brain
- Edge TTS voice: bn-BD-NabanitaNeural / bn-BD-PradeepNeural / en-US-JennyNeural / en-US-GuyNeural — free, unlimited, no key
- Full CRM, jobs, leads, profit — all real time on JSON files

## Optional keys (add in UI → ⚙️ API Keys, instantly active, no restart)

- **Gemini** — free 1500 req/day → https://aistudio.google.com/app/apikey
- **Gmail** — App Password for real email sending (500/day)
- **WhatsApp** — Cloud API webhook URL: `https://yourdomain.com/api/whatsapp-webhook`, verify_token: `visahobe123`
- **Facebook** — Page token for posting/auto reply

## Run locally

```bash
pip install -r requirements.txt
python app.py
# open http://localhost:5001
```

## Deploy on Hugging Face Spaces (free forever)

1. Create Space → SDK: **Docker**
2. Upload all files (or push via git)
3. App reads `PORT` env automatically (HF sets it). Done.

## Deploy on Render (free)

1. New Web Service → connect repo
2. Build: `pip install -r requirements.txt`
3. Start: `python app.py` (or `gunicorn app:app`)
4. Port 5001.

## Data

All data lives in `data/*.json` — candidates, leads, jobs, transactions, agencies, settings, conversations, knowledge_base. Backup any time via /api/backup. For permanent hosting, mount a volume on the `data/` folder.

## PWA

Open on mobile → "Add to Home Screen" → VisaHoBe becomes a native app (manifest + service worker included).
