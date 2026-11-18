import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./index.css";
import { AuthProvider } from "@/lib/auth";
import { ToastProvider } from "@/components/ui";
import { PublicLayout } from "@/components/layout/PublicLayout";
import { PanelLayout } from "@/components/layout/PanelLayout";
import { CatalogPage } from "@/features/public/CatalogPage";
import { EventPage } from "@/features/public/EventPage";
import { LoginPage, RegisterPage } from "@/features/public/AuthPages";
import { MyTicketsPage } from "@/features/participant/MyTicketsPage";
import { DashboardPage } from "@/features/panel/DashboardPage";
import { IncidentsPage } from "@/features/panel/IncidentsPage";
import { ApprovalsPage } from "@/features/panel/ApprovalsPage";
import { RunDetailPage, RunsPage } from "@/features/panel/RunsPage";
import { AttendeesPage, CheckinPage, SupportPage } from "@/features/panel/OpsPages";
import { GraphPage, KnowledgePage } from "@/features/panel/KnowledgePages";
import { AgentsPage, AuditPage, EvalsPage } from "@/features/panel/QualityPages";

const queryClient = new QueryClient({ defaultOptions: { queries: { staleTime: 15_000, retry: 1, refetchOnWindowFocus: false } } });

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <ToastProvider>
          <BrowserRouter>
            <Routes>
              <Route element={<PublicLayout />}>
                <Route index element={<CatalogPage />} />
                <Route path="eventos/:slug" element={<EventPage />} />
                <Route path="meus-ingressos" element={<MyTicketsPage />} />
                <Route path="entrar" element={<LoginPage />} />
                <Route path="cadastro" element={<RegisterPage />} />
              </Route>
              <Route path="painel" element={<PanelLayout />}>
                <Route index element={<DashboardPage />} />
                <Route path="ocorrencias" element={<IncidentsPage />} />
                <Route path="aprovacoes" element={<ApprovalsPage />} />
                <Route path="inscritos" element={<AttendeesPage />} />
                <Route path="checkin" element={<CheckinPage />} />
                <Route path="chamados" element={<SupportPage />} />
                <Route path="grafo" element={<GraphPage />} />
                <Route path="conhecimento" element={<KnowledgePage />} />
                <Route path="trajetorias" element={<RunsPage />} />
                <Route path="trajetorias/:id" element={<RunDetailPage />} />
                <Route path="evals" element={<EvalsPage />} />
                <Route path="agentes" element={<AgentsPage />} />
                <Route path="auditoria" element={<AuditPage />} />
              </Route>
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </BrowserRouter>
        </ToastProvider>
      </AuthProvider>
    </QueryClientProvider>
  </React.StrictMode>,
);
