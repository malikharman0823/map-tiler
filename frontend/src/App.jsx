import React, { Suspense, lazy } from "react"
import { BrowserRouter, Route, Routes } from "react-router-dom"

import Navbar from "./components/Navbar"

const HomePage = lazy(() => import("./pages/HomePage"))
const UploadPage = lazy(() => import("./pages/UploadPage"))
const DatasetPage = lazy(() => import("./pages/DatasetPage"))

export default function App() {
  return (
    <BrowserRouter>
      <Navbar />
      <Suspense fallback={<p className="page-message">Loading…</p>}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/upload" element={<UploadPage />} />
          <Route path="/datasets/:id" element={<DatasetPage />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}
