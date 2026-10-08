import React, { Suspense, lazy } from "react"
import { BrowserRouter, Route, Routes } from "react-router-dom"

import DashboardLayout from "./components/DashboardLayout"

const HomePage = lazy(() => import("./pages/HomePage"))
const UploadPage = lazy(() => import("./pages/UploadPage"))
const DatasetPage = lazy(() => import("./pages/DatasetPage"))
const GeoreferencePage = lazy(() => import("./pages/GeoreferencePage"))

export default function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<p className="text-zinc-400 p-8">Loading…</p>}>
        <Routes>
          <Route element={<DashboardLayout />}>
            <Route path="/" element={<HomePage />} />
            <Route path="/upload" element={<UploadPage />} />
          </Route>
          <Route path="/datasets/:id" element={<DatasetPage />} />
          <Route path="/datasets/:id/georeference" element={<GeoreferencePage />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}
