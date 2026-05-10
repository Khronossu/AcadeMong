import { useState, useEffect } from "react";
import { onAuthStateChanged, signInWithPopup, signOut as firebaseSignOut } from "firebase/auth";
import { auth, googleProvider } from "../firebase";

/**
 * Firebase auth hook.
 *
 * authState:
 *   "loading"         — Firebase initialising
 *   "signed-out"      — no Firebase user
 *   "needs-register"  — Firebase user exists but not yet in our DB
 *   "signed-in"       — fully authenticated
 */
export function useAuth() {
  const [user, setUser] = useState(null);
  const [authState, setAuthState] = useState("loading");
  const [username, setUsername] = useState(null);
  const [registerError, setRegisterError] = useState(null);

  useEffect(() => {
    const unsub = onAuthStateChanged(auth, async (firebaseUser) => {
      if (!firebaseUser) {
        setUser(null);
        setUsername(null);
        setAuthState("signed-out");
        return;
      }
      setUser(firebaseUser);
      await _tryLogin(firebaseUser);
    });
    return unsub;
  }, []);

  async function _tryLogin(firebaseUser) {
    try {
      const idToken = await firebaseUser.getIdToken();
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ idToken }),
      });
      if (res.ok) {
        const data = await res.json();
        setUsername(data.username);
        setAuthState("signed-in");
      } else if (res.status === 404) {
        setAuthState("needs-register");
      } else {
        setAuthState("signed-out");
      }
    } catch {
      setAuthState("signed-out");
    }
  }

  const signIn = () => signInWithPopup(auth, googleProvider);

  const signOut = async () => {
    await firebaseSignOut(auth);
    setUser(null);
    setUsername(null);
    setAuthState("signed-out");
  };

  const register = async (usernameInput) => {
    setRegisterError(null);
    try {
      const idToken = await user.getIdToken();
      const res = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ idToken, username: usernameInput }),
      });
      if (!res.ok) {
        const err = await res.json();
        setRegisterError(err.detail || "Registration failed");
        return;
      }
      await _tryLogin(user);
    } catch (e) {
      setRegisterError(e.message);
    }
  };

  // Always returns a fresh token — Firebase refreshes silently if needed.
  const getToken = () => {
    if (!user) throw new Error("Not authenticated");
    return user.getIdToken();
  };

  return { user, authState, username, signIn, signOut, register, registerError, getToken };
}
