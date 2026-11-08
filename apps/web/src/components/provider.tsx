"use client";

import {
  createContext,
  useContext,
  useEffect,
  useSyncExternalStore,
} from "react";

import { en, ru } from "@/lib/i18n";
import { kk } from "@/lib/i18n-kk";

const dictionaries: Record<string, Record<string, string>> = { ru, kk, en };

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

// Fallback when storage is blocked (private mode, disabled site data): the choice lives until reload.
let memoryLanguage: string | null = null;

function snapshot() {
  let stored: string | null = memoryLanguage;
  try {
    stored = localStorage.getItem("nexora-language") ?? memoryLanguage;
  } catch {
    /* Storage unavailable: keep the in-memory choice. */
  }
  return stored === "en" || stored === "kk" ? stored : "ru";
}

export function Provider({ children }: { children: React.ReactNode }) {
  const lang = useSyncExternalStore(subscribe, snapshot, () => "ru");

  useEffect(() => {
    document.documentElement.lang = lang;
  }, [lang]);

  function setLang(value: string) {
    memoryLanguage = value;
    try {
      localStorage.setItem("nexora-language", value);
    } catch {
      /* Storage unavailable: memoryLanguage keeps the choice for this page. */
    }
    window.dispatchEvent(new Event("nexora-language"));
  }

  const dict = dictionaries[lang] || ru;

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
      <option value="kk">{t("languageKk")}</option>
      <option value="en">{t("languageEn")}</option>
    </select>
  );
}
