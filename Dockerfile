FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend ./backend
COPY web ./web
ENV PYTHONPATH=/app/backend
EXPOSE 8000
CMD ["sh","-c","if [ \"$HOCKEY_PUBLIC_PROXY\" = \"1\" ]; then exec uvicorn render_public:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000}; else exec uvicorn main:app --app-dir backend --host 0.0.0.0 --port ${PORT:-8000}; fi"]
