FROM node:22-alpine
WORKDIR /srv/catalog
COPY package.json ./
RUN npm ci --omit=dev
COPY src ./src
EXPOSE 8081
CMD ["node", "src/main.js"]
