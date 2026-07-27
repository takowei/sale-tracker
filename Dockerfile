# Deploy-only Dockerfile — sale-tracker has no packaging metadata (no
# pyproject.toml), so this installs straight from requirements.txt. Does not
# change any scraper/tracking logic, just packages the existing scripts.
FROM python:3.10-slim

RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data && chown -R appuser:appgroup /app
USER appuser

EXPOSE 8080

# Default command serves the static frontend + data/ over HTTP.
# The "scraper" service in docker-compose.yml overrides this to run
# scripts/cron_loop.sh instead.
CMD ["python3", "-m", "http.server", "8080"]
