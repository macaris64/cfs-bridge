FROM python:3.10-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/sensor_manager

ENV PYTHONPATH=/app

CMD ["streamlit", "run", "sensor_manager/manager_app.py", "--server.headless=true", "--server.port=8501"]
