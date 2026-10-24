FROM node:22-alpine
WORKDIR /srv/billing
COPY package.json ./
RUN npm ci --omit=dev
COPY src ./src
EXPOSE 8082
CMD ["node", "src/main.js"]
