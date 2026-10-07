import "./index.css";

import { createQueryClient } from "@scorecode/api-client";
import { applyColorScheme, readColorScheme } from "@scorecode/ui";
import { QueryClientProvider } from "@tanstack/react-query";
import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";

import { router } from "./routes";

applyColorScheme(readColorScheme());
// Toasts never show while the app boots, so their renderer loads right after the first paint instead of
// being part of every student's first download (P10.5 budget).
const Toaster = lazy(() => import("@scorecode/ui/toast").then((m) => ({ default: m.Toaster })));
const queryClient = createQueryClient();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      <Suspense fallback={null}>
        <Toaster />
      </Suspense>
    </QueryClientProvider>
  </StrictMode>,
);
