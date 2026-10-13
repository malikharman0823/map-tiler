import React from "react"
import { Outlet } from "react-router-dom"
import Sidebar from "./Sidebar"
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar"

export default function DashboardLayout() {
  return (
    <SidebarProvider defaultOpen={true}>
      <div className="flex min-h-screen w-full bg-[#f5f5f7] text-[#1d1d1f]">
        <Sidebar />
        <SidebarInset className="flex flex-1 flex-col min-w-0 bg-[#f5f5f7]">
          <Outlet />
        </SidebarInset>
      </div>
    </SidebarProvider>
  )
}
