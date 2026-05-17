import { initializeApp } from "firebase/app";
import { getAuth, GoogleAuthProvider } from "firebase/auth";

const firebaseConfig = {
  apiKey:            import.meta.env.VITE_FIREBASE_API_KEY            || "AIzaSyA4_YPCybW0L1sJ4T4yDN9Z31zNDISOotI",
  authDomain:        import.meta.env.VITE_FIREBASE_AUTH_DOMAIN        || "academong-dd125.firebaseapp.com",
  projectId:         import.meta.env.VITE_FIREBASE_PROJECT_ID         || "academong-dd125",
  storageBucket:     import.meta.env.VITE_FIREBASE_STORAGE_BUCKET     || "academong-dd125.firebasestorage.app",
  messagingSenderId: import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID || "999724010913",
  appId:             import.meta.env.VITE_FIREBASE_APP_ID             || "1:999724010913:web:d1df8407e73ab3aae40fe0",
};

const app = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export const googleProvider = new GoogleAuthProvider();
