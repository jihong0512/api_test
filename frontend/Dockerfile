FROM node:18-alpine

WORKDIR /app

# 复制package文件
COPY package*.json ./

# 设置清华镜像
RUN npm config set registry https://registry.npmmirror.com

# 安装依赖
RUN npm install

# 复制应用代码
COPY . .

# 暴露端口（React默认3000，但可以在package.json中配置）
EXPOSE 3000

# 设置环境变量
# 注意：在Docker容器中，backend服务名为"backend"
ENV REACT_APP_API_URL=http://backend:8004
ENV PORT=3000
ENV HOST=0.0.0.0

# 启动应用（使用PORT环境变量）
CMD ["npm", "start"]



