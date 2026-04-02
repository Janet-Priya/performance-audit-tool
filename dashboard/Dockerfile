FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci 2>/dev/null || npm install
COPY public ./public
COPY src ./src
# Default empty: production bundle uses /api/... on same origin (nginx → manager). Override for static hosting without a proxy.
ARG REACT_APP_API_URL=
ARG REACT_APP_TARGET_URL=http://localhost:8000
ENV REACT_APP_API_URL=$REACT_APP_API_URL
ENV REACT_APP_TARGET_URL=$REACT_APP_TARGET_URL
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
