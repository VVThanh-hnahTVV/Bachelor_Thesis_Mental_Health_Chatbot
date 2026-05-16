import { useState, useEffect } from "react";

interface User {
  _id: string;
  name: string;
  email: string;
}

export function useSession() {
  const [user, setUser] = useState<User | null>({
    _id: "guest",
    name: "Guest",
    email: "guest@local",
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void checkSession();
  }, []);

  const checkSession = async () => {
    setUser({
      _id: "guest",
      name: "Guest",
      email: "guest@local",
    });
    setLoading(false);
  };

  const logout = async () => {
    setUser({
      _id: "guest",
      name: "Guest",
      email: "guest@local",
    });
  };

  return {
    user,
    loading,
    isAuthenticated: true,
    logout,
    checkSession,
  };
}
