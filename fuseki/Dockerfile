# Use Python 3.11 as the base image (Debian-based)
FROM python:3.11-slim

# Install Java 21 (for Jena 5.x) and utilities, also curl and tar since we need to extract
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    openjdk-21-jre-headless \
    curl \
    tar \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Define versions
ENV JENA_VERSION=5.6.0

# Download and install Apache Jena
RUN curl -L -o jena.tar.gz https://archive.apache.org/dist/jena/binaries/apache-jena-${JENA_VERSION}.tar.gz && \
    tar -xzf jena.tar.gz -C /opt && \
    rm jena.tar.gz

# Download and Install Apache Jena Fuseki
RUN curl -L -o fuseki.tar.gz https://archive.apache.org/dist/jena/binaries/apache-jena-fuseki-${JENA_VERSION}.tar.gz && \
    tar -xzf fuseki.tar.gz -C /opt && \
    rm fuseki.tar.gz

# Setup Env variables
ENV JENA_HOME=/opt/apache-jena-${JENA_VERSION}
ENV FUSEKI_HOME=/opt/apache-jena-fuseki-${JENA_VERSION}
ENV PATH="${JENA_HOME}/bin:${FUSEKI_HOME}:${PATH}"

# Set up the working dir inside container
WORKDIR /app

# Copy current dir (scrips and schema) into container
COPY . /app/

# Expose port
EXPOSE 3030

# Run existing setup for knowledge graphs on startup
CMD ["python", "setup_fuseki.py"]
