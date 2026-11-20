"use client";

import React, { createContext, useContext, useState, useCallback } from "react";
import { api } from "@/lib/api";

interface SimulationState {
  rainfallMm: number;
  useSimulation: boolean;
  setRainfallMm: (mm: number) => void;
  setUseSimulation: (sim: boolean) => void;
  refreshTick: number;
  triggerRefresh: () => void;
  resetting: boolean;
  resetDemo: () => Promise<void>;
}

const SimulationContext = createContext<SimulationState | null>(null);

export function SimulationProvider({ children }: { children: React.ReactNode }) {
  const [rainfallMm, setRainfallMm] = useState<number>(20);
  const [useSimulation, setUseSimulation] = useState<boolean>(true);
  const [refreshTick, setRefreshTick] = useState<number>(0);
  const [resetting, setResetting] = useState<boolean>(false);

  const triggerRefresh = useCallback(() => {
    setRefreshTick((t) => t + 1);
  }, []);

  const resetDemo = useCallback(async () => {
    setResetting(true);
    try {
      await api.resetDemo();
      setRainfallMm(20);
      setUseSimulation(true);
      setRefreshTick((t) => t + 1);
    } finally {
      setResetting(false);
    }
  }, []);

  return (
    <SimulationContext.Provider
      value={{
        rainfallMm,
        useSimulation,
        setRainfallMm,
        setUseSimulation,
        refreshTick,
        triggerRefresh,
        resetting,
        resetDemo,
      }}
    >
      {children}
    </SimulationContext.Provider>
  );
}

export function useSimulation() {
  const ctx = useContext(SimulationContext);
  if (!ctx) {
    throw new Error("useSimulation must be used within SimulationProvider");
  }
  return ctx;
}
