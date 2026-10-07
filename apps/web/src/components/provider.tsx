"use client";

import {
  createContext,
  useContext,
  useEffect,
  useSyncExternalStore,
} from "react";

import { en, ru } from "@/lib/i18n";

const Context = createContext<{
  lang: string;
  setLang: (value: string) => void;
  t: (key: string) => string;
}>({ lang: "ru", setLang: () => {}, t: (key) => key });

function subscribe(callback: () => void) {
  window.addEventListener("storage", callback);
  window.addEventListener("nexora-language", callback);
  return () => {
    window.removeEventListener("storage", callback);
    window.removeEventListener("nexora-language", callback);
  };
}

function snapshot() {
  return localStorage.getItem("nexora-language") === "en" ? "en" : "ru";
}

export function Provider({ children }: { children: React.ReactNode }) {
  const lang = useSyncExternalStore(subscribe, snapshot, () => "ru");

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  function setLang(value: string) {
    localStorage.setItem("nexora-language", value);
    window.dispatchEvent(new Event("nexora-language"));
  }

  const dict = lang === "en" ? en : ru;

  return (
    <Context.Provider value={{ lang, setLang, t: (key) => dict[key] || key }}>
      {children}
    </Context.Provider>
  );
}

export function useI18n() {
  return useContext(Context);
}

export function Language() {
  const { lang, setLang, t } = useI18n();
  return (
    <select
      aria-label={t("languageLabel")}
      value={lang}
      onChange={(e) => setLang(e.target.value)}
    >
      <option value="ru">{t("languageRu")}</option>
      <option value="en">{t("languageEn")}</option>
    </select>
  );
}
