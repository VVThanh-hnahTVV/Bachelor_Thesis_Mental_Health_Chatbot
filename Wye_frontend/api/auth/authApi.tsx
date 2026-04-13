import { apiPost } from "../apiMethod";

export type LoginRequest = {
  email: string;
  password: string;
};

export type RegisterRequest = {
  name: string;
  email: string;
  password: string;
};

export type AuthUser = {
  id: string;
  name: string;
  email: string;
};

export type AuthResponse = {
  access_token: string;
  refresh_token?: string;
  user: AuthUser;
};

export const login = (payload: LoginRequest) =>
  apiPost<AuthResponse, LoginRequest>("/auth/login", payload);

export const register = (payload: RegisterRequest) =>
  apiPost<AuthResponse, RegisterRequest>("/auth/register", payload);
