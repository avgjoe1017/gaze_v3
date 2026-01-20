import { create } from "zustand";

interface EngineState {
  port: number | null;
  token: string | null;
  setPort: (port: number | null) => void;
  setToken: (token: string | null) => void;
}

export const useEngineStore = create<EngineState>((set) => ({
  port: null,
  token: null,
  setPort: (port) => set({ port }),
  setToken: (token) => set({ token }),
}));
