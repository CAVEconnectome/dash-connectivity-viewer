import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { NeuronView } from "./components/NeuronView";
import { TableRowsView } from "./components/TableRowsView";
import { TableView } from "./components/TableView";
import { Workspace } from "./components/Workspace";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 0,
      refetchOnWindowFocus: false,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter
        future={{
          v7_startTransition: true,
          v7_relativeSplatPath: true,
        }}
      >
        <Routes>
          <Route path="/" element={<Workspace />}>
            <Route index element={<Navigate to="/neuron" replace />} />
            <Route path="neuron" element={<NeuronView />} />
            <Route path="tables" element={<TableView />} />
            <Route path="tables/:name" element={<TableRowsView />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
