# 使用官方 JMeter 镜像（最简单最稳定）
FROM justb4/jmeter:latest

WORKDIR /app

# 设置系统时区为北京时间（UTC+8）
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 创建工作目录
RUN mkdir -p /app/jmeter-scripts /app/jmeter-results

# 默认命令：显示 JMeter 版本
CMD ["jmeter", "--version"]

