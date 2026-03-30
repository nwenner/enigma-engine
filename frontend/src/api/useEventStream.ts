import { useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";

/**
 * Connects to the backend SSE stream and invalidates TanStack Query caches
 * when sync events arrive.  Reconnects automatically on connection drop.
 *
 * Mount this once at the App level.
 */
export function useEventStream(): void {
  const qc = useQueryClient();

  useEffect(() => {
    let es: EventSource | null = null;
    let retryTimeout: ReturnType<typeof setTimeout> | null = null;
    let unmounted = false;

    function connect() {
      if (unmounted) return;

      es = new EventSource("/api/events/stream");

      es.onmessage = (e: MessageEvent) => {
        let event: { type: string };
        try {
          event = JSON.parse(e.data as string);
        } catch {
          return;
        }

        if (event.type === "connected") return;

        if (event.type === "sync_complete") {
          qc.invalidateQueries({ queryKey: ["preflight"] });
          qc.invalidateQueries({ queryKey: ["sync", "summary"] });
          qc.invalidateQueries({ queryKey: ["autosync", "status"] });
          qc.invalidateQueries({ queryKey: ["characters"] });
          qc.invalidateQueries({ queryKey: ["seasons", "active", "stats"] });
          qc.invalidateQueries({ queryKey: ["sync", "toast-poll"] });
          qc.invalidateQueries({ queryKey: ["backups"] });
        }

        if (event.type === "device_online" || event.type === "device_offline") {
          qc.invalidateQueries({ queryKey: ["preflight"] });
          qc.invalidateQueries({ queryKey: ["autosync", "status"] });
        }

        if (event.type === "conflict") {
          qc.invalidateQueries({ queryKey: ["autosync", "status"] });
          qc.invalidateQueries({ queryKey: ["sync", "summary"] });
        }
      };

      es.onerror = () => {
        es?.close();
        es = null;
        if (!unmounted) {
          retryTimeout = setTimeout(connect, 3_000);
        }
      };
    }

    connect();

    return () => {
      unmounted = true;
      if (retryTimeout !== null) clearTimeout(retryTimeout);
      es?.close();
    };
  }, [qc]);
}
