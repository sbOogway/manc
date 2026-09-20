import { inject } from "vue";

import type { Client } from "../api/client";

export function useClient(): Client {
  const client = inject<Client>("client");
  if (!client) throw new Error("the API client is provided by main.ts");
  return client;
}
