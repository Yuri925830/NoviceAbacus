"use client";
import { createContext, useContext, useEffect, useMemo, useState } from "react";

type PrivacyContextType = { hidden: boolean; toggle: () => void };
const PrivacyContext = createContext<PrivacyContextType>({
  hidden: false,
  toggle: () => {},
});
export const usePrivacy = () => useContext(PrivacyContext);

export function AppProviders({ children }: { children: React.ReactNode }) {
  const [hidden, setHidden] = useState(false);
  useEffect(() => {
    if ("serviceWorker" in navigator)
      navigator.serviceWorker.register("/sw.js").catch(() => {});
    const blur = () => {
      if (document.visibilityState === "hidden")
        document.documentElement.classList.add("app-obscured");
      else document.documentElement.classList.remove("app-obscured");
    };
    document.addEventListener("visibilitychange", blur);
    return () => document.removeEventListener("visibilitychange", blur);
  }, []);
  const value = useMemo(
    () => ({ hidden, toggle: () => setHidden((v) => !v) }),
    [hidden],
  );
  return (
    <PrivacyContext.Provider value={value}>{children}</PrivacyContext.Provider>
  );
}
