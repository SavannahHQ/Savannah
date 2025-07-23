FROM python:3.9-slim

WORKDIR /home/python

# Install system dependencies
RUN apt update \
    && apt install -y --no-install-recommends \
        build-essential \
        findutils

# If using postgres:
#RUN apt update \
#    && apt install -y postgresql-common libpq-dev

# If using mysql/mariadb:
#RUN apt update \
#    && apt install -y default-mysql-client libmariadb-dev pkg-config

# Cleanup apt
RUN rm -rf /var/lib/apt/lists/* \
    && apt clean

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Command to run
CMD ["bash"]