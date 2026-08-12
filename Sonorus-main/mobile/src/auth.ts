import * as SecureStore from 'expo-secure-store';
import { API_BASE } from './config';

const TOKEN_KEY = 'sonorus_token';
const USER_KEY = 'sonorus_user';

export interface AuthUser {
  id: string;
  email: string;
  name: string;
}

async function authRequest(path: string, body: object): Promise<{ token: string; user: AuthUser }> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data?.detail || 'Something went wrong');
  await SecureStore.setItemAsync(TOKEN_KEY, data.token);
  await SecureStore.setItemAsync(USER_KEY, JSON.stringify(data.user));
  return data;
}

export function signup(email: string, password: string, name: string) {
  return authRequest('/api/auth/signup', { email, password, name });
}

export function login(email: string, password: string) {
  return authRequest('/api/auth/login', { email, password });
}

export async function logout(): Promise<void> {
  await SecureStore.deleteItemAsync(TOKEN_KEY);
  await SecureStore.deleteItemAsync(USER_KEY);
}

export async function getToken(): Promise<string | null> {
  return SecureStore.getItemAsync(TOKEN_KEY);
}

export async function getStoredUser(): Promise<AuthUser | null> {
  const raw = await SecureStore.getItemAsync(USER_KEY);
  return raw ? JSON.parse(raw) : null;
}

export async function authHeader(): Promise<Record<string, string>> {
  const token = await getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}
