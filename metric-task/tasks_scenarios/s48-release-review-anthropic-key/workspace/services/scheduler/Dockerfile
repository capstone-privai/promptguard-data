FROM node:22-alpine
WORKDIR /srv/scheduler
COPY package.json ./
RUN npm ci --omit=dev
COPY src ./src
EXPOSE 8086
CMD ["node", "src/main.js"]
