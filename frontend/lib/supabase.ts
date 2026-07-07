import { createClient, type SupabaseClient } from "@supabase/supabase-js";

const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

// Client Supabase optionnel : si non configuré, l'app fonctionne en polling pur.
export const supabase: SupabaseClient | null =
  url && anonKey ? createClient(url, anonKey) : null;
