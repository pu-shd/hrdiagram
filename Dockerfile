FROM nginx:1.28.0-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY web/ /usr/share/nginx/html/
COPY LICENSE.md /usr/share/nginx/html/LICENSE.md
COPY docs/third-party.md /usr/share/nginx/html/THIRD_PARTY.md
