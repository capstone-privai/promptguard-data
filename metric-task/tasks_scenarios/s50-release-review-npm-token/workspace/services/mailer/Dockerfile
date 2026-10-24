FROM node:22-alpine
WORKDIR /srv/mailer
COPY package.json ./
RUN npm ci --omit=dev
COPY src ./src
EXPOSE 8083
CMD ["node", "src/main.js"]
