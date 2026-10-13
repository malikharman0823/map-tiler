import React, { Suspense, lazy, useEffect } from "react"
import { BrowserRouter, Navigate, Route, Routes, useParams } from "react-router-dom"

import DashboardLayout from "./components/DashboardLayout"
import { ensureActiveSession } from "./api"

const HomePage = lazy(() => import("./pages/HomePage"))
const UploadPage = lazy(() => import("./pages/UploadPage"))
const DatasetPage = lazy(() => import("./pages/DatasetPage"))
const GeoreferencePage = lazy(() => import("./pages/GeoreferencePage"))
const WorkspacePage = lazy(() => import("./pages/WorkspacePage"))

function DatasetWorkspaceRedirect() {
  const { id } = useParams()
  return <Navigate to={`/datasets/${id}/workspace`} replace />
}

import { TooltipProvider } from "@/components/ui/tooltip"

export default function App() {
  useEffect(() => {
    ensureActiveSession().catch((err) => {
      console.warn("Session check failed:", err)
    })
  }, [])
  return (
    <TooltipProvider>
      <BrowserRouter>
        <Suspense
          fallback={
            <div className="flex min-h-screen items-center justify-center bg-[#f5f5f7] text-[#7a7a7a] text-sm">
              Loading…
            </div>
          }
        >
          <Routes>
            <Route element={<DashboardLayout />}>
              <Route path="/" element={<HomePage />} />
              <Route path="/upload" element={<Navigate to="/" replace />} />
            </Route>
            <Route path="/datasets/:id" element={<DatasetWorkspaceRedirect />} />
            <Route path="/datasets/:id/legacy" element={<DatasetPage />} />
            <Route path="/datasets/:id/workspace" element={<WorkspacePage />} />
            <Route path="/datasets/:id/georeference" element={<GeoreferencePage />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </TooltipProvider>
  )
}
