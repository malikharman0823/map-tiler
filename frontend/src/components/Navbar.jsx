import React from "react"
import { Link, NavLink } from "react-router-dom"

export default function Navbar() {
  return (
    <nav className="h-11 bg-black text-white" aria-label="Primary navigation">
      <div className="mx-auto flex h-full max-w-canvas items-center justify-between px-5 phone:px-8">
        <Link
          to="/"
          className="pressable flex min-h-11 items-center text-[17px] font-semibold tracking-[-0.374px] phone:text-[21px]"
        >
          MapTiler Clone
        </Link>
        <div className="flex h-full items-center gap-2 small-phone:gap-5">
          <NavLink
            to="/"
            end
            className={({ isActive }) =>
              `pressable flex min-h-11 items-center px-2 text-[12px] tracking-[-0.12px] ${
                isActive ? "text-white" : "text-[#cccccc]"
              }`
            }
          >
            Datasets
          </NavLink>
          <NavLink
            to="/upload"
            className="pressable inline-flex min-h-8 items-center rounded-full bg-primary px-4 text-[12px] tracking-[-0.12px] text-white small-phone:min-h-9 small-phone:px-5 small-phone:text-[14px]"
          >
            Upload
          </NavLink>
        </div>
      </div>
    </nav>
  )
}
