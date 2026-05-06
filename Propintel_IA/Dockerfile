FROM python:3.14-slim

WORKDIR /app
COPY . /app

ENV APP_HOST=0.0.0.0
ENV APP_PORT=8088
ENV DATABASE_PATH=/app/data/propintel.sqlite3
ENV FRONTEND_DIR=/app/frontend

EXPOSE 8088
CMD ["python", "backend/app.py"]
