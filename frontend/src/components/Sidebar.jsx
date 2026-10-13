import React from "react"
import { NavLink } from "react-router-dom"
import {
  Sidebar as ShadcnSidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  useSidebar,
} from "@/components/ui/sidebar"
import {
  Layers,
  UploadCloud,
  MapPin,
  Compass,
} from "lucide-react"
import EndSessionDialog from "./EndSessionDialog"

export default function Sidebar() {
  const { setOpenMobile } = useSidebar()

  const handleNavClick = () => {
    // Automatically close mobile drawer when link is clicked
    if (setOpenMobile) {
      setOpenMobile(false)
    }
  }

  return (
    <ShadcnSidebar
      className="border-r border-[#e0e0e0] bg-[#ffffff] text-[#1d1d1f]"
    >
      {/* Brand Header */}
      <SidebarHeader className="h-14 border-b border-[#e0e0e0] px-4 flex flex-row items-center justify-between">
        <NavLink
          to="/"
          onClick={handleNavClick}
          className="flex items-center gap-2.5 group"
        >
          <div className="h-7 w-7 rounded-lg bg-[#0066cc] text-white flex items-center justify-center font-bold shadow-xs transition-transform group-hover:scale-105">
            <Compass className="size-4" />
          </div>
          <div className="flex flex-col">
            <span className="font-semibold text-sm tracking-tight text-[#1d1d1f]">
              MapTiler
            </span>
          </div>
        </NavLink>
        <span className="font-mono text-[10px] uppercase font-semibold px-2 py-0.5 rounded-full border border-[#e0e0e0] bg-[#f5f5f7] text-[#7a7a7a]">
          Pro MVP
        </span>
      </SidebarHeader>

      {/* Main Navigation */}
      <SidebarContent className="px-2 py-3">
        <SidebarGroup>
          <SidebarGroupLabel className="text-[11px] font-semibold uppercase tracking-wider text-[#7a7a7a] px-2 mb-1">
            Workspace
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu className="space-y-1">
              <SidebarMenuItem>
                <NavLink to="/" end onClick={handleNavClick}>
                  {({ isActive }) => (
                    <SidebarMenuButton
                      isActive={isActive}
                      className={`w-full justify-start gap-2.5 rounded-xl px-3 py-2 text-xs font-medium transition-all ${
                        isActive
                          ? "bg-[#0066cc] text-white font-medium hover:bg-[#0071e3] hover:text-white"
                          : "text-[#333333] hover:bg-[#f5f5f7] hover:text-[#1d1d1f]"
                      }`}
                    >
                      <UploadCloud className={`size-4 ${isActive ? "text-white" : "text-[#7a7a7a]"}`} />
                      <span>Upload Dataset</span>
                    </SidebarMenuButton>
                  )}
                </NavLink>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      {/* Footer Info */}
      <SidebarFooter className="border-t border-[#e0e0e0] p-3 text-[11px] text-[#7a7a7a] bg-[#fafafc] space-y-2">
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-1.5">
            <span className="size-2 rounded-full bg-[#34c759] inline-block animate-pulse"></span>
            Spatial Server
          </span>
          <span className="font-mono text-[10px] text-[#7a7a7a]">Online</span>
        </div>
        <div className="pt-1.5 border-t border-[#e0e0e0]/60 flex items-center justify-between">
          <span className="text-[10px] text-[#7a7a7a]">Workspace Session</span>
          <EndSessionDialog
            trigger={
              <button
                type="button"
                className="text-[10px] font-medium text-[#7a7a7a] hover:text-[#dc2626] transition-colors cursor-pointer"
                title="End session and clear workspace"
              >
                Clear
              </button>
            }
          />
        </div>
      </SidebarFooter>
    </ShadcnSidebar>
  )
}
