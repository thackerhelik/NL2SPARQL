# ./frontend/Dockerfile
FROM node:20-alpine

WORKDIR /frontend

# Install deps first (better caching)
COPY package*.json ./
RUN npm ci

# Copy the rest of files
COPY . .

# Next dev must listen on all interfaces inside Docker
ENV HOST=0.0.0.0
ENV PORT=3000
EXPOSE 3000

CMD ["npm", "run", "dev", "--", "-p", "3000", "-H", "0.0.0.0"]
