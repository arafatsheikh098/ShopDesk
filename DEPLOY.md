# Deploying ShopDesk

This guide covers two production options:

1. **Render** (managed, recommended for small shops).
2. **Docker Compose** on your own VPS (full control, no vendor).

## 0. Before you deploy

You need a long, random `SECRET_KEY`. Generate one with:

```
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Treat this value like a database password. Never commit it.

## 1. Render (Blueprint)

The repo includes `render.yaml` that provisions Postgres and the Web
Service in one click.

1. Fork / push this repo to GitHub.
2. In Render: **New → Blueprint** → connect the repo.
3. After the database is created, set `SECRET_KEY` in the Web Service
   environment (Render → shopdesk → Environment → Add Secret).
4. Render will build the image, run `alembic upgrade head` at boot, and
   start `uvicorn`. The health check is `GET /health`.
5. Create the first owner from the Render shell:

   ```
   python scripts/create_owner.py <username> <password>
   ```

6. (Optional) Seed demo data:

   ```
   python scripts/seed.py
   ```

7. Open the URL Render gave you and log in.

### Backing up on Render

Render-managed Postgres supports logical backups out of the box. To run
the included backup script against the managed DB, copy the
`DATABASE_URL` from the database's "Connection" tab and run:

```
DATABASE_URL='postgresql://...' ./scripts/backup.sh
```

The archive is written to `./backups/` on your local machine. To restore:

```
./scripts/restore.sh ./backups/shopdesk-pg-20251024T103000Z.sql.gz
```

## 2. Docker Compose on a VPS

`docker-compose.yml` runs the app and a Postgres sidecar.

1. Clone the repo on the VPS.
2. Copy `.env.example` to `.env` and fill in:

   ```
   APP_ENV=production
   SECRET_KEY=<the long random value from step 0>
   SHOP_NAME=My Shop
   CURRENCY_SYMBOL=৳
   SHOP_TIMEZONE=Asia/Dhaka
   ```

3. Bring it up:

   ```
   docker compose up -d --build
   docker compose exec app alembic upgrade head
   docker compose exec app python scripts/create_owner.py <user> <pw>
   docker compose exec app python scripts/seed.py   # optional demo
   ```

4. Put nginx or Caddy in front for HTTPS. The app listens on `:8000`
   inside the container.

### Backing up on the VPS

```
docker compose exec -T db pg_dump -U shopdesk shopdesk | gzip > shopdesk-$(date -u +%Y%m%dT%H%M%SZ).sql.gz
```

Or use the included script with `DATABASE_URL` pointing at the db
container:

```
DATABASE_URL='postgresql://shopdesk:shopdesk@db:5432/shopdesk' \
  docker compose exec -T app /app/scripts/backup.sh
```

## 3. Smoke test

`scripts/smoke_test.sh` checks a running deployment:

```
BASE=https://shop.example.com ./scripts/smoke_test.sh
```

Exits 0 on a healthy service. Wire it into a cron or uptime check.

## 4. Production checklist

- [ ] `SECRET_KEY` is set and is not the default value.
- [ ] `APP_ENV=production` so the default-secret refusal is armed.
- [ ] HTTPS is terminated in front of the app.
- [ ] `DATABASE_URL` points at a real database (Postgres recommended).
- [ ] `alembic upgrade head` has been run.
- [ ] At least one owner exists (`create_owner.py`).
- [ ] Backups run on a schedule and are tested with a restore.
- [ ] Smoke test is wired into monitoring.

## 5. Troubleshooting

- **Service won't start in production**: check the logs for
  `FATAL: default SECRET_KEY in production. Refusing to start.` — set
  `SECRET_KEY` to a long random value.
- **Login fails with 429**: you've hit the per-IP rate limit
  (5/minute by default). Wait a minute or raise
  `LOGIN_RATE_LIMIT_PER_MINUTE`.
- **PDF font missing**: the bundled Noto Sans Bengali font should be in
  `assets/fonts/`. The build copies it into the image automatically.
- **Offline sales not syncing**: check the browser dev tools → IndexedDB
  → `shopdesk.pending_sales`; the sales stay there until the network is
  back. The badge in the header shows the count.