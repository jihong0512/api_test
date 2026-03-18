import axios from 'axios';

// 动态获取后端 API 地址
// 如果设置了环境变量，优先使用环境变量
// 否则根据当前访问的域名/IP 自动构建后端地址
function getApiUrl() {
  // 优先使用环境变量
  if (process.env.REACT_APP_API_URL) {
    return process.env.REACT_APP_API_URL;
  }
  
  // 获取当前访问的协议和主机名
  const protocol = window.location.protocol; // http: 或 https:
  const hostname = window.location.hostname; // localhost 或 192.168.1.6
  
  // 如果是 localhost 或 127.0.0.1，使用 localhost:8004
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return 'http://localhost:8004';
  }
  
  // 否则使用相同的 IP 地址，端口改为 8004
  return `${protocol}//${hostname}:8004`;
}

const API_URL = getApiUrl();

const client = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 请求拦截器
client.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// 响应拦截器
client.interceptors.response.use(
  (response) => {
    return response.data;
  },
  (error) => {
    // 已禁用登录功能，不再跳转到登录页
    // if (error.response?.status === 401) {
    //   localStorage.removeItem('token');
    //   window.location.href = '/login';
    // }
    return Promise.reject(error);
  }
);

export default client;

