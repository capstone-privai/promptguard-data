FROM node:22-alpine
WORKDIR /srv/worker
COPY package.json ./
RUN npm ci --omit=dev
COPY src ./src
EXPOSE 8087
CMD ["node", "src/main.js"]
