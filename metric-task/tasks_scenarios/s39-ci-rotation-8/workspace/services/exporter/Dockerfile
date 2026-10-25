FROM node:22-alpine
WORKDIR /srv/exporter
COPY package.json ./
RUN npm ci --omit=dev
COPY src ./src
EXPOSE 8085
CMD ["node", "src/main.js"]
