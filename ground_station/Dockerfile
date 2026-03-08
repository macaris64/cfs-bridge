FROM python:3.10-slim

WORKDIR /app

COPY ground_station/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy both packages (ground_station depends on sensor_manager.core)
COPY sensor_manager/ /app/sensor_manager/
COPY ground_station/ /app/ground_station/

ENV PYTHONPATH=/app

EXPOSE 8502
EXPOSE 2234/udp

CMD ["streamlit", "run", "ground_station/ground_app.py", "--server.headless=true", "--server.port=8502"]
