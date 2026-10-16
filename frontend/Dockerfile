# frontend 이미지 (T26): Vite 빌드 → nginx 정적 서빙 + /api 프록시. 빌드 컨텍스트는 저장소 루트(compose 와 같음).
#   docker build -f frontend/Dockerfile .
# 번들에 키·토큰을 넣지 않는다(SAFE-13): VITE_* 비밀값 없음, MSW 는 운영 빌드에서 빠짐(main.tsx: DEV 에서만).
FROM node:22-alpine AS build
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM nginx:1.27-alpine
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
