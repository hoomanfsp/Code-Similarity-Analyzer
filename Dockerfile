FROM docker.arvancloud.ir/python:3.10-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install -i https://mirror-pypi.runflare.com/simple --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create templates directory if it doesn't exist
RUN mkdir -p templates

# Expose the port Flask runs on
EXPOSE 5000

# Set environment variables
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

# Run the application
CMD ["python", "app.py"]
