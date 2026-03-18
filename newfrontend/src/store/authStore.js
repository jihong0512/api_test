import create from 'zustand';
import axios from 'axios';
import { message } from 'antd';
import { getErrorMessage } from '../utils/errorHandler';

// 动态获取后端 API 地址
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

export const useAuthStore = create((set) => ({
  isAuthenticated: !!localStorage.getItem('token'),
  token: localStorage.getItem('token') || null,
  user: null,

  login: async (username, password) => {
    try {
      const formData = new FormData();
      formData.append('username', username);
      formData.append('password', password);

      const response = await axios.post(`${API_URL}/api/session/token`, formData, {
        headers: {
          'Content-Type': 'multipart/form-data',
        },
      });

      const token = response.data.access_token;
      localStorage.setItem('token', token);

      // 设置axios默认header
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;

      // 获取用户信息
      const userResponse = await axios.get(`${API_URL}/api/session/me`);
      
      set({
        isAuthenticated: true,
        token,
        user: userResponse.data,
      });

      message.success('登录成功');
      return true;
    } catch (error) {
      const errorMsg = getErrorMessage(error);
      message.error('登录失败: ' + errorMsg);
      return false;
    }
  },

  logout: () => {
    localStorage.removeItem('token');
    delete axios.defaults.headers.common['Authorization'];
    set({
      isAuthenticated: false,
      token: null,
      user: null,
    });
    message.success('已退出登录');
  },

  checkAuth: async () => {
    const token = localStorage.getItem('token');
    if (token) {
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`;
      try {
        const response = await axios.get(`${API_URL}/api/session/me`);
        set({
          isAuthenticated: true,
          token,
          user: response.data,
        });
        return true;
      } catch (error) {
        localStorage.removeItem('token');
        delete axios.defaults.headers.common['Authorization'];
        set({
          isAuthenticated: false,
          token: null,
          user: null,
        });
        return false;
      }
    }
    return false;
  },
}));

