# 英文註解: Stage 1: Build the frontend application
FROM node:18-alpine as build

# 英文註解: Set the working directory
WORKDIR /app

# 英文註解: Copy package.json and package-lock.json (if available)
COPY package*.json ./

# 英文註解: Install dependencies
RUN npm install

# 英文註解: Copy the rest of the frontend code
COPY . .

# 英文註解: Build the app
RUN npm run build

# 英文註解: Stage 2: Serve the app with Nginx
FROM nginx:alpine

# 英文註解: Copy the build output to replace the default nginx contents
COPY --from=build /app/dist /usr/share/nginx/html

# 英文註解: Copy custom nginx config if needed (optional)
# COPY nginx.conf /etc/nginx/conf.d/default.conf

# 英文註解: Expose port 80
EXPOSE 80

# 英文註解: Start Nginx
CMD ["nginx", "-g", "daemon off;"]
