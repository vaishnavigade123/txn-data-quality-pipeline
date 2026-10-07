# Packages the pipeline into a portable container that can run identically
# on any machine or scheduler (cron, Airflow, a cloud job runner, etc.)

FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scripts/ ./scripts/

WORKDIR /app/scripts

CMD ["python", "alert.py"]
