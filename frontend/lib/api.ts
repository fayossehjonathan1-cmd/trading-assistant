"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { supabase } from "./supabase";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status} sur ${path}`);
  return res.json();
}

/**
 * Données live : polling régulier + rafraîchissement immédiat via Supabase Realtime
 * quand NEXT_PUBLIC_SUPABASE_URL / ANON_KEY sont configurés.
 */
export function useLiveData<T>(path: string, intervalMs = 10000) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const mounted = useRef(true);

  const refresh = useCallback(async () => {
    try {
      const json = await fetchJson<T>(path);
      if (mounted.current) {
        setData(json);
        setError(null);
      }
    } catch (err) {
      if (mounted.current) setError(err instanceof Error ? err.message : "Erreur réseau");
    } finally {
      if (mounted.current) setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    mounted.current = true;
    refresh();
    const timer = setInterval(refresh, intervalMs);

    let channel: ReturnType<NonNullable<typeof supabase>["channel"]> | null = null;
    if (supabase) {
      channel = supabase
        .channel(`live-${path}`)
        .on("postgres_changes", { event: "*", schema: "public", table: "signals" }, refresh)
        .on("postgres_changes", { event: "*", schema: "public", table: "trades" }, refresh)
        .subscribe();
    }

    return () => {
      mounted.current = false;
      clearInterval(timer);
      channel?.unsubscribe();
    };
  }, [path, intervalMs, refresh]);

  return { data, error, loading, refresh };
}

export function formatPrice(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return value >= 100
    ? value.toLocaleString("fr-FR", { maximumFractionDigits: 2 })
    : value.toLocaleString("fr-FR", { maximumFractionDigits: 5 });
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("fr-FR", {
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
  });
}
