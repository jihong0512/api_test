import create from 'zustand';
import axios from 'axios';
import { message } from 'antd';
import { getErrorMessage } from '../utils/errorHandler';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8004';

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




