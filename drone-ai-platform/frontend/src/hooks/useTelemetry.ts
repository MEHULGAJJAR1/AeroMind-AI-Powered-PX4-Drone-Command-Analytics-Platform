import { useCallback, useEffect, useState } from 'react';
import { api, telemetrySocketUrl } from '../services/api';
import type { Telemetry } from '../types';

export function useTelemetry(enabled: boolean) {
  const [telemetry, setTelemetry] = useState<Telemetry | null>(null);
  const [history, setHistory] = useState<Telemetry[]>([]);
  const [socketConnected, setSocketConnected] = useState(false);
  const [lastMessageAt, setLastMessageAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const acceptTelemetry = useCallback((value: Telemetry) => {
    setTelemetry(value);
    setHistory((current) => {
      if (current.at(-1)?.timestamp === value.timestamp) return [...current.slice(0, -1), value];
      return [...current.slice(-179), value];
    });
    setError(null);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const value = await api.latest();
      acceptTelemetry(value);
      return value;
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : 'Telemetry API is unavailable');
      return null;
    }
  }, [acceptTelemetry]);

  const hydrateHistory = useCallback(async () => {
    try {
      const records = await api.telemetryHistory(180);
      const persisted = records.map((record) => record.payload as unknown as Telemetry).filter((item) => Boolean(item.timestamp));
      setHistory((current) => {
        const merged = new Map<string, Telemetry>();
        for (const sample of [...persisted, ...current]) merged.set(sample.timestamp, sample);
        return [...merged.values()].sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp)).slice(-180);
      });
    } catch {
      // A missing database history should not stop the live WebSocket stream.
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      setTelemetry(null);
      setHistory([]);
      setSocketConnected(false);
      return;
    }
    let live = true;
    let socket: WebSocket | null = null;
    let retryTimer: number | undefined;
    let pollTimer: number | undefined;
    let attempts = 0;

    const fetchLatest = async () => {
      try {
        const value = await api.latest();
        if (live) acceptTelemetry(value);
      } catch (failure) {
        if (live) setError(failure instanceof Error ? failure.message : 'Telemetry API is unavailable');
      }
    };

    const scheduleReconnect = () => {
      if (!live || retryTimer) return;
      const delay = Math.min(1000 * 2 ** attempts, 15000);
      attempts += 1;
      retryTimer = window.setTimeout(() => {
        retryTimer = undefined;
        connect();
      }, delay);
    };

    const connect = async () => {
      if (!live) return;
      try {
        const { ticket } = await api.wsTicket();
        if (!live) return;
        socket = new WebSocket(telemetrySocketUrl(ticket));
      } catch (failure) {
        if (live) setError(failure instanceof Error ? failure.message : 'WebSocket ticket unavailable');
        scheduleReconnect();
        return;
      }
      socket.onopen = () => {
        attempts = 0;
        if (live) setSocketConnected(true);
      };
      socket.onmessage = (event) => {
        if (!live) return;
        setLastMessageAt(Date.now());
        try {
          const message = JSON.parse(String(event.data)) as { type?: string; data?: Telemetry };
          if (message.type === 'telemetry' && message.data) acceptTelemetry(message.data);
        } catch {
          setError('Received an unreadable telemetry frame');
        }
      };
      socket.onerror = () => socket?.close();
      socket.onclose = () => {
        if (!live) return;
        setSocketConnected(false);
        scheduleReconnect();
      };
    };

    void fetchLatest();
    void hydrateHistory();
    void connect();
    pollTimer = window.setInterval(() => {
      if (!socket || socket.readyState !== WebSocket.OPEN) void fetchLatest();
    }, 3000);

    return () => {
      live = false;
      if (retryTimer) window.clearTimeout(retryTimer);
      if (pollTimer) window.clearInterval(pollTimer);
      socket?.close();
    };
  }, [enabled, acceptTelemetry, hydrateHistory]);

  return { telemetry, history, setTelemetry, socketConnected, lastMessageAt, error, refresh };
}
