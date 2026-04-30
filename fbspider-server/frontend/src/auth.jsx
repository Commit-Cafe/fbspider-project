import { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { Spin } from 'antd';
import API, { setAuthUser, setAuthToken } from './api';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const location = useLocation();

  const fetchUser = useCallback(async () => {
    try {
      const data = await API.get('/api/auth/me');
      if (data.success) {
        setAuthUser(data.user);
        setUser(data.user);
        return data.user;
      } else {
        setAuthUser(null);
        setAuthToken('');
        setUser(null);
        return null;
      }
    } catch {
      setAuthUser(null);
      setAuthToken('');
      setUser(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  // On mount: check auth, redirect to login if not authenticated
  useEffect(() => {
    fetchUser().then(u => {
      if (!u && location.pathname !== '/login') navigate('/login', { replace: true });
    });
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  const login = async (username, password) => {
    const data = await API.post('/api/auth/login', {
      username, password, issue_token: true, client_type: 'browser',
    });
    if (!data.success) throw new Error(data.message || '登录失败');
    setAuthToken(data.token || '');
    await fetchUser();
    navigate('/dashboard', { replace: true });
  };

  const logout = async () => {
    await API.post('/api/auth/logout').catch(() => {});
    setAuthUser(null);
    setAuthToken('');
    setUser(null);
    navigate('/login', { replace: true });
  };

  if (loading) {
    return <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}><Spin size="large" /></div>;
  }

  return (
    <AuthContext.Provider value={{ user, login, logout, refreshUser: fetchUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
