/**
 * 统一错误处理工具
 * 处理FastAPI返回的各种错误格式
 */
export const getErrorMessage = (error) => {
  if (!error) {
    return '未知错误';
  }

  // 如果是字符串，直接返回
  if (typeof error === 'string') {
    return error;
  }

  // 处理axios错误响应
  if (error.response?.data?.detail) {
    const detail = error.response.data.detail;
    
    // 如果是数组（FastAPI验证错误格式）
    if (Array.isArray(detail)) {
      return detail.map(err => {
        if (typeof err === 'string') {
          return err;
        }
        // 提取错误消息
        const msg = err.msg || err.message || JSON.stringify(err);
        const loc = err.loc ? `[${err.loc.join('.')}]` : '';
        return loc ? `${loc} ${msg}` : msg;
      }).join('; ');
    }
    
    // 如果是字符串
    if (typeof detail === 'string') {
      return detail;
    }
    
    // 如果是对象
    if (typeof detail === 'object') {
      return detail.msg || detail.message || JSON.stringify(detail);
    }
  }

  // 处理error.message
  if (error.message) {
    return error.message;
  }

  // 默认返回
  return '操作失败';
};

