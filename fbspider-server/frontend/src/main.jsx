import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { ConfigProvider } from 'antd';
import zhCN from 'antd/locale/zh_CN';
import App from './App';

ReactDOM.createRoot(document.getElementById('root')).render(
  <ConfigProvider locale={zhCN} theme={{ token: { borderRadius: 8 } }}>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </ConfigProvider>
);
