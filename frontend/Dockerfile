FROM node:18-alpine AS builder

ENV TZ=Asia/Shanghai

WORKDIR /app

COPY package*.json ./
RUN npm install && npm install lunar-javascript terser
COPY . .
RUN printf '%s\n' \
  "import { defineConfig } from 'vite'" \
  "import vue from '@vitejs/plugin-vue'" \
  "import path from 'path'" \
  "" \
  "export default defineConfig({" \
  "  plugins: [vue()]," \
  "  resolve: {" \
  "    alias: {" \
  "      '@': path.resolve(__dirname, './src')," \
  "    }," \
  "  }," \
  "  build: {" \
  "    minify: 'terser'," \
  "    terserOptions: {" \
  "      compress: {" \
  "        drop_console: false," \
  "        drop_debugger: true," \
  "      }," \
  "      mangle: {" \
  "        toplevel: true," \
  "      }," \
  "    }," \
  "    rollupOptions: {" \
  "      output: {" \
  "        chunkFileNames: 'assets/[hash].js'," \
  "        entryFileNames: 'assets/[hash].js'," \
  "        assetFileNames: 'assets/[hash][extname]'," \
  "      }," \
  "    }," \
  "  }," \
  "})" \
  > vite.config.js

RUN npm run build

FROM nginx:1.27-alpine

# 只保留 Asia/Shanghai 一个时区文件，装完 tzdata 立刻卸载
RUN apk add --no-cache tzdata \
    && cp /usr/share/zoneinfo/Asia/Shanghai /etc/localtime \
    && echo "Asia/Shanghai" > /etc/timezone \
    && apk del tzdata

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]