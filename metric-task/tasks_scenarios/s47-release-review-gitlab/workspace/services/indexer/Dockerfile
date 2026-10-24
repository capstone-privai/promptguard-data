FROM node:22-alpine
WORKDIR /srv/indexer
COPY package.json ./
RUN npm ci --omit=dev
COPY src ./src
EXPOSE 8084
CMD ["node", "src/main.js"]
