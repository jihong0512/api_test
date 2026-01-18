"""
启动服务器脚本 - 绑定到所有网络接口
"""
import uvicorn
import os

if __name__ == "__main__":
    # 获取主机和端口配置
    host = os.getenv("SERVER_HOST", "0.0.0.0")  # 绑定到所有网络接口
    port = int(os.getenv("SERVER_PORT", "8004"))
    
    print(f"🚀 启动服务器...")
    print(f"📍 绑定地址: {host}:{port}")
    print(f"🌐 可通过以下地址访问:")
    print(f"   - http://localhost:{port}")
    print(f"   - http://127.0.0.1:{port}")
    print(f"   - http://<your-ip>:{port}")
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=True,
        log_level="info"
    )

