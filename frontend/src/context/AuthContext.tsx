import React, { createContext, useContext, useState, useEffect } from 'react';
import { User } from '../types';
import { apiClient } from '../services/api';

interface AuthContextType {
  user: User | null;
  token: string | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (payload: { email: string; password: string; full_name: string; organization_name: string; role?: string }) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(() => {
    const saved = localStorage.getItem('techdebt_user');
    return saved ? JSON.parse(saved) : null;
  });
  const [token, setToken] = useState<string | null>(() => localStorage.getItem('techdebt_token'));
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    const initAuth = async () => {
      const storedToken = localStorage.getItem('techdebt_token');
      if (storedToken) {
        try {
          const profile = await apiClient.getMe();
          setUser(profile);
          localStorage.setItem('techdebt_user', JSON.stringify(profile));
        } catch {
          logout();
        }
      }
      setIsLoading(false);
    };
    initAuth();
  }, []);

  const login = async (email: string, password: string) => {
    const data = await apiClient.login(email, password);
    setToken(data.access_token);
    setUser(data.user);
    localStorage.setItem('techdebt_token', data.access_token);
    localStorage.setItem('techdebt_user', JSON.stringify(data.user));
  };

  const register = async (payload: { email: string; password: string; full_name: string; organization_name: string; role?: string }) => {
    const data = await apiClient.register(payload);
    setToken(data.access_token);
    setUser(data.user);
    localStorage.setItem('techdebt_token', data.access_token);
    localStorage.setItem('techdebt_user', JSON.stringify(data.user));
  };

  const logout = () => {
    setUser(null);
    setToken(null);
    localStorage.removeItem('techdebt_token');
    localStorage.removeItem('techdebt_user');
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        isLoading,
        login,
        register,
        logout,
        isAuthenticated: !!user && !!token,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

