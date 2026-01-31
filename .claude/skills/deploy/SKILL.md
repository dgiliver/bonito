---
name: deploy
description: Deploy Bonito to production (Docker, Vercel, Railway)
allowed-tools: Bash, Read
disable-model-invocation: true
---

# Deploy Skill

Deploy Bonito to production environments.

## Local Docker Deployment

```bash
# Build and start containers
make docker-build
make docker-up

# Verify running
docker ps
curl http://localhost:8000/health

# View logs
make docker-logs

# Stop
make docker-down
```

## Production Deployment

### Backend (Railway)
```bash
# Login to Railway
railway login

# Initialize project (first time)
railway init

# Deploy
railway up

# Set environment variables
railway variables set ANTHROPIC_API_KEY=sk-ant-...
```

### Frontend (Vercel)
```bash
cd web

# Login to Vercel
vercel login

# Deploy preview
vercel

# Deploy production
vercel --prod
```

## Pre-Deployment Checklist

- [ ] All tests pass: `make test`
- [ ] No lint errors: `make lint`
- [ ] Type checks pass: `make typecheck`
- [ ] Frontend builds: `cd web && npm run build`
- [ ] Environment variables set in production
- [ ] Database migrations applied (if any)

## Environment Variables Required

```
ANTHROPIC_API_KEY=sk-ant-...   # Required
DATABASE_URL=...               # For Supabase (future)
NEXT_PUBLIC_API_URL=...        # Frontend API endpoint
```

## Rollback

```bash
# Railway
railway rollback

# Vercel
vercel rollback
```
