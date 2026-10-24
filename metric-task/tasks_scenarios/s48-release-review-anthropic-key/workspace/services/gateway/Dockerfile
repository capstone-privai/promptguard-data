FROM node:22-alpine
WORKDIR /srv/gateway
COPY package.json ./
RUN npm ci --omit=dev
COPY src ./src
EXPOSE 8080
CMD ["node", "src/main.js"]
