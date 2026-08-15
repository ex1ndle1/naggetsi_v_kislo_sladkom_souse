FROM node:20-alpine AS builder

WORKDIR /build

# Зависимости отдельным слоем: он переиспользуется, пока не менялся package-lock.json.
COPY package.json package-lock.json ./
# Не --omit=dev: vite, tsc и tailwind лежат в devDependencies, и без них
# `npm run build` не запустится вовсе.
RUN npm ci --no-audit --no-fund

COPY . .
RUN npm run build

# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine

COPY --from=builder /build/dist /usr/share/nginx/html
COPY nginx-spa.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

# curl нужен healthcheck'у из docker-compose.yml; в базовом образе его нет.
RUN apk add --no-cache curl

CMD ["nginx", "-g", "daemon off;"]
