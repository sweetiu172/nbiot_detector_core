# ---- Stage 1: Builder ----
# Change base image to Alpine to match the runtime environment for compiled dependencies
FROM python:3.12-slim AS builder

LABEL stage="builder"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set up a directory for our virtual environment
WORKDIR /opt/venv_builder

# Create a virtual environment
RUN python -m venv .
# Activate virtual environment for subsequent RUN commands in this stage
ENV PATH="/opt/venv_builder/bin:$PATH"

# Copy requirements.txt
COPY ./requirements.txt /opt/venv_builder/requirements.txt

# Install Python dependencies into the virtual environment
# Use --no-cache-dir to reduce layer size.
RUN pip install --no-cache-dir -r requirements.txt
    # pip install --no-cache-dir torch==2.7.0 --index-url https://download.pytorch.org/whl/cpu

# ---- Stage 2: Runtime ----
FROM python:3.12-slim AS runtime

LABEL stage="runtime"

# --- FIX: Install the missing system dependency for LightGBM ---
# This library is required for multi-threading on CPU
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PATH="/opt/venv/bin:$PATH"

# Create a non-root user and group for the application
RUN addgroup appgroup && useradd appuser && adduser appuser appgroup 

# Define main application directory that will contain the venv and the app code
WORKDIR /app_code

# Copy the virtual environment from the builder stage
# This venv was built on Alpine, so it's compatible.
COPY --from=builder /opt/venv_builder /opt/venv

# Copy the application code
# This copies your local './app' directory to '/app_code/app' in the image
COPY . /app_code/app

# Set the working directory to where main.py is, for simpler CMD execution
WORKDIR /app_code

# Change ownership of the venv and the app code directory to the non-root user
# This should be done after all files are copied and before switching user.
RUN chown -R appuser:appgroup /opt/venv /app_code/app

# Switch to the non-root user
USER appuser

# Expose the port the app runs on
EXPOSE 8000

# Define the command to run the application
# 'main:app' refers to the 'app' FastAPI instance in 'main.py'
# Since WORKDIR is /app_code/app, main.py is directly accessible.
CMD ["/opt/venv/bin/python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]