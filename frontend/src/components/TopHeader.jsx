import React from "react"
import { Link } from "react-router-dom"
import { SidebarTrigger } from "@/components/ui/sidebar"
import { Separator } from "@/components/ui/separator"
import { User, ChevronRight } from "lucide-react"
import EndSessionDialog from "./EndSessionDialog"

export default function TopHeader({ breadcrumbs = [], actions }) {
  return (
    <header className="sticky top-0 z-40 h-14 bg-[#f5f5f7]/85 backdrop-blur-md border-b border-[#e0e0e0] px-4 md:px-6 flex items-center justify-between">
      {/* Left: Sidebar trigger + Breadcrumb */}
      <div className="flex items-center gap-3 text-xs">
        <SidebarTrigger className="text-[#1d1d1f] hover:bg-[#fafafc] hover:text-[#0066cc] rounded-lg transition-colors" />
        <Separator orientation="vertical" className="h-4 bg-[#e0e0e0]" />

        <div className="flex items-center gap-1.5 text-xs">
          <span className="text-[#7a7a7a] font-normal">Workspace</span>
          <ChevronRight className="size-3 text-[#7a7a7a]" />
          {breadcrumbs.map((crumb, i) => (
            <React.Fragment key={i}>
              {crumb.path ? (
                <Link
                  to={crumb.path}
                  className="text-[#7a7a7a] hover:text-[#0066cc] transition-colors"
                >
                  {crumb.label}
                </Link>
              ) : (
                <span
                  className={
                    i === breadcrumbs.length - 1
                      ? "text-[#1d1d1f] font-semibold"
                      : "text-[#7a7a7a]"
                  }
                >
                  {crumb.label}
                </span>
              )}
              {i < breadcrumbs.length - 1 && (
                <ChevronRight className="size-3 text-[#7a7a7a]" />
              )}
            </React.Fragment>
          ))}
        </div>
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-2.5">
        {actions}
        <EndSessionDialog />
        <div className="h-4 w-px bg-[#e0e0e0] mx-1 hidden sm:block"></div>
        <div className="h-8 w-8 rounded-full bg-[#ffffff] border border-[#e0e0e0] flex items-center justify-center text-[#1d1d1f] text-xs font-medium shadow-xs hover:border-[#0066cc] hover:text-[#0066cc] transition-colors cursor-pointer">
          <User className="size-4" />
        </div>
      </div>
    </header>
  )
}
